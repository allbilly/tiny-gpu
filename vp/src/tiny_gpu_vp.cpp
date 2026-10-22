#include <array>
#include <cstdint>
#include <cstring>
#include <iomanip>
#include <iostream>
#include <stdexcept>
#include <string>
#include <vector>

#include <systemc>
#include <tlm>
#include <tlm_utils/simple_initiator_socket.h>
#include <tlm_utils/simple_target_socket.h>

namespace vp {

constexpr uint64_t kRegThreadCount = 0x0000;
constexpr uint64_t kRegStart = 0x0004;
constexpr uint64_t kRegStatus = 0x0008;
constexpr uint64_t kProgramBase = 0x1000;
constexpr uint64_t kDataBase = 0x2000;

constexpr unsigned kProgramRows = 256;
constexpr unsigned kDataRows = 256;
constexpr unsigned kThreadsPerBlock = 4;

enum Opcode : uint8_t {
    kNop = 0x0,
    kBranch = 0x1,
    kCmp = 0x2,
    kAdd = 0x3,
    kSub = 0x4,
    kMul = 0x5,
    kDiv = 0x6,
    kLoad = 0x7,
    kStore = 0x8,
    kConst = 0x9,
    kRet = 0xf,
};

struct Workload {
    std::string name;
    std::vector<uint16_t> program;
    std::vector<uint8_t> data;
    uint32_t threads = 0;
    uint32_t result_base = 0;
    std::vector<uint8_t> expected;
};

Workload matadd_workload()
{
    Workload workload;
    workload.name = "matadd";
    workload.program = {
        0b0101000011011110,
        0b0011000000001111,
        0b1001000100000000,
        0b1001001000001000,
        0b1001001100010000,
        0b0011010000010000,
        0b0111010001000000,
        0b0011010100100000,
        0b0111010101010000,
        0b0011011001000101,
        0b0011011100110000,
        0b1000000001110110,
        0b1111000000000000,
    };
    workload.data = {0, 1, 2, 3, 4, 5, 6, 7, 0, 1, 2, 3, 4, 5, 6, 7};
    workload.threads = 8;
    workload.result_base = 16;
    for (unsigned i = 0; i < 8; ++i) {
        workload.expected.push_back(static_cast<uint8_t>(workload.data[i] + workload.data[i + 8]));
    }
    return workload;
}

Workload matmul_workload()
{
    Workload workload;
    workload.name = "matmul";
    workload.program = {
        0b0101000011011110,
        0b0011000000001111,
        0b1001000100000001,
        0b1001001000000010,
        0b1001001100000000,
        0b1001010000000100,
        0b1001010100001000,
        0b0110011000000010,
        0b0101011101100010,
        0b0100011100000111,
        0b1001100000000000,
        0b1001100100000000,
        0b0101101001100010,
        0b0011101010101001,
        0b0011101010100011,
        0b0111101010100000,
        0b0101101110010010,
        0b0011101110110111,
        0b0011101110110100,
        0b0111101110110000,
        0b0101110010101011,
        0b0011100010001100,
        0b0011100110010001,
        0b0010000010010010,
        0b0001100000001100,
        0b0011100101010000,
        0b1000000010011000,
        0b1111000000000000,
    };
    workload.data = {1, 2, 3, 4, 1, 2, 3, 4};
    workload.threads = 4;
    workload.result_base = 8;
    workload.expected = {7, 10, 15, 22};
    return workload;
}

class TinyGpuTarget : public sc_core::sc_module {
public:
    tlm_utils::simple_target_socket<TinyGpuTarget> socket;

    SC_HAS_PROCESS(TinyGpuTarget);

    explicit TinyGpuTarget(sc_core::sc_module_name name)
        : sc_core::sc_module(name)
        , socket("socket")
    {
        socket.register_b_transport(this, &TinyGpuTarget::b_transport);
        reset();
    }

private:
    std::array<uint16_t, kProgramRows> program_{};
    std::array<uint8_t, kDataRows> data_{};
    uint32_t thread_count_ = 0;
    bool done_ = false;
    bool failed_ = false;

    void reset()
    {
        program_.fill(0);
        data_.fill(0);
        thread_count_ = 0;
        done_ = false;
        failed_ = false;
    }

    void b_transport(tlm::tlm_generic_payload& trans, sc_core::sc_time& delay)
    {
        const auto command = trans.get_command();
        const uint64_t address = trans.get_address();
        auto* bytes = trans.get_data_ptr();
        const auto length = trans.get_data_length();

        delay += sc_core::sc_time(10, sc_core::SC_NS);

        try {
            if (!bytes || length == 0) {
                throw std::runtime_error("empty TLM payload");
            }
            if (trans.get_byte_enable_ptr()) {
                trans.set_response_status(tlm::TLM_BYTE_ENABLE_ERROR_RESPONSE);
                return;
            }
            if (trans.get_streaming_width() < length) {
                trans.set_response_status(tlm::TLM_BURST_ERROR_RESPONSE);
                return;
            }
            if (command == tlm::TLM_WRITE_COMMAND) {
                write(address, bytes, length);
            } else if (command == tlm::TLM_READ_COMMAND) {
                read(address, bytes, length);
            } else {
                throw std::runtime_error("unsupported TLM command");
            }
            trans.set_response_status(tlm::TLM_OK_RESPONSE);
        } catch (const std::exception& error) {
            std::cerr << name() << ": " << error.what() << " at 0x" << std::hex << address << std::dec << "\n";
            trans.set_response_status(tlm::TLM_ADDRESS_ERROR_RESPONSE);
        }
    }

    static uint32_t load_le(const unsigned char* bytes, unsigned length)
    {
        uint32_t value = 0;
        for (unsigned i = 0; i < length; ++i) {
            value |= static_cast<uint32_t>(bytes[i]) << (8 * i);
        }
        return value;
    }

    static void store_le(unsigned char* bytes, unsigned length, uint32_t value)
    {
        for (unsigned i = 0; i < length; ++i) {
            bytes[i] = static_cast<unsigned char>((value >> (8 * i)) & 0xff);
        }
    }

    static bool in_window(uint64_t address, unsigned length, uint64_t base, unsigned size)
    {
        return length != 0 && address >= base && address - base < size
            && length <= size - (address - base);
    }

    void write(uint64_t address, const unsigned char* bytes, unsigned length)
    {
        if (address == kRegThreadCount && length == 4) {
            const uint32_t count = load_le(bytes, length);
            thread_count_ = 0;
            done_ = false;
            failed_ = true;
            if (count == 0 || count > 255) {
                throw std::runtime_error("thread count must be in 1..255");
            }
            thread_count_ = count;
            failed_ = false;
            return;
        }

        if (address == kRegStart && length == 4) {
            if (load_le(bytes, length) != 0) {
                done_ = false;
                failed_ = false;
                try {
                    run_kernel();
                    done_ = true;
                } catch (const std::exception& error) {
                    failed_ = true;
                    std::cerr << name() << ": kernel failed: " << error.what() << "\n";
                }
            }
            return;
        }

        if (in_window(address, length, kProgramBase, kProgramRows * sizeof(uint16_t))) {
            const auto offset = static_cast<unsigned>(address - kProgramBase);
            if ((offset % sizeof(uint16_t)) != 0 || length != sizeof(uint16_t)) {
                throw std::runtime_error("program memory expects aligned 16-bit writes");
            }
            program_[offset / sizeof(uint16_t)] = static_cast<uint16_t>(load_le(bytes, length));
            return;
        }

        if (in_window(address, length, kDataBase, kDataRows)) {
            std::memcpy(&data_[address - kDataBase], bytes, length);
            return;
        }

        throw std::runtime_error("write outside VP memory map");
    }

    void read(uint64_t address, unsigned char* bytes, unsigned length) const
    {
        if (address == kRegStatus && length == 4) {
            store_le(bytes, length, (done_ ? 1u : 0u) | (failed_ ? 2u : 0u));
            return;
        }

        if (in_window(address, length, kDataBase, kDataRows)) {
            std::memcpy(bytes, &data_[address - kDataBase], length);
            return;
        }

        throw std::runtime_error("read outside VP memory map");
    }

    uint8_t register_value(const std::array<uint8_t, 16>& regs, uint8_t index) const
    {
        return regs[index & 0xf];
    }

    void run_kernel()
    {
        if (thread_count_ == 0 || thread_count_ > 255) {
            throw std::runtime_error("thread count must be in 1..255");
        }
        for (uint32_t thread = 0; thread < thread_count_; ++thread) {
            run_thread(thread);
        }
    }

    void run_thread(uint32_t linear_thread)
    {
        std::array<uint8_t, 16> regs{};
        regs[13] = static_cast<uint8_t>(linear_thread / kThreadsPerBlock);
        regs[14] = static_cast<uint8_t>(kThreadsPerBlock);
        regs[15] = static_cast<uint8_t>(linear_thread % kThreadsPerBlock);

        uint8_t pc = 0;
        uint8_t nzp = 0;

        for (unsigned instructions = 0; instructions < 1024; ++instructions) {
            const uint16_t instruction = program_[pc];
            const auto opcode = static_cast<uint8_t>((instruction >> 12) & 0xf);
            const auto rd = static_cast<uint8_t>((instruction >> 8) & 0xf);
            const auto rs = static_cast<uint8_t>((instruction >> 4) & 0xf);
            const auto rt = static_cast<uint8_t>(instruction & 0xf);
            const auto imm = static_cast<uint8_t>(instruction & 0xff);
            const auto decoded_nzp = static_cast<uint8_t>((instruction >> 9) & 0x7);

            switch (opcode) {
            case kNop:
                ++pc;
                break;
            case kBranch:
                pc = ((nzp & decoded_nzp) != 0) ? imm : static_cast<uint8_t>(pc + 1);
                break;
            case kCmp: {
                const uint8_t diff = static_cast<uint8_t>(register_value(regs, rs) - register_value(regs, rt));
                // Match the RTL's unsigned 8-bit comparison behavior in src/alu.sv.
                constexpr bool negative = false;
                nzp = static_cast<uint8_t>(((diff > 0) << 2) | ((diff == 0) << 1) | negative);
                ++pc;
                break;
            }
            case kAdd:
                if (rd < 13) regs[rd] = static_cast<uint8_t>(register_value(regs, rs) + register_value(regs, rt));
                ++pc;
                break;
            case kSub:
                if (rd < 13) regs[rd] = static_cast<uint8_t>(register_value(regs, rs) - register_value(regs, rt));
                ++pc;
                break;
            case kMul:
                if (rd < 13) regs[rd] = static_cast<uint8_t>(register_value(regs, rs) * register_value(regs, rt));
                ++pc;
                break;
            case kDiv:
                if (rd < 13) {
                    if (register_value(regs, rt) == 0) {
                        throw std::runtime_error("division by zero has no defined RTL result");
                    }
                    regs[rd] = static_cast<uint8_t>(register_value(regs, rs) / register_value(regs, rt));
                }
                ++pc;
                break;
            case kLoad:
                if (rd < 13) regs[rd] = data_[register_value(regs, rs)];
                ++pc;
                break;
            case kStore:
                data_[register_value(regs, rs)] = register_value(regs, rt);
                ++pc;
                break;
            case kConst:
                if (rd < 13) regs[rd] = imm;
                ++pc;
                break;
            case kRet:
                return;
            default:
                throw std::runtime_error("unknown opcode");
            }
        }

        throw std::runtime_error("kernel did not terminate");
    }
};

class QBoxLikeDriver : public sc_core::sc_module {
public:
    tlm_utils::simple_initiator_socket<QBoxLikeDriver> socket;

    SC_HAS_PROCESS(QBoxLikeDriver);

    QBoxLikeDriver(sc_core::sc_module_name name, std::vector<Workload> workloads)
        : sc_core::sc_module(name)
        , socket("socket")
        , workloads_(std::move(workloads))
    {
        SC_THREAD(run);
    }

private:
    std::vector<Workload> workloads_;

    void run()
    {
        for (const auto& workload : workloads_) {
            run_workload(workload);
        }

        std::cout << "all VP workloads passed\n";
        sc_core::sc_stop();
    }

    void run_workload(const Workload& workload)
    {
        std::cout << "loading " << workload.name << " through qbox-like TLM initiator\n";

        for (unsigned i = 0; i < workload.program.size(); ++i) {
            write16(kProgramBase + i * sizeof(uint16_t), workload.program[i]);
        }


        for (unsigned i = 0; i < workload.data.size(); ++i) {
            write8(kDataBase + i, workload.data[i]);
        }

        write32(kRegThreadCount, workload.threads);
        write32(kRegStart, 1);

        bool completed = false;
        for (unsigned polls = 0; polls < 1000; ++polls) {
            const uint32_t status = read32(kRegStatus);
            if (status & 2u) {
                SC_REPORT_FATAL("tiny-gpu-vp", "kernel execution failed");
                return;
            }
            if (status & 1u) {
                completed = true;
                break;
            }
            wait(sc_core::sc_time(1, sc_core::SC_US));
        }
        if (!completed) {
            SC_REPORT_FATAL("tiny-gpu-vp", "kernel completion polling exceeded 1000 attempts");
            return;
        }

        for (unsigned i = 0; i < workload.expected.size(); ++i) {
            const auto got = read8(kDataBase + workload.result_base + i);
            const auto expected = workload.expected[i];
            if (got != expected) {
                std::ostringstream message;
                message << workload.name << " result mismatch at " << i << ": expected "
                        << static_cast<unsigned>(expected) << ", got " << static_cast<unsigned>(got);
                SC_REPORT_ERROR("tiny-gpu-vp", message.str().c_str());
            }
        }

        std::cout << workload.name << " passed";
        std::cout << " result=";
        for (unsigned i = 0; i < workload.expected.size(); ++i) {
            std::cout << (i == 0 ? "[" : ", ") << static_cast<unsigned>(read8(kDataBase + workload.result_base + i));
        }
        std::cout << "]\n";
    }

    void transport(tlm::tlm_command command, uint64_t address, unsigned char* data, unsigned length)
    {
        tlm::tlm_generic_payload payload;
        sc_core::sc_time delay = sc_core::SC_ZERO_TIME;

        payload.set_command(command);
        payload.set_address(address);
        payload.set_data_ptr(data);
        payload.set_data_length(length);
        payload.set_streaming_width(length);
        payload.set_byte_enable_ptr(nullptr);
        payload.set_dmi_allowed(false);
        payload.set_response_status(tlm::TLM_INCOMPLETE_RESPONSE);

        socket->b_transport(payload, delay);
        wait(delay);

        if (payload.is_response_error()) {
            SC_REPORT_ERROR("qbox-like-driver", payload.get_response_string().c_str());
        }
    }

    void write32(uint64_t address, uint32_t value)
    {
        unsigned char bytes[4] = {
            static_cast<unsigned char>(value & 0xff),
            static_cast<unsigned char>((value >> 8) & 0xff),
            static_cast<unsigned char>((value >> 16) & 0xff),
            static_cast<unsigned char>((value >> 24) & 0xff),
        };
        transport(tlm::TLM_WRITE_COMMAND, address, bytes, sizeof(bytes));
    }

    void write16(uint64_t address, uint16_t value)
    {
        unsigned char bytes[2] = {
            static_cast<unsigned char>(value & 0xff),
            static_cast<unsigned char>((value >> 8) & 0xff),
        };
        transport(tlm::TLM_WRITE_COMMAND, address, bytes, sizeof(bytes));
    }

    void write8(uint64_t address, uint8_t value)
    {
        unsigned char byte = value;
        transport(tlm::TLM_WRITE_COMMAND, address, &byte, sizeof(byte));
    }

    uint32_t read32(uint64_t address)
    {
        unsigned char bytes[4] = {};
        transport(tlm::TLM_READ_COMMAND, address, bytes, sizeof(bytes));
        return static_cast<uint32_t>(bytes[0]) | (static_cast<uint32_t>(bytes[1]) << 8)
            | (static_cast<uint32_t>(bytes[2]) << 16) | (static_cast<uint32_t>(bytes[3]) << 24);
    }

    uint8_t read8(uint64_t address)
    {
        unsigned char byte = 0;
        transport(tlm::TLM_READ_COMMAND, address, &byte, sizeof(byte));
        return byte;
    }
};

} // namespace vp

#ifndef TINY_GPU_MODEL_TEST
int sc_main(int argc, char* argv[])
{
    std::vector<vp::Workload> workloads;

    if (argc == 1 || std::string(argv[1]) == "all") {
        workloads.push_back(vp::matadd_workload());
        workloads.push_back(vp::matmul_workload());
    } else if (std::string(argv[1]) == "matadd") {
        workloads.push_back(vp::matadd_workload());
    } else if (std::string(argv[1]) == "matmul") {
        workloads.push_back(vp::matmul_workload());
    } else {
        std::cerr << "usage: " << argv[0] << " [all|matadd|matmul]\n";
        return 1;
    }

    vp::QBoxLikeDriver qbox("qbox", workloads);
    vp::TinyGpuTarget gpu("tiny_gpu");
    qbox.socket.bind(gpu.socket);

    sc_core::sc_start();
    return 0;
}

#endif // TINY_GPU_MODEL_TEST
