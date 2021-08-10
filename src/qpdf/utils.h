/*
 * This Source Code Form is subject to the terms of the Mozilla Public
 * License, v. 2.0. If a copy of the MPL was not distributed with this
 * file, You can obtain one at http://mozilla.org/MPL/2.0/.
 *
 * Copyright (C) 2017, James R. Barlow (https://github.com/jbarlow83/)
 */

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