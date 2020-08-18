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

py::memoryview memoryview_from_memory(void *mem, ssize_t size, bool readonly = false);
py::memoryview memoryview_from_memory(const void *mem, ssize_t size);
