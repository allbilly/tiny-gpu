local defaults = TINYGPU_BUILD_DEFAULTS or {}
TINYGPU_BUILD_DEFAULTS = nil
local function setting(name, fallback)
    return os.getenv(name) or defaults[name] or fallback
end
local function fail(message)
    io.stderr:write(message .. "\n")
    os.exit(1)
end
local function argument_path(name, value)
    -- This legacy QBox bridge tokenizes on spaces, without shell quoting.
    if not value or value == "" or value:find("[%s,\"']") then
        fail(name .. " must be a path without whitespace, commas, or quotes")
    end
    return value
end
local source_dir = debug.getinfo(1, "S").source:match("^@(.*)/[^/]*$") or "."
local repo = argument_path("TINYGPU_REPO_ROOT", setting("TINYGPU_REPO_ROOT", source_dir .. "/../../.."))
local vp_root = setting("QBOX_VP_ROOT", repo .. "/../nvdla/ref/vp")
local library = setting("QBOX_LIBRARY", vp_root .. "/libs/qbox.build/aarch64-softmmu/libqbox-nvdla.so")
local kernel = argument_path("KERNEL_IMAGE", setting("KERNEL_IMAGE", vp_root .. "/../../examples/vp/Image"))
local rootfs = argument_path("ROOTFS (a private copy is required)", setting("ROOTFS"))
local share = argument_path("SHARE_ROOT", setting("SHARE_ROOT", repo))
local port = tonumber(setting("SSH_PORT", "6677"))
if not port or port % 1 ~= 0 or port < 1 or port > 65535 then
    fail("SSH_PORT must be between 1 and 65535")
end
for name, path in pairs({QBOX_LIBRARY = library, KERNEL_IMAGE = kernel, ROOTFS = rootfs}) do
    local handle = io.open(path, "rb")
    if not handle then fail(name .. " is not readable: " .. path) end
    handle:close()
end
CPU = {
    library = library,
    extra_arguments = "-machine virt -cpu cortex-a57 -nographic -smp 1 -m 1024 -kernel " .. kernel ..
        " -append root=/dev/vda -drive file=" .. rootfs .. ",if=none,format=raw,id=hd0" ..
        " -device virtio-blk-device,drive=hd0 -fsdev local,id=r,path=" .. share ..
        ",security_model=none,readonly=on -device virtio-9p-device,fsdev=r,mount_tag=r" ..
        " -netdev user,id=user0,hostfwd=tcp:127.0.0.1:" .. port .. "-:22 -device virtio-net-device,netdev=user0"
}
ram = {
    -- SimpleMemory's size is in KiB.
    size = 1048576,
    target_port = { base_addr = 0xc0000000, high_addr = 0xffffffff }
}
tiny_gpu = {
    irq_number = 176,
    size = 65536,
    target_port = { base_addr = 0x10200000, high_addr = 0x1020ffff }
}
