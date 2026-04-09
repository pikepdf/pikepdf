# SPDX-FileCopyrightText: 2022 James R. Barlow
# SPDX-License-Identifier: MPL-2.0

cmake_minimum_required(VERSION 3.15...3.30)
project(pikepdf LANGUAGES CXX)

find_package(Python 3.10
    REQUIRED COMPONENTS Interpreter Development.Module
    OPTIONAL_COMPONENTS Development.SABIModule)

# Detect nanobind: either from pip install or find_package
execute_process(
    COMMAND "${Python_EXECUTABLE}" -m nanobind --cmake_dir
    OUTPUT_STRIP_TRAILING_WHITESPACE OUTPUT_VARIABLE nanobind_ROOT)
find_package(nanobind CONFIG REQUIRED)

# -- Collect sources --
file(GLOB PIKEPDF_SOURCES src/core/*.cpp)

# -- Optional: local qpdf source tree --
set(EXTRA_INCLUDES "")
set(EXTRA_LIBDIRS "")

if(DEFINED ENV{QPDF_SOURCE_TREE} OR EXISTS "${CMAKE_SOURCE_DIR}/../qpdf")
    if(DEFINED ENV{QPDF_SOURCE_TREE})
        set(QPDF_SOURCE_TREE "$ENV{QPDF_SOURCE_TREE}")
    else()
        get_filename_component(QPDF_SOURCE_TREE "${CMAKE_SOURCE_DIR}/../qpdf" ABSOLUTE)
        message(STATUS "Using local qpdf source tree at '${QPDF_SOURCE_TREE}'")
    endif()

    list(APPEND EXTRA_INCLUDES "${QPDF_SOURCE_TREE}/include")

    if(DEFINED ENV{QPDF_BUILD_LIBDIR})
        list(APPEND EXTRA_LIBDIRS "$ENV{QPDF_BUILD_LIBDIR}")
    else()
        list(APPEND EXTRA_LIBDIRS "${QPDF_SOURCE_TREE}/build/libqpdf")
    endif()
endif()

# -- Platform shims for finding qpdf --
if(NOT QPDF_SOURCE_TREE)
    if(CMAKE_SYSTEM_NAME STREQUAL "FreeBSD" OR CMAKE_SYSTEM_NAME STREQUAL "OpenBSD")
        list(APPEND EXTRA_INCLUDES "/usr/local/include")
    elseif(APPLE AND CMAKE_SYSTEM_PROCESSOR STREQUAL "arm64")
        foreach(prefix /opt/homebrew /opt/local)
            if(EXISTS "${prefix}/include")
                list(APPEND EXTRA_INCLUDES "${prefix}/include")
            endif()
            if(EXISTS "${prefix}/lib")
                list(APPEND EXTRA_LIBDIRS "${prefix}/lib")
            endif()
        endforeach()
    endif()
endif()

# -- Build the extension module --
# NB_DOMAIN scopes nanobind's leak warnings to pikepdf's own extension so they
# don't commingle with any other nanobind modules loaded in the same interpreter.
nanobind_add_module(_core
    NB_DOMAIN pikepdf
    ${PIKEPDF_SOURCES}
)

target_compile_features(_core PRIVATE cxx_std_20)

target_include_directories(_core PRIVATE
    ${EXTRA_INCLUDES}
)

target_link_directories(_core PRIVATE
    ${EXTRA_LIBDIRS}
)

target_link_libraries(_core PRIVATE qpdf)

# -- RPATH for local qpdf builds --
if(EXTRA_LIBDIRS AND NOT WIN32)
    set_target_properties(_core PROPERTIES
        BUILD_RPATH "${EXTRA_LIBDIRS}"
        INSTALL_RPATH "${EXTRA_LIBDIRS}"
    )
endif()

# -- Compile definitions --
if(DEFINED ENV{QPDF_FUTURE})
    target_compile_definitions(_core PRIVATE QPDF_FUTURE=True)
endif()

# Suppress GCC note about C++17 ABI change for std::pair
if(NOT WIN32)
    target_compile_options(_core PRIVATE -Wno-psabi)
endif()

# -- Install --
install(TARGETS _core LIBRARY DESTINATION pikepdf)
