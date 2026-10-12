# SPDX-FileCopyrightText: 2026 James R. Barlow
# SPDX-License-Identifier: CC0-1.0

"""Keep the pikepdf._core stubs the single home of its API documentation.

Sphinx, type checkers and IDEs all read the .pyi stubs in src/pikepdf/_core,
so a docstring attached to a C++ binding is never published and only drifts
from the stub. These tests catch docstrings added in C++ and public C++ names
that the stubs do not declare.

They also compare the signature of every C++ binding with its declaration in
the stubs. mypy.stubtest cannot do this, because nanobind functions have no
inspect.signature; they do carry ``__nb_signature__``, the text of a ``def``
line for each overload, which is parsed here. Only what C++ binds is compared:
where pikepdf._methods replaces a method with a Python function, the stub
describes that function and there is no binding left to compare it with.

The stubs are deliberately not a transcription of the bindings. They split one
binding into overloads to give precise return types, merge several overloads
into one declaration, narrow ``object`` to what is really accepted, and make
parameters positional-only where C++ has a name not worth publishing. So the
comparison does not ask for identical text, but for two properties:

Soundness: every call a stub declaration allows is one C++ accepts. A
declaration with optional positional parameters is taken as one way of calling
the member for each number of arguments it allows, since ``f(x=...)`` in a stub
may stand for the overloads ``f()`` and ``f(x)``. Each such way of calling must
fit at least one overload of the binding:

* its positional parameters correspond, in order, to those of the overload,
  and there are no more of them than the overload takes;
* a parameter that may be passed by keyword has the same name in C++, and is
  not positional-only there (special methods excepted, since their parameters
  are positional by convention however they are declared);
* its keyword-only parameters, ``*args`` and ``**kwargs`` exist in C++;
* every parameter of the overload that it leaves out, or lets callers leave
  out, has a default in C++;
* a default the stub writes as a literal is the default in C++.

Completeness: nothing C++ binds is unreachable through the stubs. Every
overload must be fitted by some declaration, and among the declarations that
fit it, every parameter must appear in one, and every parameter that has a
default must be one that some declaration lets callers omit. Likewise a
property that C++ lets callers set needs a setter in the stub, and one it
does not must not have one. A method must not be declared as a property, nor
a static method as an instance method, nor the reverse.

So the number of overloads need not be equal, but neither side may have one
the other cannot account for.

Types are compared only for contradiction, because nanobind prints the C++
parameter type, not everything implicit conversion accepts, and prints
``object`` wherever the binding works on Python objects directly. Annotations
are reduced to the classes at the top level of their union (``list[Page] |
None`` is ``list`` and ``None``); anything that is not a class, such as
``object``, ``Any``, a type variable or an alias, could be anything and never
contradicts. Two classes agree if one is a subclass of the other. Then:

* a parameter is flagged if none of the types C++ takes agrees with any the
  stub takes, or if the stub takes ``None`` and C++ does not;
* a return type is flagged if C++ can return a type that agrees with none of
  those in the stub's annotation, as when C++ returns ``bool`` and the stub
  says ``None``. A binding that returns ``Object`` may in fact return ``None``,
  ``int``, ``bool`` or ``Decimal``, because pikepdf decodes those on the way
  out, so a stub may say so.

A difference that is intended goes in SIGNATURE_ALLOWLIST, with the reason.
"""

from __future__ import annotations

import ast
import builtins
import collections.abc
import datetime
import decimal
import os
import pathlib
import re
import types
from dataclasses import dataclass, field, replace
from pathlib import Path
from types import SimpleNamespace

import pytest

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


# Members whose C++ signature and stub declaration differ on purpose. Each entry
# is 'Class.member' (or the bare name of a module-level function) and the reason
# the difference is wanted. An entry that no longer differs fails the test.
SIGNATURE_ALLOWLIST: dict[str, str] = {
    # copy_foreign(Page) is bound only to raise NotImplementedError, with a
    # message directing the caller to Pdf.pages. It is not an API to declare.
    'Pdf.copy_foreign': 'the overload taking a Page exists to raise an error',
    # make_indirect has an overload for Object, whose parameter is `h`, and a
    # general one, whose parameter is `obj`. The stub declares `obj`, which
    # works for every argument; declaring the first too would publish `h`.
    'Pdf.make_indirect': 'the parameter name of the Object overload is not public',
}

_UNKNOWN = object()  # a type about which nothing can be concluded
_NUMERIC_TOWER = (bool, int, float)
_TYPE_NAMESPACES = (builtins, collections.abc, datetime, decimal, os, pathlib, types)

# What nanobind converts implicitly to the containers it generates, which are
# declared in the stubs without base classes.
_IMPLICIT_BASES: dict[str, type] = {
    '_ObjectList': collections.abc.Iterable,
    '_ObjectMapping': collections.abc.Mapping,
}

# What a function bound as returning Object may return instead: the type caster
# in src/core/pikepdf.h decodes null and, unless the conversion mode is
# explicit, numbers and booleans.
_OBJECT_RETURNED_AS = {type(None), int, bool, decimal.Decimal}


@dataclass(frozen=True)
class _Param:
    name: str
    kind: str  # 'positional', 'standard', 'keyword', 'var' or 'varkw'
    annotation: ast.expr | None
    default: ast.expr | None

    @property
    def is_positional(self) -> bool:
        return self.kind in ('positional', 'standard')


@dataclass(frozen=True)
class _Signature:
    params: tuple[_Param, ...]
    returns: ast.expr | None
    text: str
    is_static: bool = False
    defaults: tuple = ()  # the default values of a nanobind signature

    def has(self, kind: str) -> bool:
        return any(p.kind == kind for p in self.params)

    def without_receiver(self) -> _Signature:
        return replace(self, params=self.params[1:])


def _signature_from_def(node: ast.FunctionDef, text: str, **kwargs) -> _Signature:
    a = node.args
    params: list[_Param] = []
    positional = a.posonlyargs + a.args
    defaults: list[ast.expr | None] = [None] * (len(positional) - len(a.defaults))
    defaults.extend(a.defaults)
    for i, (arg, default) in enumerate(zip(positional, defaults, strict=True)):
        kind = 'positional' if i < len(a.posonlyargs) else 'standard'
        params.append(_Param(arg.arg, kind, arg.annotation, default))
    if a.vararg:
        params.append(_Param(a.vararg.arg, 'var', a.vararg.annotation, None))
    for arg, default in zip(a.kwonlyargs, a.kw_defaults, strict=True):
        params.append(_Param(arg.arg, 'keyword', arg.annotation, default))
    if a.kwarg:
        params.append(_Param(a.kwarg.arg, 'varkw', a.kwarg.annotation, None))
    return _Signature(tuple(params), node.returns, text, **kwargs)


def _runtime_signatures(func) -> list[_Signature]:
    r"""Parse the signatures nanobind recorded for a bound function.

    Each is a ``def`` line without a body, which may lack a name (properties,
    lambdas) and refers to its default values as ``\0``, ``\1``...
    """
    result = []
    for text, _doc, defaults in func.__nb_signature__:
        defaults = defaults or ()
        source = re.sub(r'^def \w*\(', 'def _(', text)
        source = re.sub(r'\\(\d+)', r'_default_\1', source)
        node = ast.parse(source + ': ...').body[0]
        assert isinstance(node, ast.FunctionDef)
        # The lambda is called by re.sub, before the loop moves on
        shown = re.sub(
            r'\\(\d+)',
            lambda m: repr(defaults[int(m[1])]),  # noqa: B023
            text,
        )
        result.append(_signature_from_def(node, shown, defaults=defaults))
    return result


def _runtime_members():
    """Yield (qualified name, class name, attribute, kind, signatures).

    Only what C++ binds is yielded. A method that pikepdf._methods replaced
    with a Python function has no nanobind signature, so it is not compared
    with the stub: there, the stub describes the Python function.
    """
    for name in dir(_core):
        func = getattr(_core, name)
        if hasattr(func, '__nb_signature__'):
            yield name, None, name, 'function', _runtime_signatures(func)
    for cls_name, cls in _runtime_classes():
        for attr, value in vars(cls).items():
            qualname = f'{cls_name}.{attr}'
            if isinstance(value, property):
                if not hasattr(value.fget, '__nb_signature__'):
                    continue
                yield (
                    qualname,
                    cls_name,
                    attr,
                    'getter',
                    _runtime_signatures(value.fget),
                )
                if value.fset is None:
                    yield qualname, cls_name, attr, 'no setter', []
                else:
                    signatures = _runtime_signatures(value.fset)
                    yield qualname, cls_name, attr, 'setter', signatures
                continue
            func = getattr(value, '__func__', value)
            if not hasattr(func, '__nb_signature__'):
                continue
            signatures = []
            for signature in _runtime_signatures(func):
                # nanobind names the receiver of every method it binds `self`,
                # and the class methods are lambdas whose first parameter is
                # `cls`. Anything else was bound with def_static.
                receiver = signature.params[0].name if signature.params else None
                if receiver in ('self', 'cls'):
                    signature = signature.without_receiver()
                is_static = receiver != 'self' and attr != '__new__'
                signatures.append(replace(signature, is_static=is_static))
            yield qualname, cls_name, attr, 'method', signatures


@dataclass
class _StubClass:
    name: str
    bases: list[str]
    functions: dict[str, list[ast.FunctionDef]] = field(default_factory=dict)
    attributes: dict[str, ast.expr] = field(default_factory=dict)


@dataclass
class _Stubs:
    classes: dict[str, _StubClass] = field(default_factory=dict)
    functions: dict[str, list[ast.FunctionDef]] = field(default_factory=dict)
    paths: dict[int, Path] = field(default_factory=dict)  # id(def) -> stub file

    @classmethod
    def load(cls) -> _Stubs:
        """Index every stub in the package.

        The runtime module is flat and _core/__init__.pyi only re-exports, under
        the same names, what the other stubs declare, so declarations are looked
        up by name across all of them.
        """
        stubs = cls()
        for path in sorted(STUB_DIR.glob('*.pyi')):
            tree = ast.parse(path.read_text(encoding='utf-8'))
            for node in tree.body:
                if isinstance(node, ast.FunctionDef):
                    stubs.functions.setdefault(node.name, []).append(node)
                    stubs.paths[id(node)] = path
                elif isinstance(node, ast.ClassDef):
                    stubs._add_class(node, path)
        return stubs

    def _add_class(self, node: ast.ClassDef, path: Path) -> None:
        stub_class = _StubClass(node.name, [_base_name(b) for b in node.bases])
        for item in node.body:
            if isinstance(item, ast.FunctionDef):
                stub_class.functions.setdefault(item.name, []).append(item)
                self.paths[id(item)] = path
            elif isinstance(item, ast.AnnAssign) and isinstance(item.target, ast.Name):
                stub_class.attributes[item.target.id] = item.annotation
        self.classes[node.name] = stub_class

    def find(self, cls_name: str | None, attr: str):
        """Return the stub's function definitions or attribute annotation.

        Returns None if the stub inherits the member from a class that is not
        itself a stub, such as collections.abc.MutableMapping.
        """
        if cls_name is None:
            return self.functions.get(attr)
        stub_class = self.classes.get(cls_name)
        if stub_class is None:
            return None
        if attr in stub_class.functions:
            return stub_class.functions[attr]
        if attr in stub_class.attributes:
            return stub_class.attributes[attr]
        for base in stub_class.bases:
            found = self.find(base, attr)
            if found is not None:
                return found
        return None

    def ancestors(self, cls_name: str) -> set:
        """Return the stub class names and real classes a stub class derives from."""
        result: set = {cls_name}
        if cls_name in _IMPLICIT_BASES:
            result.add(_IMPLICIT_BASES[cls_name])
        for base in self.classes[cls_name].bases:
            if base in self.classes:
                result |= self.ancestors(base)
            else:
                real = _real_class(base)
                if real is not None:
                    result.add(real)
        return result

    def describe(self, node: ast.FunctionDef) -> str:
        """Return the ``def`` line of a declaration and where it is."""
        bare = ast.FunctionDef(
            name=node.name,
            args=node.args,
            body=[ast.Pass()],
            decorator_list=[],
            returns=node.returns,
            lineno=node.lineno,
            col_offset=0,
        )
        line = ast.unparse(bare).removesuffix(':\n    pass')
        return f'{line}  [{self.paths[id(node)].name}:{node.lineno}]'


def _decorators(node: ast.FunctionDef) -> set[str]:
    return {ast.unparse(d).rsplit('.', maxsplit=1)[-1] for d in node.decorator_list}


def _real_class(dotted: str):
    name = dotted.rsplit('.', maxsplit=1)[-1]
    for namespace in _TYPE_NAMESPACES:
        found = getattr(namespace, name, None)
        if isinstance(found, type):
            return found
    return None


def _union_members(annotation: ast.expr) -> list[ast.expr]:
    if isinstance(annotation, ast.Constant) and isinstance(annotation.value, str):
        annotation = ast.parse(annotation.value, mode='eval').body
    if isinstance(annotation, ast.BinOp) and isinstance(annotation.op, ast.BitOr):
        return _union_members(annotation.left) + _union_members(annotation.right)
    if isinstance(annotation, ast.Subscript):
        head = ast.unparse(annotation.value).rsplit('.', maxsplit=1)[-1]
        inner = annotation.slice
        if head in ('ClassVar', 'Final'):
            return _union_members(inner)
        if head == 'Optional':
            return [*_union_members(inner), ast.Constant(None)]
        if head == 'Union':
            elts = inner.elts if isinstance(inner, ast.Tuple) else [inner]
            return [m for elt in elts for m in _union_members(elt)]
    return [annotation]


def _types(stubs: _Stubs, annotation: ast.expr | None) -> list:
    """Reduce an annotation to the classes at the top level of its union.

    A class the stubs declare is represented by its name and any other by the
    class itself. A type that is neither (a type variable, an alias, Any,
    object, Literal, a missing annotation) is _UNKNOWN. Type arguments are
    dropped, so list[Page] is list.
    """
    if annotation is None:
        return [_UNKNOWN]
    result: list = []
    for member in _union_members(annotation):
        if isinstance(member, ast.Constant) and member.value is None:
            result.append(type(None))
            continue
        if isinstance(member, ast.Subscript):
            member = member.value
        if not isinstance(member, ast.Name | ast.Attribute):
            result.append(_UNKNOWN)
            continue
        name = ast.unparse(member).rsplit('.', maxsplit=1)[-1]
        if name in stubs.classes:
            result.append(name)
        else:
            real = _real_class(name)
            result.append(_UNKNOWN if real in (None, object) else real)
    return result


def _agree(stubs: _Stubs, a, b) -> bool:
    """Tell whether one type could be the other, or a subtype of it."""
    if a is _UNKNOWN or b is _UNKNOWN or a == b:
        return True
    if isinstance(a, str) and isinstance(b, str):
        return a in stubs.ancestors(b) or b in stubs.ancestors(a)
    if isinstance(a, str) or isinstance(b, str):
        stub_name, real = (a, b) if isinstance(a, str) else (b, a)
        return any(
            isinstance(ancestor, type)
            and (issubclass(ancestor, real) or issubclass(real, ancestor))
            for ancestor in stubs.ancestors(stub_name)
        )
    if a in _NUMERIC_TOWER and b in _NUMERIC_TOWER:
        return True
    return issubclass(a, b) or issubclass(b, a)


def _type_names(type_list: list) -> str:
    return ' | '.join(
        '?' if t is _UNKNOWN else t if isinstance(t, str) else t.__name__
        for t in type_list
    )


def _compare_return(stubs: _Stubs, runtime: ast.expr | None, stub: ast.expr | None):
    runtime_types, stub_types = _types(stubs, runtime), _types(stubs, stub)
    for runtime_type in runtime_types:
        if runtime_type == 'Object' and set(stub_types) & _OBJECT_RETURNED_AS:
            continue
        if not any(_agree(stubs, runtime_type, s) for s in stub_types):
            yield (
                f'C++ can return {_type_names([runtime_type])}, which the stub '
                f'return type ({_type_names(stub_types)}) does not include'
            )


def _compare_param_type(
    stubs: _Stubs, name: str, runtime: ast.expr | None, stub: ast.expr | None
):
    runtime_types, stub_types = _types(stubs, runtime), _types(stubs, stub)
    if not any(_agree(stubs, r, s) for r in runtime_types for s in stub_types):
        yield (
            f'parameter {name!r}: C++ takes {_type_names(runtime_types)}, the stub '
            f'takes {_type_names(stub_types)}'
        )
    elif type(None) in stub_types and not any(
        t is _UNKNOWN or t is type(None) for t in runtime_types
    ):
        yield f'parameter {name!r}: the stub accepts None, C++ does not'


def _compare_default(runtime: _Signature, r: _Param, s: _Param):
    if s.default is None or r.default is None or ast.unparse(s.default) == '...':
        return
    assert isinstance(r.default, ast.Name)
    value = runtime.defaults[int(r.default.id.removeprefix('_default_'))]
    try:
        stub_value = ast.literal_eval(s.default)
    except ValueError:
        return  # not a literal: an enum member, say
    if type(value) is not type(stub_value) or value != stub_value:
        yield (
            f'parameter {s.name!r}: the default is {value!r} in C++, '
            f'{stub_value!r} in the stub'
        )


def _fit(
    stubs: _Stubs, stub: _Signature, runtime: _Signature, *, dunder: bool
) -> tuple[list[str], dict[int, _Param]]:
    """Check that every call a stub declaration allows is one an overload accepts.

    Returns the reasons it is not, and the stub parameter that corresponds to
    each parameter of the overload, by its index.
    """
    problems: list[str] = []
    bound: dict[int, _Param] = {}

    def bind(index: int, s: _Param) -> None:
        r = runtime.params[index]
        bound[index] = s
        problems.extend(_compare_default(runtime, r, s))
        problems.extend(_compare_param_type(stubs, s.name, r.annotation, s.annotation))

    positional = [i for i, r in enumerate(runtime.params) if r.is_positional]
    for n, s in enumerate(p for p in stub.params if p.is_positional):
        if n >= len(positional):
            if not runtime.has('var'):
                problems.append(
                    f'parameter {s.name!r}: C++ takes only {len(positional)} '
                    'positional parameter(s)'
                )
            continue
        r = runtime.params[positional[n]]
        if s.kind == 'standard':
            if r.kind == 'positional':
                # By convention the parameters of special methods are
                # positional whether or not a stub marks them so.
                if not dunder:
                    problems.append(
                        f'parameter {s.name!r}: positional-only in C++, but the '
                        'stub allows passing it by keyword'
                    )
            elif r.name != s.name:
                problems.append(f'parameter {s.name!r} is named {r.name!r} in C++')
        bind(positional[n], s)

    for s in stub.params:
        if s.kind != 'keyword':
            continue
        matches = [
            i
            for i, r in enumerate(runtime.params)
            if r.name == s.name and r.kind in ('standard', 'keyword') and i not in bound
        ]
        if matches:
            bind(matches[0], s)
            if s.default is not None and runtime.params[matches[0]].default is None:
                problems.append(
                    f'parameter {s.name!r}: optional in the stub, required in C++'
                )
        elif not runtime.has('varkw'):
            problems.append(f'parameter {s.name!r}: C++ has no such keyword parameter')

    for kind, spelling in (('var', '*'), ('varkw', '**')):
        if stub.has(kind) and not runtime.has(kind):
            name = next(p.name for p in stub.params if p.kind == kind)
            problems.append(f'C++ does not take {spelling}{name}')
    for i, r in enumerate(runtime.params):
        if i not in bound and r.kind not in ('var', 'varkw') and r.default is None:
            problems.append(f'C++ requires parameter {r.name!r}, which the stub omits')
    problems.extend(_compare_return(stubs, runtime.returns, stub.returns))
    return problems, bound


def _stub_signatures(stubs: _Stubs, nodes, *, in_class: bool) -> list[_Signature]:
    """Return the ways a member can be called according to its declarations.

    A declaration with optional positional parameters stands for one way of
    calling it per number of arguments, which is how the stubs merge overloads
    such as ``f()`` and ``f(x)`` into ``f(x=...)``. Each is returned as a
    signature in which the arguments left out are absent.
    """
    nodes = [n for n in nodes if 'overload' in _decorators(n)] or nodes[-1:]
    result = []
    for node in nodes:
        decorators = _decorators(node)
        signature = _signature_from_def(node, stubs.describe(node))
        if in_class and 'staticmethod' not in decorators:
            signature = signature.without_receiver()
        if node.name != '__new__' and decorators & {'staticmethod', 'classmethod'}:
            signature = replace(signature, is_static=True)

        positional = [p for p in signature.params if p.is_positional]
        keywords = [p for p in signature.params if p.kind == 'keyword']
        required = sum(1 for p in positional if p.default is None)
        for count in range(required, len(positional) + 1):
            text = signature.text
            if required != len(positional):
                text += f', with {count} positional argument(s)'
            params = (*positional[:count], *keywords)
            result.append(replace(signature, params=params, text=text))
        if signature.has('var') or signature.has('varkw'):
            result.append(signature)
    return result


def _compare_member(stubs: _Stubs, cls_name, attr, kind, runtime) -> tuple[int, str]:
    """Compare one bound member with its stub.

    Returns the number of signatures compared and a description of the
    mismatches, which is empty if there are none.
    """
    found = stubs.find(cls_name, attr)
    if found is None:
        return 0, ''  # inherited from a class outside the stubs, or undeclared
    if kind not in ('method', 'function'):
        return _compare_property(stubs, attr, kind, runtime, found)
    if not isinstance(found, list):
        return 0, '    - a function in C++, an attribute in the stub'
    if any('property' in _decorators(node) for node in found):
        return 0, '    - a method in C++, a property in the stub'

    declared = _stub_signatures(stubs, found, in_class=cls_name is not None)
    lines = []
    if runtime[0].is_static != declared[0].is_static:
        lines.append(
            f'    - {"static" if runtime[0].is_static else "not static"} in C++, '
            f'{"static" if declared[0].is_static else "not static"} in the stub'
        )
    dunder = attr.startswith('__') and attr.endswith('__')
    fits = [[_fit(stubs, s, r, dunder=dunder) for r in runtime] for s in declared]

    def report(first: str, second: str, problems: list[str]) -> None:
        block = [f'    {first}', f'    {second}', *(f'    - {p}' for p in problems)]
        if block[2:] and not set(block) <= set(lines):
            lines.extend(block)

    # Soundness: each declaration fits some overload.
    for s, row in zip(declared, fits, strict=True):
        if all(problems for problems, _bound in row):
            closest = min(range(len(runtime)), key=lambda i: len(row[i][0]))
            report(f'stub: {s.text}', f'C++:  {runtime[closest].text}', row[closest][0])
    # Completeness: each overload, and each of its parameters, is declared.
    for i, r in enumerate(runtime):
        fitting = [row[i][1] for row in fits if not row[i][0]]
        if not fitting:
            closest = min(range(len(declared)), key=lambda j: len(fits[j][i][0]))
            problems = fits[closest][i][0]
        else:
            problems = []
            for index, param in enumerate(r.params):
                if param.kind in ('var', 'varkw'):
                    continue
                uses = [bound.get(index) for bound in fitting]
                if all(use is None for use in uses):
                    problems.append(
                        f'parameter {param.name!r} of C++ is not declared in the stub'
                    )
                elif param.default is not None and all(
                    use is not None and use.default is None for use in uses
                ):
                    problems.append(
                        f'parameter {param.name!r}: has a default in C++, '
                        'required in the stub'
                    )
            closest = next(j for j, row in enumerate(fits) if not row[i][0])
        report(f'C++:  {r.text}', f'stub: {declared[closest].text}', problems)
    return len(runtime), '\n'.join(lines)


def _compare_property(stubs: _Stubs, attr, kind, runtime, found) -> tuple[int, str]:
    if not isinstance(found, list):  # declared as a plain attribute, `name: type`
        annotation = ast.unparse(found)
        if kind == 'no setter':
            if annotation.startswith(('ClassVar[', 'Final[')):
                return 0, ''  # a constant
            return 0, '    - read-only in C++, a writable attribute in the stub'
        (signature,) = runtime
        if kind == 'getter':
            problems = list(_compare_return(stubs, signature.returns, found))
        else:
            value = signature.params[-1]
            problems = list(_compare_param_type(stubs, attr, value.annotation, found))
        text = f'{attr}: {annotation}'
    else:
        getters = [n for n in found if 'property' in _decorators(n)]
        setters = [n for n in found if 'setter' in _decorators(n)]
        if not getters:
            if kind == 'getter':
                return 0, '    - a property in C++, a method in the stub'
            return 0, ''
        if kind == 'no setter':
            if setters:
                return 0, '    - read-only in C++, has a setter in the stub'
            return 0, ''
        (signature,) = runtime
        if kind == 'getter':
            node = getters[0]
            problems = list(_compare_return(stubs, signature.returns, node.returns))
        elif not setters:
            return 0, '    - has a setter in C++, read-only in the stub'
        else:
            node = setters[0]
            problems = list(
                _compare_param_type(
                    stubs,
                    attr,
                    signature.params[-1].annotation,
                    node.args.args[-1].annotation,
                )
            )
        text = stubs.describe(node)
    if not problems:
        return 1, ''
    lines = [f'    C++ {kind}: {runtime[0].text}', f'    stub: {text}']
    lines.extend(f'    - {problem}' for problem in problems)
    return 1, '\n'.join(lines)


def _signature_mismatches() -> tuple[int, dict[str, str]]:
    stubs = _Stubs.load()
    checked = 0
    mismatches: dict[str, list[str]] = {}
    for qualname, cls_name, attr, kind, runtime in _runtime_members():
        count, report = _compare_member(stubs, cls_name, attr, kind, runtime)
        checked += count
        if report:
            mismatches.setdefault(qualname, []).append(report)
    return checked, {name: '\n'.join(parts) for name, parts in mismatches.items()}


@pytest.mark.parametrize(
    'stub, runtime, expected',
    [
        # What the stubs may do.
        ('def f(a: int) -> None', 'def f(a: int) -> None', None),
        ('def f(a, /) -> None', 'def f(arg: int, /) -> None', None),
        ('def f(a, /) -> None', 'def f(ugly: int) -> None', None),
        ('def f(a: Page) -> Page', 'def f(a: object) -> object', None),
        ('def f(a: str | Name) -> None', 'def f(a: str) -> None', None),
        ('def f(a: int = ...)', 'def f(a: int = \\0) -> None', None),
        ('def f(a: int = 3)', 'def f(a: int = \\0) -> None', None),
        ('def f(a) -> int | None', 'def f(a) -> pikepdf.objects.Object', None),
        ('def f(a, /)', 'def f(a, b=\\0)', None),
        ('def f(*, k: bool = False)', 'def f(*, k: bool = \\1)', None),
        # What they may not.
        ('def f(a: int) -> None', 'def f(b: int) -> None', "named 'b' in C++"),
        ('def f(a: int) -> None', 'def f(arg: int, /) -> None', 'positional-only'),
        ('def f(a, b) -> None', 'def f(a) -> None', 'only 1 positional'),
        ('def f(a) -> None', 'def f(a, b) -> None', "requires parameter 'b'"),
        ('def f(*, k: int)', 'def f(a=\\0)', 'no such keyword'),
        ('def f(*, k: int = ...)', 'def f(*, k: int)', 'optional in the stub'),
        ('def f(a: int = 4)', 'def f(a: int = \\0) -> None', 'default is 3'),
        ('def f(*args)', 'def f(a)', 'does not take *args'),
        ('def f(a: str) -> None', 'def f(a: int) -> None', 'C++ takes int'),
        ('def f(a: Page | None)', 'def f(a: pikepdf._core.Page)', 'accepts None'),
        ('def f() -> None', 'def f() -> bool', 'C++ can return bool'),
        ('def f() -> Page', 'def f() -> pikepdf._core.Page | None', 'NoneType'),
        ('def f() -> str', 'def f() -> pikepdf.objects.Object', 'return Object'),
    ],
)
def test_signature_comparison(stub, runtime, expected):
    """The comparison itself accepts and rejects what it is meant to."""
    stubs = _Stubs.load()
    node = ast.parse(stub + ': ...').body[0]
    assert isinstance(node, ast.FunctionDef)
    func = SimpleNamespace(__nb_signature__=((runtime, None, (3, False)),))
    (runtime_signature,) = _runtime_signatures(func)
    problems, _bound = _fit(
        stubs, _signature_from_def(node, stub), runtime_signature, dunder=False
    )
    if expected is None:
        assert not problems
    else:
        assert any(expected in problem for problem in problems), problems


def test_cpp_signatures_match_stubs():
    checked, mismatches = _signature_mismatches()

    # Guard against the comparison quietly finding nothing to compare.
    assert checked > 500

    unexpected = sorted(set(mismatches) - set(SIGNATURE_ALLOWLIST))
    assert not unexpected, (
        f'{len(unexpected)} C++ binding(s) disagree with the _core stubs:\n\n'
        + '\n\n'.join(f'{name}\n{mismatches[name]}' for name in unexpected)
    )
    stale = sorted(set(SIGNATURE_ALLOWLIST) - set(mismatches))
    assert not stale, 'No longer needed in SIGNATURE_ALLOWLIST: ' + ', '.join(stale)
