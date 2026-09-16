# SPDX-FileCopyrightText: 2026 James R. Barlow
# SPDX-License-Identifier: CC0-1.0

"""Keep the pikepdf._core stubs the single home of its API documentation.

Sphinx, type checkers and IDEs all read the .pyi stubs in src/pikepdf/_core,
so a docstring attached to a C++ binding is never published and only drifts
from the stub. These tests catch docstrings added in C++ and public C++ names
that the stubs do not declare.
"""

from __future__ import annotations

import ast
import collections.abc
from pathlib import Path

import pikepdf
from pikepdf import _core

STUB_DIR = Path(pikepdf.__file__).parent / '_core'

# nanobind's bind_vector/bind_map generate these classes and their docstrings.
NANOBIND_GENERATED = {'_ObjectList', '_ObjectMapping'}


def _runtime_classes():
    for name in dir(_core):
        obj = getattr(_core, name)
        if isinstance(obj, type) and obj.__module__.startswith('pikepdf'):
            yield name, obj


def _nb_doc(func) -> str | None:
    """Return the docstrings a nanobind function carries, or None if none."""
    signatures = getattr(func, '__nb_signature__', None)
    if signatures is None:
        return None
    docs = [doc for _sig, doc, _defaults in signatures if doc]
    return '\n'.join(docs) or None


def _member_funcs(cls):
    for attr, value in vars(cls).items():
        if isinstance(value, property):
            for accessor in (value.fget, value.fset):
                if accessor is not None:
                    yield attr, accessor
        else:
            yield attr, getattr(value, '__func__', value)


def _cpp_docstrings():
    for name in dir(_core):
        doc = _nb_doc(getattr(_core, name))
        if doc:
            yield name, doc
    for cls_name, cls in _runtime_classes():
        if cls_name in NANOBIND_GENERATED:
            continue
        if cls.__doc__ and cls.__doc__.strip():
            yield cls_name, cls.__doc__
        for attr, func in _member_funcs(cls):
            doc = _nb_doc(func)
            if doc:
                yield f'{cls_name}.{attr}', doc


def test_no_docstrings_in_cpp_bindings():
    offenders = sorted(name for name, _doc in _cpp_docstrings())
    assert not offenders, (
        'Document these in the src/pikepdf/_core/*.pyi stubs instead of C++: '
        + ', '.join(offenders)
    )


def _base_name(node: ast.expr) -> str:
    if isinstance(node, ast.Subscript):  # e.g. MutableMapping[str, Object]
        node = node.value
    return node.id if isinstance(node, ast.Name) else ast.unparse(node)


def _stub_declarations():
    """Map each stub class to its declared member names and base classes."""
    module_names: set[str] = set()
    classes: dict[str, tuple[set[str], list[str]]] = {}
    for path in sorted(STUB_DIR.glob('*.pyi')):
        tree = ast.parse(path.read_text(encoding='utf-8'))
        for node in tree.body:
            if isinstance(node, ast.ClassDef):
                module_names.add(node.name)
                members = set()
                for item in node.body:
                    if isinstance(item, ast.FunctionDef | ast.ClassDef):
                        members.add(item.name)
                    elif isinstance(item, ast.AnnAssign) and isinstance(
                        item.target, ast.Name
                    ):
                        members.add(item.target.id)
                    elif isinstance(item, ast.Assign):
                        members.update(
                            t.id for t in item.targets if isinstance(t, ast.Name)
                        )
                bases = [_base_name(b) for b in node.bases]
                classes[node.name] = (members, bases)
            elif isinstance(node, ast.FunctionDef):
                module_names.add(node.name)
            elif isinstance(node, ast.ImportFrom):
                module_names.update(a.asname or a.name for a in node.names)
    return module_names, classes


def _stub_has_member(classes, cls_name, attr) -> bool:
    if cls_name not in classes:
        abc = getattr(collections.abc, cls_name, None)
        return abc is not None and hasattr(abc, attr)
    members, bases = classes[cls_name]
    return attr in members or any(
        _stub_has_member(classes, base, attr) for base in bases
    )


def test_public_cpp_names_are_declared_in_stubs():
    module_names, classes = _stub_declarations()
    missing = [
        name
        for name in dir(_core)
        if not name.startswith('_') and name not in module_names
    ]
    for cls_name, cls in _runtime_classes():
        for attr, value in vars(cls).items():
            if attr.startswith('_'):
                continue
            if cls_name in NANOBIND_GENERATED and isinstance(value, type):
                continue  # nanobind's key/value/item view classes
            if not _stub_has_member(classes, cls_name, attr):
                missing.append(f'{cls_name}.{attr}')
    assert not missing, 'Declare these in the _core stubs: ' + ', '.join(
        sorted(missing)
    )
