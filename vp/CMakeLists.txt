cmake_minimum_required(VERSION 3.16)
project(tiny_gpu_vp LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)

find_package(SystemCLanguage QUIET)

if(NOT SystemCLanguage_FOUND)
    find_path(SYSTEMC_INCLUDE_DIR
        NAMES systemc
        HINTS ENV SYSTEMC_HOME
        PATHS /home/linuxbrew/.linuxbrew/opt/systemc /opt/homebrew/opt/systemc /usr/local/opt/systemc
        PATH_SUFFIXES include
    )
    find_library(SYSTEMC_LIBRARY
        NAMES systemc libsystemc
        HINTS ENV SYSTEMC_HOME
        PATHS /home/linuxbrew/.linuxbrew/opt/systemc /opt/homebrew/opt/systemc /usr/local/opt/systemc
        PATH_SUFFIXES lib lib-linux64 lib-macosx64
    )

    if(NOT SYSTEMC_INCLUDE_DIR OR NOT SYSTEMC_LIBRARY)
        message(FATAL_ERROR "SystemC not found. Install SystemC or set SYSTEMC_HOME to its install prefix.")
    endif()

    add_library(SystemC::systemc UNKNOWN IMPORTED)
    set_target_properties(SystemC::systemc PROPERTIES
        IMPORTED_LOCATION "${SYSTEMC_LIBRARY}"
        INTERFACE_INCLUDE_DIRECTORIES "${SYSTEMC_INCLUDE_DIR}"
    )
endif()

add_executable(tiny-gpu-vp
    src/tiny_gpu_vp.cpp
)

target_link_libraries(tiny-gpu-vp PRIVATE SystemC::systemc)

target_compile_options(tiny-gpu-vp PRIVATE
    -Wall
    -Wextra
    -Wpedantic
)

include(CTest)
if(BUILD_TESTING)
    add_executable(tiny-gpu-model-regression tests/model_regression.cpp)
    target_link_libraries(tiny-gpu-model-regression PRIVATE SystemC::systemc)
    target_compile_options(tiny-gpu-model-regression PRIVATE -Wall -Wextra -Wpedantic)
    add_test(NAME model-regression COMMAND tiny-gpu-model-regression)
    add_test(NAME workloads COMMAND tiny-gpu-vp all)
endif()
