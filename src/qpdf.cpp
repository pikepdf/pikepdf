/*
 * This Source Code Form is subject to the terms of the Mozilla Public
 * License, v. 2.0. If a copy of the MPL was not distributed with this
 * file, You can obtain one at http://mozilla.org/MPL/2.0/.
 *
 * Copyright (C) 2017, James R. Barlow (https://github.com/jbarlow83/)
 */

#include <sstream>

#include <qpdf/Constants.h>
#include <qpdf/Types.h>
#include <qpdf/DLL.h>
#include <qpdf/QPDFExc.hh>
#include <qpdf/QPDFObjGen.hh>
#include <qpdf/QPDFXRefEntry.hh>
#include <qpdf/PointerHolder.hh>
#include <qpdf/Buffer.hh>
#include <qpdf/QPDFObjectHandle.hh>
#include <qpdf/QPDF.hh>
#include <qpdf/QPDFWriter.hh>

#include <pybind11/pybind11.h>
#include <pybind11/stl.h>

#include "pikepdf.h"

using namespace std::literals::string_literals;

extern "C" const char* qpdf_get_qpdf_version();

template <typename T>
void kwargs_to_method(py::kwargs kwargs, const char* key, std::unique_ptr<QPDF> &q, void (QPDF::*callback)(T))
{
    try {
        if (kwargs.contains(key)) {
            auto v = kwargs[key].cast<T>();
            ((*q).*callback)(v); // <-- Cute
        }
    } catch (py::cast_error &e) {
        throw py::type_error(std::string(key) + ": unsupported argument type");
    }
}


/* Convert a Python object to a filesystem encoded path
 * Use Python's os.fspath() which accepts os.PathLike (str, bytes, pathlib.Path)
 * and returns bytes encoded in the filesystem encoding.
 * Cast to a string without transcoding.
 */
std::string fsencode_filename(py::object py_filename)
{
    auto fspath = py::module::import("pikepdf._cpphelpers").attr("fspath");
    std::string filename;

    try {
        auto py_encoded_filename = fspath(py_filename);
        filename = py_encoded_filename.cast<std::string>();
    } catch (py::cast_error &e) {
        throw py::type_error("expected pathlike object");
    }

    return filename;
}

void check_stream_is_usable(py::object stream)
{
    auto TextIOBase = py::module::import("io").attr("TextIOBase");

    if (py::isinstance(stream, TextIOBase)) {
        throw py::type_error("stream must be binary (no transcoding) and seekable");
    }
}

auto open_pdf(py::args args, py::kwargs kwargs)
{
    auto q = std::make_unique<QPDF>();
    if (args.size() < 1)
        throw py::value_error("not enough arguments");
    if (args.size() > 2)
        throw py::value_error("too many arguments");

    std::string password;

    q->setSuppressWarnings(true);
    if (kwargs) {
        if (kwargs.contains("password")) {
            auto v = kwargs["password"].cast<std::string>();
            password = v;
        }
        kwargs_to_method(kwargs, "ignore_xref_streams", q, &QPDF::setIgnoreXRefStreams);
        kwargs_to_method(kwargs, "suppress_warnings", q, &QPDF::setSuppressWarnings);
        kwargs_to_method(kwargs, "attempt_recovery", q, &QPDF::setAttemptRecovery);
    }

    if (py::hasattr(args[0], "read") && py::hasattr(args[0], "seek")) {
        // Python code gave us an object with a stream interface
        py::object stream = args[0];

        check_stream_is_usable(stream);

        py::object read = stream.attr("read");
        py::object pydata = read();
        py::bytes data = pydata.cast<py::bytes>();
        char *buffer;
        ssize_t length;

        // Is it safe to grab .ptr() like this? Not sure; probably safe under
        // GIL only
        PYBIND11_BYTES_AS_STRING_AND_SIZE(data.ptr(), &buffer, &length);

        // libqpdf will create a copy of this memory and attach it
        // to 'q'
        // This could be improved by subclassing InputSource into C++
        // and creating a version that obtains its data from its Python object,
        // but that is much more complex.
        q->processMemoryFile("memory", buffer, length, password.c_str());
    } else {
        std::string filename = fsencode_filename(args[0]);
        // We can release GIL because Python knows nothing about q at this
        // point; this could also take a moment for large files
        py::gil_scoped_release release;
        q->processFile(filename.c_str(), password.c_str());
    }

    return q;
}


void save_pdf(
    QPDF &q,
    py::object filename_or_stream,
    bool static_id=false,
    bool preserve_pdfa=false,
    std::string min_version=""s,
    std::string force_version=""s,
    qpdf_object_stream_e object_stream_mode=qpdf_o_preserve,
    qpdf_stream_data_e stream_data_mode=qpdf_s_preserve)
{
    QPDFWriter w(q);

    // Parameters
    if (static_id) {
        w.setStaticID(true);
        w.setStreamDataMode(qpdf_s_uncompress);
    }
    if (!min_version.empty()) {
        w.setMinimumPDFVersion(min_version, 0);
    }
    if (!force_version.empty()) {
        w.forcePDFVersion(force_version, 0);
    }
    w.setObjectStreamMode(object_stream_mode);
    w.setStreamDataMode(stream_data_mode);

    if (py::hasattr(filename_or_stream, "read") && py::hasattr(filename_or_stream, "seek")) {
        // Python code gave us an object with a stream interface
        py::object stream = filename_or_stream;
        check_stream_is_usable(stream);

        if (preserve_pdfa) {
            throw py::notimpl_error("Cannot perserve PDF/A compatible when writing to a stream");
        }

        // TODO could improve this by streaming rather than buffering
        // using subclass of Pipeline that routes calls to Python
        w.setOutputMemory();
        w.write();

        // getBuffer returns Buffer* and qpdf says we are responsible for
        // deleting it, so capture it
        std::unique_ptr<Buffer> output_buffer(w.getBuffer());

        // Awkward API alert:
        //     QPDFWriter::getBuffer -> Buffer*  (caller frees memory)
        // and  Buffer::getBuffer -> unsigned char*  (caller does not own memory)
        auto output = py::bytes(
            (const char*)output_buffer->getBuffer(),
            output_buffer->getSize());

        stream.attr("write")(output);
    } else {
        py::object filename = filename_or_stream;
        w.setOutputFilename(fsencode_filename(filename).c_str());
        w.write();

        if (preserve_pdfa) {
            auto helpers = py::module::import("pikepdf._cpphelpers");
            helpers.attr("repair_pdfa")(filename);
        }
    }
}

class PageList {
public:
    PageList(QPDF &q) : qpdf(q) {};

    QPDFObjectHandle getItem(size_t index) const
    {
        auto pages = this->qpdf.getAllPages();
        if (index < pages.size())
            return pages.at(index);        
        throw py::index_error("Accessing nonexistent PDF page number");
    }

    py::list getItemList(py::slice slice) 
    {
        size_t start, stop, step, slicelength;
        if (!slice.compute(this->count(), &start, &stop, &step, &slicelength))
            throw py::error_already_set();
        py::list result;
        for (size_t i = 0; i < slicelength; ++i) {
            QPDFObjectHandle oh = this->getItem(start);
            result.append(oh);
            start += step;
        }
        return result;
    }

    void setItem(size_t index, QPDFObjectHandle page) 
    {
        this->insertItem(index, page);
        if (index != this->count()) {
            this->deleteItem(index + 1);
        }
    }

    void setItemList(py::slice slice, const PageList &other)
    {
        size_t start, stop, step, slicelength;
        if (!slice.compute(this->count(), &start, &stop, &step, &slicelength))
            throw py::error_already_set();
        if (slicelength != other.count())
            throw std::runtime_error("Left and right hand size of slice assignment have different sizes!");
        for (size_t i = 0; i < slicelength; ++i) {
            this->setItem(start, other.getItem(i)); start += step;
        }
    }

    void setItemsFromIterable(py::slice slice, py::iterable other)
    {
        size_t start, stop, step, slicelength;
        if (!slice.compute(this->count(), &start, &stop, &step, &slicelength))
            throw py::error_already_set();
        std::vector<QPDFObjectHandle> results;
        py::iterator it = other.attr("__iter__")();
        for (size_t i = 0; i < slicelength; i++) {
            if (it == py::iterator::sentinel())
                throw std::runtime_error("Left and right hand size of slice assignment have different sizes!");
            QPDFObjectHandle oh;
            try {
                oh = (*it).cast<QPDFObjectHandle>();
            } catch (py::cast_error) {
                throw py::type_error("only pages can be assigned to a page list");
            }
            if (!oh.isPageObject()) {
                throw py::type_error("only pages can be assigned to a page list");
            }
            results.push_back(oh);
            ++it;
        }
        if (it != py::iterator::sentinel())
            throw std::runtime_error("Left and right hand size of slice assignment have different sizes!");
        
        for (size_t i = 0; i < slicelength; ++i) {
            this->setItem(start, results[i]); start += step;
        }
    }

    void deleteItem(size_t index)
    {
        auto page = this->getItem(index);
        this->qpdf.removePage(page);
    }

    size_t count() const
    {
        return this->qpdf.getAllPages().size();
    }

    void insertItem(size_t index, QPDFObjectHandle page)
    {
        if (page.getOwningQPDF() == &this->qpdf) {
            page = this->qpdf.makeIndirectObject(page);
        }

        if (index != this->count()) {
            QPDFObjectHandle refpage = this->getItem(index);
            this->qpdf.addPageAt(page, true, refpage);
        } else {
            this->qpdf.addPage(page, false);
        }
    }

    QPDF &getQPDF() { return qpdf; }

private:
    QPDF &qpdf;
};


PYBIND11_MODULE(_qpdf, m) {
    //py::options options;
    //options.disable_function_signatures();

    m.doc() = "pikepdf provides a Pythonic interface for QPDF";

    m.def("qpdf_version", &qpdf_get_qpdf_version, "Get libqpdf version");

    static py::exception<QPDFExc> exc_main(m, "PDFError");
    static py::exception<QPDFExc> exc_password(m, "PasswordError");
    py::register_exception_translator([](std::exception_ptr p) {
        try {
            if (p) std::rethrow_exception(p);
        } catch (const QPDFExc &e) {
            if (e.getErrorCode() == qpdf_e_password) {
                exc_password(e.what());
            } else {
                exc_main(e.what());
            }
        }
    });

    py::enum_<qpdf_object_stream_e>(m, "ObjectStreamMode")
        .value("disable", qpdf_object_stream_e::qpdf_o_disable)
        .value("preserve", qpdf_object_stream_e::qpdf_o_preserve)
        .value("generate", qpdf_object_stream_e::qpdf_o_generate);

    py::enum_<qpdf_stream_data_e>(m, "StreamDataMode")
        .value("uncompress", qpdf_stream_data_e::qpdf_s_uncompress)
        .value("preserve", qpdf_stream_data_e::qpdf_s_preserve)
        .value("compress", qpdf_stream_data_e::qpdf_s_compress);
        
    py::class_<PageList>(m, "PageList")
        .def("__getitem__", &PageList::getItem)
        .def("__getitem__", &PageList::getItemList)
        .def("__setitem__", &PageList::setItem)
        .def("__setitem__", &PageList::setItemList)
        .def("__setitem__", &PageList::setItemsFromIterable)
        .def("__delitem__", &PageList::deleteItem)
        .def("__len__", &PageList::count)
        //.def("insert", &PageList::insertItem, py::keep_alive<1, 3>())
        .def("insert", 
            [](PageList &pl, size_t index, py::object item) {
                QPDFObjectHandle page;
                try {
                    page = item.cast<QPDFObjectHandle>();
                } catch (py::cast_error) {
                    throw py::type_error("only pages can be inserted");
                }

                // Get our owner
                QPDF *page_owner = page.getOwningQPDF();
                py::object pyqpdf = py::cast(page_owner);

                // Gulp
                pyqpdf.inc_ref();
                pl.insertItem(index, page);
            }, py::keep_alive<1, 3>()
        )
        .def("reverse", 
            [](PageList &pl) {
                py::slice ordinary_indices(0, pl.count(), 1);                
                py::int_ step(-1);
                PyObject *raw_slice = PySlice_New(Py_None, Py_None, step.ptr());
                py::slice reversed = py::reinterpret_steal<py::slice>(raw_slice);
                py::list reversed_pages = pl.getItemList(reversed);
                pl.setItemsFromIterable(ordinary_indices, reversed_pages);
            }
        )
        .def("append",
            [](PageList &pl, QPDFObjectHandle &page) {
                pl.insertItem(pl.count(), page);
                //return &pl.getQPDF();
            }
            //py::keep_alive<0, 2>()
        )
        ;

    py::class_<QPDF>(m, "PDF", "In-memory representation of a PDF")
        .def_static("new",
            []() {
                auto q = std::make_unique<QPDF>();
                q->emptyPDF();
                q->setSuppressWarnings(true);
                return q;
            },
            "create a new empty PDF from stratch"
        )
        .def_static("open", open_pdf,
            R"~~~(
            Open an existing file at `filename_or_stream` according to `options`, all
            of which are optional.

            If `filename_or_stream` is path-like, the file will be opened.

            If `filename_or_stream` has `.read()` and `.seek()` methods, the file
            will be accessed as a readable binary stream. pikepdf will read the
            entire stream into a private buffer.

            :param filename_or_stream: Filename of PDF to open
            :param password: User or owner password to open the PDF, if encrypted
            :type filename_or_stream: os.PathLike or file stream
            :type password: str or None
            :param ignore_xref_streams: If True, ignore cross-reference streams. See qpdf documentation.
            :param suppress_warnings: If True (default), warnings are not printed to stderr. Use `get_warnings()` to retrieve warnings.
            :param attempt_recovery: If True (default), attempt to recover from PDF parsing errors.
            :throws pikepdf.PasswordError: If the password failed to open the file.
            :throws pikepdf.PDFError: If for other reasons we could not open the file.
            :throws TypeError: If the type of `filename_or_stream` is not usable.
            )~~~"
        )
        .def("__repr__",
            [](const QPDF &q) {
                return "<pikepdf.PDF description='"s + q.getFilename() + "'>"s;
            }
        )
        .def_property_readonly("filename", &QPDF::getFilename,
            "the source filename of an existing PDF, when available")
        .def_property_readonly("pdf_version", &QPDF::getPDFVersion,
            "the PDF standard version, such as '1.7'")
        .def_property_readonly("extension_level", &QPDF::getExtensionLevel)
        .def_property_readonly("Root", &QPDF::getRoot,
            "the /Root object of the PDF")
        .def_property_readonly("root", &QPDF::getRoot,
            "alias for .Root, the /Root object of the PDF")    
        .def_property_readonly("trailer", &QPDF::getTrailer,
            "the PDF trailer")
        .def_property_readonly("pages",
            [](QPDF &q) {
                return PageList(q);
            }
        )
        .def_property_readonly("_pages", &QPDF::getAllPages)
        .def_property_readonly("is_encrypted", &QPDF::isEncrypted)
        .def("get_warnings", &QPDF::getWarnings)  // this is a def because it modifies state by clearing warnings
        .def("show_xref_table", &QPDF::showXRefTable)
        .def("_add_page",
            [](QPDF& q, QPDFObjectHandle& page, bool first=false) {
                q.addPage(page, first);
            },
            R"~~~(
            Attach a page to this PDF. The page can be either be a
            newly constructed PDF object or it can be obtained from another
            PDF.

            :param pikepdf.Object page: The page object to attach
            :param bool first: If True, prepend this before the first page; if False append after last page
            )~~~",
            py::arg("page"),
            py::arg("first")=false,
            py::keep_alive<1, 2>()
        )
        .def("_add_page_at", &QPDF::addPageAt, py::keep_alive<1, 2>())
        .def("_remove_page", &QPDF::removePage)
        .def("save",
             save_pdf,
             "save as a PDF",
             py::arg("filename"),
             py::arg("static_id")=false,
             py::arg("preserve_pdfa")=false,
             py::arg("min_version")=""s,
             py::arg("force_version")=""s,
             py::arg("object_stream_mode")=qpdf_o_preserve,
             py::arg("stream_data_mode")=qpdf_s_preserve
        )
        .def("_get_object_id", &QPDF::getObjectByID)
        .def("make_indirect", &QPDF::makeIndirectObject)
        .def("make_indirect",
            [](QPDF &q, py::object obj) -> QPDFObjectHandle {
                return q.makeIndirectObject(objecthandle_encode(obj));
            }
        )
        .def("_replace_object",
            [](QPDF &q, int objid, int gen, QPDFObjectHandle &h) {
                q.replaceObject(objid, gen, h);
            }
        );

    init_object(m);

#ifdef VERSION_INFO
    m.attr("__version__") = py::str(VERSION_INFO);
#else
    m.attr("__version__") = py::str("dev");
#endif
}
