// SPDX-FileCopyrightText: 2022 James R. Barlow
// SPDX-License-Identifier: MPL-2.0

#pragma once

#include "pikepdf.h"

py::object fspath(py::object filename);

template <typename T, typename S>
inline bool str_startswith(T haystack, S needle)
{
    return std::string(haystack).rfind(needle, 0) == 0;
}

template <typename T>
inline bool str_replace(std::string &str, T from, T to)
{
    size_t start_pos = str.find(from);
    if (start_pos == std::string::npos)
        return false;
    str.replace(start_pos, std::string(from).length(), to);
    return true;
}