// SPDX-FileCopyrightText: 2022 James R. Barlow
// SPDX-License-Identifier: MPL-2.0

#include <qpdf/Constants.h>
#include <qpdf/Types.h>
#include <qpdf/DLL.h>
#include <qpdf/QPDFExc.hh>
#include <qpdf/PointerHolder.hh>
#include <qpdf/QPDFNameTreeObjectHelper.hh>

#include <pybind11/pybind11.h>
#include <pybind11/stl.h>

#include "pikepdf.h"

// Dummy class to avoid error: undefined symbol: _ZTI24QPDFNameTreeObjectHelper
// That is, "typeinfo for QPDFNameTreeObjectHelper"
// Possibly QPDF needs to export QPDFNameTreeObjectHelper with QPDF_DLL although
// it's not clear why.
// The unique_ptr allows us to hold a QPDFNameTreeObjectHelper without knowing
// its typeinfo. Somehow.
class NameTreeHolder {
public:
    NameTreeHolder(QPDFObjectHandle oh, bool auto_repair = true)
    {
        if (!oh.getOwningQPDF()) {
            throw py::value_error(
                "NameTree must wrap a Dictionary that is owned by a Pdf");
        }
        ntoh = std::make_unique<QPDFNameTreeObjectHelper>(
            oh, *oh.getOwningQPDF(), auto_repair);
    }

    static NameTreeHolder newEmpty(QPDF &pdf, bool auto_repair = true)
    {
        // Would be a little cleaner to do:
        // auto new_ntoh = QPDFNameTreeObjectHelper::newEmpty(pdf, auto_repair);
        // Then again, it would be clear to eliminate this class entirely.
        // But gcc wants QPDF 10.6.3 to export typeinfo and vtable
        // So work around it for now by duplicating the code in ::newEmpty() to
        // create a root node, make a holder for it.
        auto root = pdf.makeIndirectObject(QPDFObjectHandle::parse("<< /Names [] >>"));
        return NameTreeHolder(root, auto_repair);
    }

    QPDFObjectHandle getObjectHandle() { return this->ntoh->getObjectHandle(); }

    bool hasName(const std::string &utf8) { return this->ntoh->hasName(utf8); }

    bool findObject(const std::string &utf8, QPDFObjectHandle &oh)
    {
        return this->ntoh->findObject(utf8, oh);
    }

    std::map<std::string, QPDFObjectHandle> getAsMap() const
    {
        return this->ntoh->getAsMap();
    }

    void insert(std::string const &key, QPDFObjectHandle value)
    {
        (void)this->ntoh->insert(key, value);
    }

    void remove(std::string const &key)
    {
        bool result = this->ntoh->remove(key);
        if (!result)
            throw py::key_error(key);
    }

    QPDFNameTreeObjectHelper::iterator begin() { return this->ntoh->begin(); }
    QPDFNameTreeObjectHelper::iterator end() { return this->ntoh->end(); }

private:
    std::unique_ptr<QPDFNameTreeObjectHelper> ntoh;
};

void init_nametree(py::module_ &m)
{
    py::class_<NameTreeHolder>(m, "NameTree")
        .def(py::init<QPDFObjectHandle, bool>(),
            py::arg("oh"), // LCOV_EXCL_LINE
            py::kw_only(), // LCOV_EXCL_LINE
            py::arg("auto_repair") = true,
            py::keep_alive<0, 1>())
        .def_static(
            "new",
            [](QPDF &pdf, bool auto_repair = true) {
                return NameTreeHolder::newEmpty(pdf, auto_repair);
            },
            py::arg("pdf"), // LCOV_EXCL_LINE
            py::kw_only(),
            py::arg("auto_repair") = true,
            py::keep_alive<0, 1>(),
            R"~~~(
                Create a new NameTree in the provided Pdf.

                You will probably need to insert the name tree in the PDF's
                catalog. For example, to insert this name tree in 
                /Root /Names /Dests:

                .. code-block:: python

                    nt = NameTree.new(pdf)
                    pdf.Root.Names.Dests = nt.obj
            )~~~")
        .def_property_readonly(
            "obj",
            [](NameTreeHolder &nt) { return nt.getObjectHandle(); },
            "Returns the underlying root object for this name tree.")
        .def(
            "__eq__",
            [](NameTreeHolder &self, NameTreeHolder &other) {
                return objecthandle_equal(
                    self.getObjectHandle(), other.getObjectHandle());
            },
            py::is_operator())
        .def_property_readonly("_pikepdf_disallow_objecthandle_encode",
            [](NameTreeHolder &nt) { return true; })
        .def("__contains__",
            [](NameTreeHolder &nt, std::string const &name) {
                return nt.hasName(name);
            })
        .def("__getitem__",
            [](NameTreeHolder &nt, std::string const &name) {
                QPDFObjectHandle oh;
                if (nt.findObject(name, oh)) // writes to 'oh'
                    return oh;
                else
                    throw py::key_error(name);
            })
        .def("__setitem__",
            [](NameTreeHolder &nt, std::string const &name, QPDFObjectHandle oh) {
                nt.insert(name, oh);
            })
        .def("__setitem__",
            [](NameTreeHolder &nt, std::string const &name, py::object obj) {
                auto oh = objecthandle_encode(obj);
                nt.insert(name, oh);
            })
        .def("__delitem__",
            [](NameTreeHolder &nt, std::string const &name) { nt.remove(name); })
        .def(
            "__iter__",
            [](NameTreeHolder &nt) { return py::make_key_iterator(nt); },
            py::return_value_policy::reference_internal)
        .def(
            "_as_map",
            [](NameTreeHolder &nt) { return nt.getAsMap(); },
            py::return_value_policy::reference_internal)
        .def("__len__", [](NameTreeHolder &nt) { return nt.getAsMap().size(); });
}
