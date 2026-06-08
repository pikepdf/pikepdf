// SPDX-FileCopyrightText: 2022 James R. Barlow
// SPDX-License-Identifier: MPL-2.0

#pragma once

// Declarations shared between object.cpp and object_methods.cpp, which together
// bind the QPDFObjectHandle ("Object") class. The binding is split across two
// translation units so each one's nanobind template instantiation uses less
// peak compiler memory.

#include "namepath.h"
#include "pikepdf.h"

#include <memory>
#include <string>
#include <utility>

#include <qpdf/Buffer.hh>
#include <qpdf/Constants.h>
#include <qpdf/QPDFObjectHandle.hh>

// Helpers defined in object.cpp and used by object_methods.cpp.
std::string string_from_key(py::handle key);
py::str safe_decode(std::string const &s);
size_t list_range_check(QPDFObjectHandle h, int index);
bool object_has_key(QPDFObjectHandle h, std::string const &key);
bool array_has_item(QPDFObjectHandle haystack, QPDFObjectHandle needle);
QPDFObjectHandle object_get_key(QPDFObjectHandle h, std::string const &key);
void object_set_key(
    QPDFObjectHandle h, std::string const &key, QPDFObjectHandle &value);
void object_del_key(QPDFObjectHandle h, std::string const &key);
QPDFObjectHandle traverse_namepath(
    QPDFObjectHandle h, NamePath const &path, bool for_set = false);
std::pair<int, int> object_get_objgen(QPDFObjectHandle h);
QPDFObjectHandle copy_object(QPDFObjectHandle &h);
std::shared_ptr<Buffer> get_stream_data(
    QPDFObjectHandle &h, qpdf_stream_decode_level_e decode_level);

// Second half of the Object binding, defined in object_methods.cpp.
void init_object_methods(py::class_<QPDFObjectHandle> &object);
