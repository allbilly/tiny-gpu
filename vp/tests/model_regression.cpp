#define TINY_GPU_MODEL_TEST
#ifndef TINY_GPU_QBOX_EXTRACTED_TEST
#include "../src/tiny_gpu_vp.cpp"
#else
#include "qbox_model_under_test.h"
#endif
#include <limits>

// The same behavioral checks also run against the QBox model's extracted
// memory/ISA methods; its GreenLib transport still needs QBox integration.
#ifndef TINY_GPU_QBOX_EXTRACTED_TEST
class Harness : public sc_core::sc_module {
public:
    tlm_utils::simple_initiator_socket<Harness> socket;
    SC_HAS_PROCESS(Harness);
    explicit Harness(sc_core::sc_module_name name) : sc_core::sc_module(name), socket("socket")
    {
        SC_THREAD(run);
    }
    bool transfer(bool write, uint64_t address, unsigned char* bytes, unsigned length,
                  unsigned streaming = 0, unsigned char* enables = nullptr)
    {
        tlm::tlm_generic_payload payload;
        payload.set_command(write ? tlm::TLM_WRITE_COMMAND : tlm::TLM_READ_COMMAND);
        payload.set_address(address);
        payload.set_data_ptr(bytes);
        payload.set_data_length(length);
        payload.set_streaming_width(streaming ? streaming : length);
        payload.set_byte_enable_ptr(enables);
        payload.set_byte_enable_length(enables ? 1 : 0);
        sc_core::sc_time delay = sc_core::SC_ZERO_TIME;
        socket->b_transport(payload, delay);
        return !payload.is_response_error();
    }
#else
class Harness {
public:
    ExtractedQboxTarget target;
    bool transfer(bool write, uint64_t address, unsigned char* bytes, unsigned length,
                  unsigned = 0, unsigned char* = nullptr)
    {
        try {
            if (write) target.write(address, bytes, length);
            else target.read(address, bytes, length);
            return true;
        } catch (const std::exception&) {
            return false;
        }
    }
#endif
    static void require(bool condition, const char* message)
    {
        if (!condition) throw std::runtime_error(message);
    }
    bool write(uint64_t address, uint32_t value, unsigned length = 4)
    {
        unsigned char bytes[4] = {static_cast<unsigned char>(value),
            static_cast<unsigned char>(value >> 8), static_cast<unsigned char>(value >> 16),
            static_cast<unsigned char>(value >> 24)};
        return transfer(true, address, bytes, length);
    }
    uint32_t read(uint64_t address, unsigned length = 4)
    {
        unsigned char bytes[4] = {};
        require(transfer(false, address, bytes, length), "valid read rejected");
        return uint32_t(bytes[0]) | uint32_t(bytes[1]) << 8 | uint32_t(bytes[2]) << 16 | uint32_t(bytes[3]) << 24;
    }
    void load(std::initializer_list<uint16_t> program)
    {
        uint64_t address = 0x1000;
        for (auto instruction : program) {
            require(write(address, instruction, 2), "program upload failed");
            address += 2;
        }
    }
    void launch(unsigned threads, uint32_t expected_status)
    {
        require(write(0, threads), "valid thread count rejected");
        require(write(4, 1), "launch transport failed");
        require(read(8) == expected_status, "unexpected completion status");
    }
    void run()
    {
        load({0x6000, 0xf000});
        launch(1, 2); // A zero divisor reports failure instead of crashing the host.
        load({0xf000});
        launch(1, 1); // The next launch clears a previous fault.
        launch(255, 1);
        load({0xa000, 0xf000});
        launch(1, 2);
        load({0x9000, 0x2000, 0x1400});
        launch(1, 2); // Instruction-budget failure is also visible to the guest.

        // Every opcode that can write rd must preserve all reserved registers.
        for (unsigned opcode : {3u, 4u, 5u, 6u, 7u, 9u}) {
            for (unsigned reserved = 13; reserved <= 15; ++reserved) {
                for (unsigned threads : {2u, 5u}) {
                    const uint16_t operation = (opcode << 12) | (reserved << 8) | 0x21;
                    load({0x9020, 0x9101, 0x9202, operation,
                          static_cast<uint16_t>(0x8000 | reserved), 0xf000});
                    require(write(0x2002, 0x33, 1), "fixture write failed");
                    launch(threads, 1);
                    const unsigned expected = reserved == 13 ? (threads - 1) / 4
                        : reserved == 14 ? 4 : (threads - 1) % 4;
                    require(read(0x2020, 1) == expected, "reserved register was overwritten");
                }
            }
        }
        // Invalid configuration must invalidate the old count, even if the
        // caller ignores the bus error and launches anyway.
        load({0x9020, 0x915a, 0x8001, 0xf000});
        for (uint32_t invalid : {0u, 256u, std::numeric_limits<uint32_t>::max()}) {
            require(write(0x2020, 0, 1) && write(0, 1), "fixture setup failed");
            require(!write(0, invalid), "invalid thread count accepted");
            require(write(4, 1), "invalid-count launch did not return status");
            require(read(8) == 2 && read(0x2020, 1) == 0, "invalid count executed stale threads");
        }
        unsigned char bytes[8] = {};
        require(!transfer(false, 8, bytes, 8), "64-bit control read accepted");
        require(!transfer(true, 0, bytes, 8), "64-bit control write accepted");
        require(!transfer(true, 0x1001, bytes, 2), "unaligned program write accepted");
        require(!transfer(true, 0x1000, bytes, 1), "partial instruction accepted");
        require(!transfer(true, 0x2000, bytes, 0), "empty data write accepted");
        require(!transfer(false, 0x20ff, bytes, 2), "cross-boundary read accepted");
        require(!transfer(true, 0x20ff, bytes, 2), "cross-boundary write accepted");
        require(!transfer(false, std::numeric_limits<uint64_t>::max(), bytes, 2), "overflow read accepted");
        require(!transfer(true, std::numeric_limits<uint64_t>::max(), bytes, 2), "overflow write accepted");
#ifndef TINY_GPU_QBOX_EXTRACTED_TEST
        require(!transfer(false, 8, nullptr, 4), "null payload accepted");
        require(!transfer(true, 0x2000, bytes, 4, 2), "streaming write accepted");
        require(!transfer(true, 0x2000, bytes, 1, 1, bytes), "byte-enable write accepted");
#endif
        std::cout << "PASS model regression: faults/recovery, thread bounds, reserved registers, malformed accesses\n";
#ifndef TINY_GPU_QBOX_EXTRACTED_TEST
        sc_core::sc_stop();
#endif
    }
};

#ifndef TINY_GPU_QBOX_EXTRACTED_TEST
int sc_main(int, char**)
{
    vp::TinyGpuTarget gpu("gpu");
    Harness harness("harness");
    harness.socket.bind(gpu.socket);
    sc_core::sc_start();
    return 0;
}
#else
int main()
{
    Harness harness;
    harness.run();
}
#endif
