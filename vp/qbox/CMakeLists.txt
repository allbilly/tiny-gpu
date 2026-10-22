cmake_minimum_required(VERSION 3.16)
project(tiny_gpu_qbox_vp LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 11)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS ON)

get_filename_component(TINYGPU_REPO_ROOT "${CMAKE_CURRENT_SOURCE_DIR}/../.." ABSOLUTE)
set(QBOX_VP_ROOT "$ENV{QBOX_VP_ROOT}" CACHE PATH "Path to a built VP tree that provides SimpleCPU/QBox")
if(NOT QBOX_VP_ROOT)
    get_filename_component(QBOX_VP_DEFAULT "${TINYGPU_REPO_ROOT}/../nvdla/ref/vp" ABSOLUTE)
    set(QBOX_VP_ROOT "${QBOX_VP_DEFAULT}" CACHE PATH "Path to a built VP tree that provides SimpleCPU/QBox" FORCE)
endif()

if(NOT EXISTS "${QBOX_VP_ROOT}/models/cpu/include/SimpleCPU/simpleCPU.h")
    message(FATAL_ERROR "QBOX_VP_ROOT does not point to a built VP tree with SimpleCPU/QBox: ${QBOX_VP_ROOT}")
endif()

set(QBOX_LIBRARY_DEFAULT "$ENV{QBOX_LIBRARY}")
if(NOT QBOX_LIBRARY_DEFAULT)
    set(QBOX_LIBRARY_DEFAULT "${QBOX_VP_ROOT}/libs/qbox.build/aarch64-softmmu/libqbox-nvdla.so")
endif()
set(QBOX_LIBRARY "${QBOX_LIBRARY_DEFAULT}" CACHE FILEPATH "QBox shared library to load/link")
if(NOT EXISTS "${QBOX_LIBRARY}")
    message(FATAL_ERROR "QBOX_LIBRARY not found: ${QBOX_LIBRARY}")
endif()

find_path(SYSTEMC_INCLUDE_DIR
    NAMES systemc.h
    HINTS ENV SYSTEMC_HOME
    PATHS /usr/local/systemc-2.3.0 /home/linuxbrew/.linuxbrew/opt/systemc /opt/homebrew/opt/systemc /usr/local/opt/systemc
    PATH_SUFFIXES include
)
find_library(SYSTEMC_LIBRARY
    NAMES systemc libsystemc
    HINTS ENV SYSTEMC_HOME
    PATHS /usr/local/systemc-2.3.0 /home/linuxbrew/.linuxbrew/opt/systemc /opt/homebrew/opt/systemc /usr/local/opt/systemc
    PATH_SUFFIXES lib lib-linux64 lib-macosx64
)
if(NOT SYSTEMC_INCLUDE_DIR OR NOT SYSTEMC_LIBRARY)
    message(FATAL_ERROR "SystemC not found. Install SystemC or set SYSTEMC_HOME.")
endif()

find_package(Lua REQUIRED)

find_library(BZIP2_LIBRARY
    NAMES bz2 libbz2
    PATHS /home/linuxbrew/.linuxbrew/opt/bzip2 /opt/homebrew/opt/bzip2 /usr/local/opt/bzip2
    PATH_SUFFIXES lib
)
if(NOT BZIP2_LIBRARY)
    message(FATAL_ERROR "bzip2 library not found")
endif()

# Some prebuilt QBox libraries use libjpeg ABI 8 instead of the host default.
# Link it explicitly when available so RUNPATH resolves this direct dependency.
find_library(QBOX_JPEG8_LIBRARY
    NAMES libjpeg.so.8
    HINTS ENV QBOX_DEPS_PREFIX
    PATHS /home/linuxbrew/.linuxbrew/opt/jpeg-turbo /opt/homebrew/opt/jpeg-turbo /usr/local/opt/jpeg-turbo
    PATH_SUFFIXES lib
)
set(QBOX_EXTRA_LIBRARIES "")
if(QBOX_JPEG8_LIBRARY)
    list(APPEND QBOX_EXTRA_LIBRARIES "${QBOX_JPEG8_LIBRARY}")
endif()

set(GREENLIB_INCLUDE_DIRS
    ${QBOX_VP_ROOT}/libs/greenlib/greencontrol/include
    ${QBOX_VP_ROOT}/libs/greenlib/greenmemory/include
    ${QBOX_VP_ROOT}/libs/greenlib/greenscript/include
    ${QBOX_VP_ROOT}/libs/greenlib/greensignalbus/include
    ${QBOX_VP_ROOT}/libs/greenlib/greensocket/include
    ${QBOX_VP_ROOT}/libs/greenlib/greenmessage/include
    ${QBOX_VP_ROOT}/libs/greenlib/greenrouter/include
    ${QBOX_VP_ROOT}/libs/greenlib/greenserialsocket/include
    ${QBOX_VP_ROOT}/libs/greenlib/greensignalsocket/include
    ${QBOX_VP_ROOT}/libs/greenlib/gsgpsocket/include
    ${QBOX_VP_ROOT}/libs/greenlib/greenreg/include
    ${QBOX_VP_ROOT}/libs/greenlib/include
)

add_executable(tiny-gpu-qbox-vp
    src/tiny_gpu_qbox_toplevel.cpp
)

target_compile_definitions(tiny-gpu-qbox-vp PRIVATE
    SC_INCLUDE_DYNAMIC_PROCESSES
    AWS_FPGA_PRESENT=0
)

target_compile_options(tiny-gpu-qbox-vp PRIVATE
    -Wall
    -fpermissive
    -Wno-deprecated-declarations
    -Wno-deprecated
    -Wno-register
    -Wno-overloaded-virtual
)

target_include_directories(tiny-gpu-qbox-vp PRIVATE
    ${SYSTEMC_INCLUDE_DIR}
    ${LUA_INCLUDE_DIR}
    ${QBOX_VP_ROOT}/models/cpu/include
    ${QBOX_VP_ROOT}/models/memory/include
    ${QBOX_VP_ROOT}/libs/tlm2c/include
    ${QBOX_VP_ROOT}/libs/tlm2c.build/include
    ${QBOX_VP_ROOT}/libs/log/include
    ${QBOX_VP_ROOT}/libs/log.build/include
    ${GREENLIB_INCLUDE_DIRS}
)

target_link_libraries(tiny-gpu-qbox-vp PRIVATE
    ${SYSTEMC_LIBRARY}
    ${LUA_LIBRARIES}
    ${QBOX_LIBRARY}
    ${QBOX_VP_ROOT}/models/cpu.build/libsimplecpu.so
    ${QBOX_VP_ROOT}/libs/tlm2c.build/lib/libtlm2c.a
    ${QBOX_VP_ROOT}/libs/log.build/lib/liblog.so
    ${QBOX_VP_ROOT}/libs/greenlib/greenreg/lib/libgreenreg.a
    ${QBOX_VP_ROOT}/libs/greenlib/greenscript/lib/libgreenscript.a
    ${BZIP2_LIBRARY}
    ${QBOX_EXTRA_LIBRARIES}
    dl
    pthread
)

get_filename_component(SYSTEMC_LIBRARY_DIR "${SYSTEMC_LIBRARY}" DIRECTORY)
get_filename_component(QBOX_LIBRARY_DIR "${QBOX_LIBRARY}" DIRECTORY)
get_filename_component(BZIP2_LIBRARY_DIR "${BZIP2_LIBRARY}" DIRECTORY)
set_target_properties(tiny-gpu-qbox-vp PROPERTIES
    BUILD_RPATH "${SYSTEMC_LIBRARY_DIR};${QBOX_LIBRARY_DIR};${BZIP2_LIBRARY_DIR};${QBOX_VP_ROOT}/models/cpu.build;${QBOX_VP_ROOT}/libs/log.build/lib"
)

# Keep runtime library selection identical to the configured link dependency.
configure_file(conf/aarch64_tiny_gpu_build.lua.in aarch64_tiny_gpu.lua @ONLY)

include(CTest)
if(BUILD_TESTING)
    add_executable(tiny-gpu-qbox-transport-regression ../tests/qbox_transport_regression.cpp)
    foreach(property COMPILE_DEFINITIONS COMPILE_OPTIONS INCLUDE_DIRECTORIES LINK_LIBRARIES BUILD_RPATH)
        get_target_property(value tiny-gpu-qbox-vp ${property})
        set_target_properties(tiny-gpu-qbox-transport-regression PROPERTIES ${property} "${value}")
    endforeach()
    add_test(NAME qbox-transport-regression COMMAND tiny-gpu-qbox-transport-regression)
endif()
