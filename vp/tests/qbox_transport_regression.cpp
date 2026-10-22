#define TINY_GPU_MODEL_TEST
#include "../qbox/src/tiny_gpu_qbox_toplevel.cpp"
#include <limits>

int sc_main(int, char**)
{
    struct Owner : sc_core::sc_module {
        TinyGpuQboxTarget gpu;
        gs::gp::GenericMasterBlockingPort<32> master;
        explicit Owner(sc_core::sc_module_name name)
            : sc_core::sc_module(name), gpu("gpu"), master("master")
        {
            master(gpu.target_port);
        }
    } owner("owner");
    TinyGpuQboxTarget& gpu = owner.gpu;
    gs::gp::GenericMasterBlockingPort<32>& master = owner.master;
    auto require = [](bool condition, const char* message) {
        if (!condition) throw std::runtime_error(message);
    };
    unsigned char bytes[8] = {1};
    tlm::tlm_generic_payload payload;
    gs::gp::GenericMasterAccess transaction(&master, &payload);
    // Mirror SimpleCPU::memory_bt's Generic API sequence. In particular it
    // does not set streaming_width, whose default zero means contiguous.
    transaction.setMBurstLength(4);
    transaction.setMAddr(gpu.target_port.base_addr.getValue());
    gs::GSDataType::dtype data(bytes, 4);
    transaction.setMData(data);
    transaction.setMCmd(gs::Generic_MCMD_WR);
    require(payload.get_streaming_width() == 0, "Generic API changed its default streaming width");
    gs::gp::GenericSlaveAccessHandle access(&gpu.target_port, &payload);
    gpu.b_transact(access);
    require(payload.get_response_status() == tlm::TLM_OK_RESPONSE, "legacy Generic count write rejected");

    auto rejected = [&]() {
        payload.set_response_status(tlm::TLM_INCOMPLETE_RESPONSE);
        gpu.b_transact(access);
        require(payload.is_response_error(), "malformed Generic access accepted");
    };
    payload.set_streaming_width(2);
    rejected();
    payload.set_streaming_width(0);
    payload.set_byte_enable_ptr(bytes);
    rejected();
    payload.set_byte_enable_ptr(nullptr);
    payload.set_address(std::numeric_limits<uint64_t>::max());
    rejected();
    payload.set_address(uint64_t(gpu.target_port.base_addr) + (uint64_t(1) << 32));
    rejected(); // Must not alias register zero through truncation.
    payload.set_address(uint64_t(gpu.target_port.base_addr) + kRegStatus);
    payload.set_command(tlm::TLM_READ_COMMAND);
    payload.set_data_length(8);
    rejected();
    payload.set_data_length(4);
    payload.set_data_ptr(nullptr);
    rejected();
    std::cout << "PASS QBox Generic transport: legacy contiguous access and malformed request rejection\n";
    return 0;
}
