# SPDX-FileCopyrightText: 2026 James R. Barlow
# SPDX-License-Identifier: MPL-2.0

"""Per-role JSON Schemas for shallow PDF objects.

Each PDF/A flavour has a schema file whose ``$defs`` override roles from
``common.json``. A role's schema checks the shallow JSON encoding of one
object; annotations (``x-children``, ``x-kind``, ``x-dispatch``) tell the
walker how to continue through the object graph, and ``x-verapdf``,
``x-unsupported``, ``x-closed`` and ``x-message`` turn schema errors into
findings.

A key that a role does not list is reported as unsupported, since PDF
permits private and future keys and the validator cannot know what they
mean. Only roles marked ``x-closed``, whose unlisted keys PDF/A itself
forbids, report them as violations.
"""

from __future__ import annotations

import ast
import re
from collections.abc import Iterable
from functools import cache
from typing import TYPE_CHECKING, Any, NamedTuple

from jsonschema import Draft202012Validator
from jsonschema.exceptions import ValidationError
from referencing import Registry, Resource
from referencing.jsonschema import DRAFT202012

from pikepdf.pdfa._catalogue import load_json
from pikepdf.pdfa._context import ValidationContext
from pikepdf.pdfa._flavour import Flavour
from pikepdf.pdfa._report import FindingKind

if TYPE_CHECKING:
    from referencing._core import Resolver

    from pikepdf.pdfa._shallow import JsonValue

BASE_URI = 'https://pikepdf.invalid/pdfa/'
COMMON = 'common.json'
MAX_MESSAGE = 300
CLOSING_KEYWORDS = frozenset({'additionalProperties', 'unevaluatedProperties'})

# jsonschema reports unexpected keys as the reprs of the key strings, e.g.
# "Additional properties are not allowed ('/Foo', '/Bar' were unexpected)"
_UNEXPECTED = re.compile(r"\((.*) (?:was|were) unexpected\)$", re.DOTALL)
_STRING_LITERAL = re.compile(r"'(?:[^'\\]|\\.)*'" r'|"(?:[^"\\]|\\.)*"')


def unrecognized_keys(error: ValidationError) -> list[str]:
    """Return the unexpected keys named by an unexpected-properties error.

    Parses jsonschema's message for ``additionalProperties: false`` or
    ``unevaluatedProperties: false``. Returns an empty list if the message
    is not in the expected format.
    """
    match = _UNEXPECTED.search(error.message)
    if match is None:
        return []
    keys = []
    for literal in _STRING_LITERAL.findall(match.group(1)):
        try:
            key = ast.literal_eval(literal)
        except (ValueError, SyntaxError):
            return []
        keys.append(str(key))
    return keys


class ChildSpec(NamedTuple):
    """How to follow one key of a role to a child object."""

    role: str
    each: bool = False
    sibling: bool = False
    values: bool = False


class Dispatch(NamedTuple):
    """Select a more specific role from the value of a key."""

    key: str
    roles: dict[str, str]


def _load_schema(name: str) -> Any:
    return load_json('schemas', name)


def _format_path(path: Iterable[str | int]) -> str:
    parts = []
    for element in path:
        parts.append(f'[{element}]' if isinstance(element, int) else str(element))
    return ''.join(parts)


class SchemaSet:
    """The role schemas of one PDF/A flavour."""

    def __init__(self, flavour: Flavour):
        """Load ``common.json`` and the flavour's schema file."""
        self.flavour = flavour
        self._flavour_file = f'pdfa-{flavour.value}.json'
        common = _load_schema(COMMON)
        specific = _load_schema(self._flavour_file)
        self._defs: dict[str, dict[str, Any]] = {
            COMMON: common['$defs'],
            self._flavour_file: specific['$defs'],
        }
        self._registry: Registry = Registry().with_resources(
            [
                (
                    BASE_URI + COMMON,
                    Resource.from_contents(common, default_specification=DRAFT202012),
                ),
                (
                    BASE_URI + self._flavour_file,
                    Resource.from_contents(specific, default_specification=DRAFT202012),
                ),
            ]
        )
        self._validators: dict[str, Draft202012Validator] = {}
        self._annotation_nodes: dict[str, list[dict[str, Any]]] = {}

    @classmethod
    @cache
    def for_flavour(cls, flavour: Flavour | str) -> SchemaSet:
        """Return the (cached) schema set for a flavour."""
        return cls(Flavour(flavour))

    def roles(self) -> set[str]:
        """Return the names of all roles (``$defs`` starting with a capital)."""
        return {
            name for defs in self._defs.values() for name in defs if name[:1].isupper()
        }

    def _role_uri(self, role: str) -> str:
        if role in self._defs[self._flavour_file]:
            return f'{BASE_URI}{self._flavour_file}#/$defs/{role}'
        if role in self._defs[COMMON]:
            return f'{BASE_URI}{COMMON}#/$defs/{role}'
        raise KeyError(f"unknown role {role!r}")

    def _validator(self, role: str) -> Draft202012Validator:
        validator = self._validators.get(role)
        if validator is None:
            validator = Draft202012Validator(
                {'$ref': self._role_uri(role)}, registry=self._registry
            )
            self._validators[role] = validator
        return validator

    # --- annotations -------------------------------------------------------

    def _nodes(self, role: str) -> list[dict[str, Any]]:
        """Return the schema nodes of a role, base definitions first.

        Follows ``$ref`` and ``$ref`` items of ``allOf``, so a flavour role
        that composes the common role inherits its annotations.
        """
        cached = self._annotation_nodes.get(role)
        if cached is not None:
            return cached
        nodes: list[dict[str, Any]] = []
        resolved = self._registry.resolver().lookup(self._role_uri(role))

        def gather(node: object, resolver: Resolver[Any], depth: int) -> None:
            if not isinstance(node, dict) or depth > 16:
                return
            if '$ref' in node:
                sub = resolver.lookup(node['$ref'])
                gather(sub.contents, sub.resolver, depth + 1)
            for item in node.get('allOf', []):
                gather(item, resolver, depth + 1)
            nodes.append(node)

        gather(resolved.contents, resolved.resolver, 0)
        self._annotation_nodes[role] = nodes
        return nodes

    def children(self, role: str) -> dict[str, ChildSpec]:
        """Return the keys to follow from an object of this role."""
        merged: dict[str, ChildSpec] = {}
        for node in self._nodes(role):
            for key, spec in node.get('x-children', {}).items():
                if isinstance(spec, str):
                    merged[key] = ChildSpec(spec)
                else:
                    merged[key] = ChildSpec(
                        spec['role'],
                        each=bool(spec.get('each', False)),
                        sibling=bool(spec.get('sibling', False)),
                        values=bool(spec.get('values', False)),
                    )
        return merged

    def kind(self, role: str) -> str:
        """Return the pikepdf object kind expected for this role."""
        result = 'dict'
        for node in self._nodes(role):
            result = node.get('x-kind', result)
        return result

    def dispatch(self, role: str) -> Dispatch | None:
        """Return the dispatch rule of a role, if it has one."""
        result = None
        for node in self._nodes(role):
            if 'x-dispatch' in node:
                spec = node['x-dispatch']
                result = Dispatch(spec['key'], dict(spec['roles']))
        return result

    # --- checking ----------------------------------------------------------

    def check(
        self, role: str, shallow: JsonValue, ctx: ValidationContext, where: str
    ) -> bool:
        """Validate the shallow encoding of an object against a role.

        Each schema error becomes a finding in ``ctx.report``.

        Returns:
            True if the object satisfies the role schema.
        """
        errors = list(self._validator(role).iter_errors(shallow))
        for error in errors:
            rule_id, kind, message = self._interpret(role, error)
            location = where
            if error.absolute_path:
                location = f'{where} {_format_path(error.absolute_path)}'
            ctx.deny(rule_id, location, message, kind)
        return not errors

    def _interpret(
        self, role: str, error: ValidationError
    ) -> tuple[str, FindingKind, str]:
        """Find the rule id, kind and message for a schema error.

        Walks the error's schema path from the role's root, following
        ``$ref`` (which jsonschema elides from the path), and uses the
        deepest ``x-verapdf`` id for this flavour, any ``x-unsupported`` on
        the way, and the deepest ``x-message``.

        A key the schema does not list (``additionalProperties`` or
        ``unevaluatedProperties`` is false) is unsupported, unless the schema
        node holding that keyword is marked ``x-closed``. So is an error in
        the value of an unlisted key checked by a non-false
        ``additionalProperties`` schema.
        """
        prefix = self.flavour.spec + ':'
        rule_id: str | None = None
        unsupported = False
        message: str | None = None

        def note(node: object) -> None:
            nonlocal rule_id, unsupported, message
            if not isinstance(node, dict):
                return
            ids = [i for i in node.get('x-verapdf', []) if i.startswith(prefix)]
            if ids:
                rule_id = ids[0]
            if node.get('x-unsupported'):
                unsupported = True
            if 'x-message' in node:
                message = node['x-message']

        resolver: Resolver[Any] = self._registry.resolver()
        node: Any = {'$ref': self._role_uri(role)}
        holder: object = None
        open_value = False
        for element in error.relative_schema_path:
            while isinstance(node, dict) and element not in node and '$ref' in node:
                resolved = resolver.lookup(node['$ref'])
                node, resolver = resolved.contents, resolved.resolver
                note(node)
            holder = node
            try:
                node = node[element]
            except (KeyError, IndexError, TypeError):
                holder = None
                break
            if element == 'additionalProperties' and node is not False:
                open_value = True
            note(node)

        if (
            error.validator in CLOSING_KEYWORDS
            and error.validator_value is False
            and isinstance(holder, dict)
            and not holder.get('x-closed', False)
        ):
            keys = unrecognized_keys(error)
            names = ', '.join(keys) if keys else 'some keys'
            return (
                f'pikepdf:schema-{role}',
                'unsupported',
                _truncate(f"unrecognized key(s) {names} are not checked"),
            )
        if open_value:
            return f'pikepdf:schema-{role}', 'unsupported', _truncate(error.message)

        if message is None:
            if error.validator == 'not' and error.validator_value == {}:
                path = _format_path(error.absolute_path) or 'object'
                message = (
                    f"{path} is not supported by this validator"
                    if unsupported
                    else f"{path} is not permitted"
                )
            else:
                message = error.message
        kind: FindingKind = 'unsupported' if unsupported else 'violation'
        return rule_id or f'pikepdf:schema-{role}', kind, _truncate(message)


def _truncate(message: str) -> str:
    if len(message) > MAX_MESSAGE:
        return message[: MAX_MESSAGE - 3] + '...'
    return message
