#include "SimpleCPU/simpleCPU.h"
#include "SimpleCPU/IRQ.h"
#include "SimpleMemory/simpleMemory.h"

#include "greencontrol/config.h"
#include "greencontrol/config_api_lua_file_parser.h"
#include "greenrouter/genericRouter.h"
#include "greenrouter/protocol/SimpleBus/simpleBusProtocol.h"
#include "greenrouter/scheduler/fixedPriorityScheduler.h"
#include "greensignalsocket/green_signal.h"

#include <array>
#include <cstdint>
#include <cstdlib>
#include <cstring>
#include <iostream>
#include <sstream>
#include <stdexcept>
#include <string>

namespace {

const uint32_t kRegThreadCount = 0x0000;
const uint32_t kRegStart = 0x0004;
const uint32_t kRegStatus = 0x0008;
const uint32_t kProgramBase = 0x1000;
const uint32_t kDataBase = 0x2000;

const unsigned kProgramRows = 256;
const unsigned kDataRows = 256;
const unsigned kThreadsPerBlock = 4;

enum Opcode {
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

uint32_t load_le(const uint8_t* bytes, size_t length)
{
    uint32_t value = 0;
    for (size_t i = 0; i < length && i < sizeof(value); ++i) {
        value |= static_cast<uint32_t>(bytes[i]) << (8 * i);
    }
    return value;
}

void store_le(uint8_t* bytes, size_t length, uint32_t value)
{
    for (size_t i = 0; i < length; ++i) {
        bytes[i] = static_cast<uint8_t>((value >> (8 * i)) & 0xff);
    }
}

class TinyGpuQboxTarget:
    public sc_core::sc_module,
    public gs::tlm_b_if<gs::gp::GenericSlaveAccessHandle>
{
public:
    SC_HAS_PROCESS(TinyGpuQboxTarget);

    explicit TinyGpuQboxTarget(sc_core::sc_module_name name):
        sc_core::sc_module(name),
        target_port("target_port"),
        irq_socket("irq_socket"),
        irq_number_("irq_number", 176),
        size_("size", 0x10000)
    {
        target_port.bind_b_if(*this);

        irq_payload_.set_data_ptr(reinterpret_cast<unsigned char*>(&irq_data_));
        gs::socket::config<gs_generic_signal::gs_generic_signal_protocol_types> config;
        config.use_mandatory_extension<IRQ_LINE_EXTENSION>();
        irq_socket.set_config(config);

        SC_THREAD(irq_thread);
    }

    gs::gp::GenericSlavePort<32> target_port;
    gs_generic_signal::initiator_signal_socket irq_socket;

    void b_transact(gs::gp::GenericSlaveAccessHandle ah)
    {
        accessHandle txn = _getSlaveAccessHandle(ah);
        const uint64_t address = txn->getMAddr();
        const uint64_t offset = address - target_port.base_addr;
        const size_t length = txn->getMBurstLength();

        try {
            tlm::tlm_generic_payload* payload = txn->get_tlm_transaction();
            if (address < target_port.base_addr || offset >= uint64_t(size_) ||
                length == 0 || length > uint64_t(size_) - offset ||
                !payload->get_data_ptr() || length > payload->get_data_length()) {
                throw std::runtime_error("invalid target address or payload length");
            }
            // The legacy Generic API leaves streaming_width at its default 0
            // for contiguous bursts. Explicit nonzero wrapping is unsupported.
            if (payload->get_byte_enable_ptr() || (payload->get_streaming_width() != 0 &&
                                                   payload->get_streaming_width() < length)) {
                throw std::runtime_error("byte enables and streaming bursts are unsupported");
            }
            if (txn->getMCmd() == gs::Generic_MCMD_WR) {
                write(offset, reinterpret_cast<const uint8_t*>(&(txn->getMData()[0])), length);
            } else if (txn->getMCmd() == gs::Generic_MCMD_RD) {
                std::array<uint8_t, 8> buffer;
                buffer.fill(0);
                if (length > buffer.size()) {
                    throw std::runtime_error("read larger than target buffer");
                }
                read(offset, buffer.data(), length);
                gs::GSDataType::dtype data(buffer.data(), length);
                gs::MData mdata(data);
                txn->setSData(mdata);
            } else {
                throw std::runtime_error("unsupported command");
            }

            txn->setSResp(gs::Generic_SRESP_DVA);
        } catch (const std::exception& error) {
            std::cerr << name() << ": " << error.what() << " at offset 0x"
                      << std::hex << offset << std::dec << std::endl;
            txn->setSResp(gs::Generic_SRESP_ERR);
        }
    }

private:
    typedef gs::gp::GenericSlavePort<32>::accessHandle accessHandle;
    typedef gs_generic_signal::gs_generic_signal_payload irqPayload;

    irqPayload irq_payload_;
    IRQ_ext_data irq_data_;
    gs::gs_param<uint32_t> irq_number_;
    gs::gs_param<uint32_t> size_;
    std::array<uint16_t, kProgramRows> program_{};
    std::array<uint8_t, kDataRows> data_{};
    sc_core::sc_event irq_event_;
    uint32_t thread_count_ = 0;
    bool done_ = false;
    bool failed_ = false;
    bool irq_pending_ = false;

    static bool in_window(uint64_t offset, size_t length, uint64_t base, size_t size)
    {
        return length != 0 && offset >= base && offset - base < size
            && length <= size - (offset - base);
    }

    void write(uint64_t offset, const uint8_t* bytes, size_t length)
    {
        if (offset == kRegThreadCount && length == 4) {
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

        if (offset == kRegStart && length == 4) {
            if (load_le(bytes, length) != 0) {
                done_ = false;
                failed_ = false;
                try {
                    run_kernel();
                    done_ = true;
                } catch (const std::exception& error) {
                    failed_ = true;
                    std::cerr << name() << ": kernel failed: " << error.what() << std::endl;
                }
                raise_irq();
            }
            return;
        }

        if (in_window(offset, length, kProgramBase, kProgramRows * sizeof(uint16_t))) {
            const uint32_t program_offset = offset - kProgramBase;
            if ((program_offset % sizeof(uint16_t)) != 0 || length % sizeof(uint16_t) != 0) {
                throw std::runtime_error("program writes require aligned complete 16-bit instructions");
            }

            for (size_t i = 0; i < length; i += sizeof(uint16_t)) {
                program_[(program_offset + i) / sizeof(uint16_t)] =
                    static_cast<uint16_t>(load_le(bytes + i, sizeof(uint16_t)));
            }
            return;
        }

        if (in_window(offset, length, kDataBase, kDataRows)) {
            std::memcpy(&data_[offset - kDataBase], bytes, length);
            return;
        }

        throw std::runtime_error("write outside tiny-gpu MMIO map");
    }

    void read(uint64_t offset, uint8_t* bytes, size_t length) const
    {
        if (offset == kRegStatus && length == 4) {
            store_le(bytes, length, (done_ ? 1u : 0u) | (failed_ ? 2u : 0u));
            return;
        }

        if (in_window(offset, length, kDataBase, kDataRows)) {
            std::memcpy(bytes, &data_[offset - kDataBase], length);
            return;
        }

        throw std::runtime_error("read outside tiny-gpu MMIO map");
    }

    static uint8_t reg_value(const std::array<uint8_t, 16>& regs, uint8_t index)
    {
        return regs[index & 0xf];
    }

    void run_kernel()
    {
        if (thread_count_ == 0 || thread_count_ > 255) {
            throw std::runtime_error("thread count must be in 1..255");
        }
        std::cout << name() << ": launching " << thread_count_ << " threads" << std::endl;
        for (uint32_t thread = 0; thread < thread_count_; ++thread) {
            run_thread(thread);
        }
    }

    void run_thread(uint32_t linear_thread)
    {
        std::array<uint8_t, 16> regs;
        regs.fill(0);
        regs[13] = static_cast<uint8_t>(linear_thread / kThreadsPerBlock);
        regs[14] = static_cast<uint8_t>(kThreadsPerBlock);
        regs[15] = static_cast<uint8_t>(linear_thread % kThreadsPerBlock);

        uint8_t pc = 0;
        uint8_t nzp = 0;

        for (unsigned count = 0; count < 1024; ++count) {
            const uint16_t instruction = program_[pc];
            const uint8_t opcode = static_cast<uint8_t>((instruction >> 12) & 0xf);
            const uint8_t rd = static_cast<uint8_t>((instruction >> 8) & 0xf);
            const uint8_t rs = static_cast<uint8_t>((instruction >> 4) & 0xf);
            const uint8_t rt = static_cast<uint8_t>(instruction & 0xf);
            const uint8_t imm = static_cast<uint8_t>(instruction & 0xff);
            const uint8_t decoded_nzp = static_cast<uint8_t>((instruction >> 9) & 0x7);

            switch (opcode) {
            case kNop:
                ++pc;
                break;
            case kBranch:
                pc = ((nzp & decoded_nzp) != 0) ? imm : static_cast<uint8_t>(pc + 1);
                break;
            case kCmp: {
                const uint8_t diff = static_cast<uint8_t>(reg_value(regs, rs) - reg_value(regs, rt));
                nzp = static_cast<uint8_t>(((diff > 0) << 2) | ((diff == 0) << 1));
                ++pc;
                break;
            }
            case kAdd:
                if (rd < 13) regs[rd] = static_cast<uint8_t>(reg_value(regs, rs) + reg_value(regs, rt));
                ++pc;
                break;
            case kSub:
                if (rd < 13) regs[rd] = static_cast<uint8_t>(reg_value(regs, rs) - reg_value(regs, rt));
                ++pc;
                break;
            case kMul:
                if (rd < 13) regs[rd] = static_cast<uint8_t>(reg_value(regs, rs) * reg_value(regs, rt));
                ++pc;
                break;
            case kDiv:
                if (rd < 13) {
                    if (reg_value(regs, rt) == 0) {
                        throw std::runtime_error("division by zero has no defined RTL result");
                    }
                    regs[rd] = static_cast<uint8_t>(reg_value(regs, rs) / reg_value(regs, rt));
                }
                ++pc;
                break;
            case kLoad:
                if (rd < 13) regs[rd] = data_[reg_value(regs, rs)];
                ++pc;
                break;
            case kStore:
                data_[reg_value(regs, rs)] = reg_value(regs, rt);
                ++pc;
                break;
            case kConst:
                if (rd < 13) regs[rd] = imm;
                ++pc;
                break;
            case kRet:
                return;
            default:
                throw std::runtime_error("unknown tiny-gpu opcode");
            }
        }

        throw std::runtime_error("tiny-gpu thread did not terminate");
    }

    void raise_irq()
    {
        irq_pending_ = true;
        irq_event_.notify(sc_core::SC_ZERO_TIME);
    }

    void irq_thread()
    {
        sc_core::sc_time delay = sc_core::SC_ZERO_TIME;

        while (true) {
            wait(irq_event_);
            if (!irq_pending_) {
                continue;
            }

            irq_pending_ = false;
            irq_data_.irq_line = irq_number_;
            irq_data_.value = 1;
            irq_socket.validate_extension<IRQ_LINE_EXTENSION>(irq_payload_);
            irq_socket->b_transport(irq_payload_, delay);

            irq_data_.value = 0;
            irq_socket.validate_extension<IRQ_LINE_EXTENSION>(irq_payload_);
            irq_socket->b_transport(irq_payload_, delay);
        }
    }
};

void show_usage(const char* name)
{
    std::cerr << "Usage: " << name << " -c CONFIGURATION_FILE\n";
}

std::string parse_config_path(int argc, char** argv)
{
    for (int i = 1; i < argc; ++i) {
        const std::string arg = argv[i];
        if (arg == "-h" || arg == "--help") {
            show_usage(argv[0]);
            std::exit(EXIT_SUCCESS);
        }
        if (arg == "-c" || arg == "--conf") {
            if (i + 1 >= argc) {
                show_usage(argv[0]);
                std::exit(EXIT_FAILURE);
            }
            return argv[++i];
        }
    }
    return "vp/qbox/conf/aarch64_tiny_gpu.lua";
}

} // namespace

#ifndef TINY_GPU_MODEL_TEST
int sc_main(int argc, char** argv)
{
    const std::string config_path = parse_config_path(argc, argv);

    gs::cnf::LuaFile_Tool lua_reader("lua_reader");
    if (lua_reader.config(config_path.c_str()) != 0) {
        show_usage(argv[0]);
        return EXIT_FAILURE;
    }

    SimpleCPU* cpu = new SimpleCPU("CPU");
    Memory<32>* ram = new Memory<32>("ram");
    TinyGpuQboxTarget* tiny_gpu = new TinyGpuQboxTarget("tiny_gpu");

    gs::gp::SimpleBusProtocol<32>* protocol = new gs::gp::SimpleBusProtocol<32>("protocol", 10);
    gs::gp::fixedPriorityScheduler* scheduler = new gs::gp::fixedPriorityScheduler("scheduler");
    gs::gp::GenericRouter<32>* router = new gs::gp::GenericRouter<32>("router");

    protocol->router_port(*router);
    protocol->scheduler_port(*scheduler);
    router->protocol_port(*protocol);

    cpu->master_socket(router->target_socket);
    tiny_gpu->irq_socket(cpu->irq_socket);
    router->init_socket(ram->target_port);
    router->init_socket(tiny_gpu->target_port);

    sc_core::sc_start();
    return EXIT_SUCCESS;
}
#endif // TINY_GPU_MODEL_TEST
