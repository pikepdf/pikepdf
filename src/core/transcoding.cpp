// SPDX-FileCopyrightText: 2026 James R. Barlow
// SPDX-License-Identifier: MPL-2.0

#include "pikepdf.h"

#include <cstdint>

namespace {

// RAII wrapper around Py_buffer. Acquires via PyObject_GetBuffer and releases
// in the destructor so exceptions don't leak the buffer reference.
class BufferView {
public:
    BufferView(py::handle obj, int flags) : acquired_(false)
    {
        if (PyObject_GetBuffer(obj.ptr(), &buf_, flags) != 0) {
            throw py::python_error();
        }
        acquired_ = true;
    }
    ~BufferView()
    {
        if (acquired_) {
            PyBuffer_Release(&buf_);
        }
    }
    BufferView(const BufferView &) = delete;
    BufferView &operator=(const BufferView &) = delete;
    BufferView(BufferView &&) = delete;
    BufferView &operator=(BufferView &&) = delete;

    const uint8_t *data() const { return static_cast<const uint8_t *>(buf_.buf); }
    uint8_t *mutable_data() const { return static_cast<uint8_t *>(buf_.buf); }
    Py_ssize_t size() const { return buf_.len; }

private:
    Py_buffer buf_;
    bool acquired_;
};

// All scaling is integer. The callers in unpack_subbyte_pixels only ever pass
// scale = 1 (palette indices) or scale = 255 / (2**bits - 1) — i.e. 85 for
// 2-bit and 17 for 4-bit — so the product of a nibble and the scale always
// fits in a uint8_t exactly. We enforce that invariant in each function so
// callers can't silently truncate by passing a too-large scale.

void unpack_2bit_inner(py::object in_obj, py::object out_obj, int scale)
{
    if (scale < 0 || scale > 85) {
        throw py::value_error("scale must be in [0, 85] for 2-bit unpack");
    }

    BufferView in_view(in_obj, PyBUF_SIMPLE);
    BufferView out_view(out_obj, PyBUF_WRITABLE | PyBUF_SIMPLE);

    const Py_ssize_t n = in_view.size();
    if (out_view.size() < 4 * n) {
        throw py::value_error("output buffer too small for 2-bit unpack");
    }

    const uint8_t s = static_cast<uint8_t>(scale);
    const uint8_t *__restrict in_ptr = in_view.data();
    uint8_t *__restrict out_ptr = out_view.mutable_data();

    for (Py_ssize_t i = 0; i < n; ++i) {
        const uint8_t val = in_ptr[i];
        out_ptr[4 * i + 0] = static_cast<uint8_t>((val >> 6) * s);
        out_ptr[4 * i + 1] = static_cast<uint8_t>(((val >> 4) & 0x3u) * s);
        out_ptr[4 * i + 2] = static_cast<uint8_t>(((val >> 2) & 0x3u) * s);
        out_ptr[4 * i + 3] = static_cast<uint8_t>((val & 0x3u) * s);
    }
}

void unpack_4bit_inner(py::object in_obj, py::object out_obj, int scale)
{
    if (scale < 0 || scale > 17) {
        throw py::value_error("scale must be in [0, 17] for 4-bit unpack");
    }

    BufferView in_view(in_obj, PyBUF_SIMPLE);
    BufferView out_view(out_obj, PyBUF_WRITABLE | PyBUF_SIMPLE);

    const Py_ssize_t n = in_view.size();
    if (out_view.size() < 2 * n) {
        throw py::value_error("output buffer too small for 4-bit unpack");
    }

    const uint8_t s = static_cast<uint8_t>(scale);
    const uint8_t *__restrict in_ptr = in_view.data();
    uint8_t *__restrict out_ptr = out_view.mutable_data();

    for (Py_ssize_t i = 0; i < n; ++i) {
        const uint8_t val = in_ptr[i];
        out_ptr[2 * i + 0] = static_cast<uint8_t>((val >> 4) * s);
        out_ptr[2 * i + 1] = static_cast<uint8_t>((val & 0xFu) * s);
    }
}

} // namespace

void init_transcoding(py::module_ &m)
{
    m.def("_unpack_subbyte_2bit",
        &unpack_2bit_inner,
        py::arg("in_").noconvert(),
        py::arg("out").noconvert(),
        py::arg("scale"),
        "Unpack 2-bit values into bytes scaled by 'scale' (0..85). "
        "Output buffer must be at least 4x the input length.");
    m.def("_unpack_subbyte_4bit",
        &unpack_4bit_inner,
        py::arg("in_").noconvert(),
        py::arg("out").noconvert(),
        py::arg("scale"),
        "Unpack 4-bit values into bytes scaled by 'scale' (0..17). "
        "Output buffer must be at least 2x the input length.");
}
