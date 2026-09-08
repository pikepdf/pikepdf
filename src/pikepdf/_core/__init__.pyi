# SPDX-FileCopyrightText: 2022 James R. Barlow
# SPDX-License-Identifier: MPL-2.0

# Type stubs for pikepdf._core, the compiled extension module built from
# src/core/*.cpp.
#
# nanobind can emit stubs via nanobind.stubgen, but we don't run that as part of
# our build, and mypy doesn't understand the way we're augmenting C++ classes
# with Python methods as in pikepdf/_methods.py. Thus, we need to manually spell
# out the resulting types after augmenting.
#
# Layout: pikepdf._core is a single extension module at runtime, but its stub is
# split into one submodule per translation unit, so that each stub sits beside
# the C++ that produces it -- _core/_matrix.pyi covers src/core/matrix.cpp, and
# so on. src/core/pikepdf.cpp, which defines the module itself, is covered by
# two stubs: _exceptions.pyi for the exception hierarchy and _module.pyi for the
# module-level functions. _typing.pyi is the one stub with no C++ counterpart:
# it holds the type variables and aliases the others share, including those
# whose meaning depends on a document's conversion mode.
#
# These submodules exist only for type checkers; none of them is importable at
# runtime. `import pikepdf._core` always resolves to the extension module, and
# everything the extension exposes is re-exported here. Stubs never re-export
# implicitly, so a name stays invisible to type checkers until it is listed in
# __all__ below -- private names included, since pikepdf's own modules import
# plenty of them.
#
# Every stub in the package repeats the directive block below:
#   pylint: this is the whole point of stub files, but apparently we have to
#     spell it out
#   ruff D418: a function decorated with @overload shouldn't contain a
#     docstring, but we want the documentation, and there seems to be no
#     alternative for the moment
#   mypy misc: the facade classes in _object_construct.pyi do not really
#     subclass Object at runtime, among other necessary fictions

# pylint: disable=no-method-argument,unused-argument,no-self-use,too-many-public-methods
# ruff: noqa: D418
# mypy: disable-error-code="misc"

from __future__ import annotations

from pikepdf._core._acroform import (
    AcroForm,
    AcroFormField,
    FormFieldFlag,
)
from pikepdf._core._annotation import (
    Annotation,
    AnnotationFlag,
)
from pikepdf._core._embeddedfiles import (
    AttachedFile,
    AttachedFileSpec,
    Attachments,
)
from pikepdf._core._exceptions import (
    DataDecodingError,
    DeletedObjectError,
    ForeignObjectError,
    JobUsageError,
    PasswordError,
    PdfError,
    PikepdfError,
    ReferenceCycleError,
)
from pikepdf._core._job import (
    Job,
)
from pikepdf._core._matrix import (
    Matrix,
)
from pikepdf._core._module import (
    _get_effective_explicit_mode,
    _get_effective_explicit_mode_for,
    _get_explicit_conversion_mode,
    _pop_thread_conversion_mode,
    _push_thread_conversion_mode,
    _set_explicit_conversion_mode,
    _translate_qpdf_logic_error,
    _unparse_content_stream,
    get_access_default_mmap,
    get_decimal_precision,
    pdf_doc_to_utf8,
    qpdf_version,
    set_access_default_mmap,
    set_decimal_precision,
    set_flate_compression_level,
    utf8_to_pdf_doc,
)
from pikepdf._core._namepath import (
    NamePath,
    _NamePath,
    _NamePathMeta,
)
from pikepdf._core._nametree import (
    NameTree,
)
from pikepdf._core._numbertree import (
    NumberTree,
)
from pikepdf._core._object import (
    Buffer,
    Object,
    ObjectHelper,
    ObjectType,
    StreamParser,
    _encode,
    _new_array,
    _new_boolean,
    _new_dictionary,
    _new_integer,
    _new_name,
    _new_operator,
    _new_real,
    _new_stream,
    _new_string,
    _new_string_utf8,
    _Null,
    _ObjectList,
    _ObjectMapping,
    unparse,
)
from pikepdf._core._object_construct import (
    Array,
    Boolean,
    Dictionary,
    Integer,
    Name,
    Operator,
    Real,
    Stream,
    String,
    _NameObjectMeta,
    _ObjectMeta,
)
from pikepdf._core._page import (
    Page,
)
from pikepdf._core._parsers import (
    ContentStreamInlineImage,
    ContentStreamInstruction,
)
from pikepdf._core._qpdf import (
    AccessMode,
    EncryptionMethod,
    JSONStreamData,
    ObjectStreamMode,
    Pdf,
    StreamDecodeLevel,
    XrefEntry,
)
from pikepdf._core._qpdf_pagelist import (
    PageList,
    _PageListIterator,
)
from pikepdf._core._rectangle import (
    Rectangle,
)
from pikepdf._core._tokenfilter import (
    Token,
    TokenFilter,
    TokenType,
    _QPDFTokenFilter,
)
from pikepdf._core._transcoding import (
    _unpack_subbyte_2bit,
    _unpack_subbyte_4bit,
)
from pikepdf._core._typing import (
    Numeric,
    T,
    TObj,
    _Number,
    _NumberResult,
)

__all__ = [
    '_encode',
    '_get_effective_explicit_mode',
    '_get_effective_explicit_mode_for',
    '_get_explicit_conversion_mode',
    '_NameObjectMeta',
    '_NamePath',
    '_NamePathMeta',
    '_new_array',
    '_new_boolean',
    '_new_dictionary',
    '_new_integer',
    '_new_name',
    '_new_operator',
    '_new_real',
    '_new_stream',
    '_new_string',
    '_new_string_utf8',
    '_Null',
    '_Number',
    '_NumberResult',
    '_ObjectList',
    '_ObjectMapping',
    '_ObjectMeta',
    '_PageListIterator',
    '_pop_thread_conversion_mode',
    '_push_thread_conversion_mode',
    '_QPDFTokenFilter',
    '_set_explicit_conversion_mode',
    '_translate_qpdf_logic_error',
    '_unpack_subbyte_2bit',
    '_unpack_subbyte_4bit',
    '_unparse_content_stream',
    'AccessMode',
    'AcroForm',
    'AcroFormField',
    'Annotation',
    'AnnotationFlag',
    'Array',
    'AttachedFile',
    'AttachedFileSpec',
    'Attachments',
    'Boolean',
    'Buffer',
    'ContentStreamInlineImage',
    'ContentStreamInstruction',
    'DataDecodingError',
    'DeletedObjectError',
    'Dictionary',
    'EncryptionMethod',
    'ForeignObjectError',
    'FormFieldFlag',
    'get_access_default_mmap',
    'get_decimal_precision',
    'Integer',
    'Job',
    'JobUsageError',
    'JSONStreamData',
    'Matrix',
    'Name',
    'NamePath',
    'NameTree',
    'NumberTree',
    'Numeric',
    'Object',
    'ObjectHelper',
    'ObjectStreamMode',
    'ObjectType',
    'Operator',
    'Page',
    'PageList',
    'PasswordError',
    'Pdf',
    'pdf_doc_to_utf8',
    'PdfError',
    'PikepdfError',
    'qpdf_version',
    'Real',
    'Rectangle',
    'ReferenceCycleError',
    'set_access_default_mmap',
    'set_decimal_precision',
    'set_flate_compression_level',
    'Stream',
    'StreamDecodeLevel',
    'StreamParser',
    'String',
    'T',
    'TObj',
    'Token',
    'TokenFilter',
    'TokenType',
    'unparse',
    'utf8_to_pdf_doc',
    'XrefEntry',
]
