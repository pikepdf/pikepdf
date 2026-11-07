// SPDX-FileCopyrightText: 2022 James R. Barlow
// SPDX-License-Identifier: MPL-2.0

#include "locked_bindings.h"
#include "object.h"
#include "pikepdf.h"

#include <qpdf/Constants.h>
#include <qpdf/DLL.h>
#include <qpdf/QPDFExc.hh>
#include <qpdf/QPDFNameTreeObjectHelper.hh>
#include <qpdf/Types.h>

using NameTree = QPDFNameTreeObjectHelper;

void init_nametree(py::module_ &m)
{
    locked_class_<NameTree, QPDFObjectHelper>(
        m, "NameTree", py::type_slots(pikepdf_gc_slots))
        .def_init(
            [](QPDFObjectHandle &oh, bool auto_repair) {
                QPDF *owner = live_owner(oh);
                if (!owner)
                    throw py::value_error(
                        "NameTree must wrap a Dictionary that is owned by a Pdf");
                return NameTree(oh, *owner, auto_repair);
            },
            py::arg("oh"), // LCOV_EXCL_LINE
            py::kw_only(), // LCOV_EXCL_LINE
            py::arg("auto_repair") = true,
            py::keep_alive<0, 1>())
        .def_static(
            "new",
            [](QPDF &pdf, bool auto_repair = true) {
                return NameTree::newEmpty(pdf, auto_repair);
            },
            py::arg("pdf"), // LCOV_EXCL_LINE
            py::kw_only(),
            py::arg("auto_repair") = true,
            py::keep_alive<0, 1>())
        .def_prop_ro("obj", [](NameTree &nt) { return nt.getObjectHandle(); })
        .def(
            "__eq__",
            [](NameTree &self, NameTree &other) {
                return objecthandle_equal(
                    self.getObjectHandle(), other.getObjectHandle());
            },
            py::is_operator())
        .def("__contains__",
            [](NameTree &nt, std::string const &name) { return nt.hasName(name); })
        .def("__contains__",
            // Only a str can be a name
            unlocked([](NameTree &, py::object) { return false; }),
            py::arg("name").none())
        .def("__getitem__",
            [](NameTree &nt, std::string const &name) {
                QPDFObjectHandle oh;
                if (nt.findObject(name, oh)) // writes to 'oh'
                    return oh;
                else
                    throw py::key_error(name.c_str());
            })
        .def("__setitem__",
            [](NameTree &nt, std::string const &name, EncodedObject const &value) {
                auto tree = nt.getObjectHandle();
                auto *owner = live_owner(tree);
                refuse_foreign_indirect(value.get(), owner);
                nt.insert(name, adopt_into(owner, value.get()));
            })
        .def("__delitem__",
            [](NameTree &nt, std::string const &name) {
                bool result = nt.remove(name);
                if (!result)
                    throw py::key_error(name.c_str());
            })
        .def("__iter__",
            [](NameTree &nt) {
                // The names as they are now. An iterator over the tree itself
                // would go on reading the Pdf after this returns, without the
                // lock, and would be invalidated by a change to the tree.
                py::list names;
                for (auto it = nt.begin(); it != nt.end(); ++it)
                    names.append(py::cast((*it).first));
                return py::iter(names);
            })
        .def(
            "_as_map",
            [](NameTree &nt) { return nt.getAsMap(); },
            py::rv_policy::reference_internal)
        .def("__len__", [](NameTree &nt) { return nt.getAsMap().size(); });
}
