/*
 * This Source Code Form is subject to the terms of the Mozilla Public
 * License, v. 2.0. If a copy of the MPL was not distributed with this
 * file, You can obtain one at http://mozilla.org/MPL/2.0/.
 *
 * Copyright (C) 2019, James R. Barlow (https://github.com/jbarlow83/)
 */

#include <qpdf/Constants.h>
#include <qpdf/Types.h>
#include <qpdf/DLL.h>
#include <qpdf/QPDFExc.hh>
#include <qpdf/PointerHolder.hh>
#include <qpdf/QPDFNameTreeObjectHelper.hh>

#include <pybind11/pybind11.h>
#include <pybind11/stl.h>

#include "pikepdf.h"

class NameTreeHolder {
public:
    NameTreeHolder(QPDFObjectHandle oh, bool auto_repair = true)
        : ntoh(oh, *oh.getOwningQPDF(), auto_repair)
    {
    }

    QPDFObjectHandle getObjectHandle() { return this->ntoh.getObjectHandle(); }

    bool hasName(const std::string &utf8) { return this->ntoh.hasName(utf8); }

    bool findObject(const std::string &utf8, QPDFObjectHandle &oh)
    {
        return this->ntoh.findObject(utf8, oh);
    }

    std::map<std::string, QPDFObjectHandle> getAsMap() const
    {
        return this->ntoh.getAsMap();
    }

    void insert(std::string const &key, QPDFObjectHandle value)
    {
        (void)this->ntoh.insert(key, value);
    }

    void remove(std::string const &key)
    {
        bool result = this->ntoh.remove(key);
        if (!result)
            throw py::key_error(key);
    }

    QPDFNameTreeObjectHelper::iterator begin() { return this->ntoh.begin(); }
    QPDFNameTreeObjectHelper::iterator end() { return this->ntoh.end(); }

private:
    QPDFNameTreeObjectHelper ntoh;
};

class NameTreeIterator {
public:
    NameTreeIterator(std::shared_ptr<NameTreeHolder> nt) : nt(nt), iter(nt->begin()) {}

    std::pair<std::string, QPDFObjectHandle> next()
    {
        if (this->iter == this->nt->end())
            throw py::stop_iteration();
        if (!this->iter.valid())
            throw std::logic_error("iterator not valid"); // LCOV_EXCL_LINE
        auto result = *(this->iter);
        this->iter++;
        return result;
    }

private:
    std::shared_ptr<NameTreeHolder> nt;
    QPDFNameTreeObjectHelper::iterator iter;
};

void init_nametree(py::module_ &m)
{
    py::class_<NameTreeHolder, std::shared_ptr<NameTreeHolder>>(m, "NameTree")
        .def(py::init<QPDFObjectHandle, bool>(),
            py::arg("oh"),
            py::kw_only(),
            py::arg("auto_repair") = true,
            py::keep_alive<0, 1>())
        .def_property_readonly(
            "obj",
            [](NameTreeHolder &nt) { return nt.getObjectHandle(); },
            "Returns the underlying root object for this name tree.")
        .def("_contains",
            [](NameTreeHolder &nt, std::string const &name) {
                return nt.hasName(name);
            })
        .def("_getitem",
            [](NameTreeHolder &nt, std::string const &name) {
                QPDFObjectHandle oh;
                if (nt.findObject(name, oh)) // writes to 'oh'
                    return oh;
                else
                    throw py::key_error(name);
            })
        .def(
            "_setitem",
            [](NameTreeHolder &nt, std::string const &name, QPDFObjectHandle oh) {
                nt.insert(name, oh);
            },
            py::keep_alive<0, 1>())
        .def("_setitem",
            [](NameTreeHolder &nt, std::string const &name, py::object obj) {
                auto oh = objecthandle_encode(obj);
                nt.insert(name, oh);
            })
        .def("_delitem",
            [](NameTreeHolder &nt, std::string const &name) { nt.remove(name); })
        .def(
            "_nameval_iter",
            [](std::shared_ptr<NameTreeHolder> nt) { return NameTreeIterator(nt); },
            py::keep_alive<0, 1>())
        .def("_as_map", [](NameTreeHolder &nt) { return nt.getAsMap(); });

    py::class_<NameTreeIterator>(m, "NameTreeIterator")
        .def("__next__", &NameTreeIterator::next)
        .def("__iter__", [](NameTreeIterator &nti) { return nti; });
}
