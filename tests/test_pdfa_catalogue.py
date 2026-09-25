# SPDX-FileCopyrightText: 2026 James R. Barlow
# SPDX-License-Identifier: MPL-2.0

from __future__ import annotations

import pytest

pytest.importorskip('jsonschema')

import importlib
import json
from collections.abc import Iterator
from typing import Any

from pikepdf.pdfa import Flavour
from pikepdf.pdfa._catalogue import (
    data_file,
    describe_rule,
    load_dispositions,
    load_rules,
)
from pikepdf.pdfa._schemas import SchemaSet

STATUSES = {'implemented', 'writer', 'denied_on_presence', 'not_applicable', 'todo'}


def _walk_annotations(node: Any, key: str) -> Iterator[Any]:
    if isinstance(node, dict):
        if key in node:
            yield node[key]
        for value in node.values():
            yield from _walk_annotations(value, key)
    elif isinstance(node, list):
        for value in node:
            yield from _walk_annotations(value, key)


def _schema_files():
    return sorted(
        (p for p in data_file('schemas').iterdir() if p.name.endswith('.json')),
        key=lambda p: p.name,
    )


def test_catalogue_has_all_three_flavours():
    rules = load_rules()
    specs = {rule_id.split(':')[0] for rule_id in rules}
    assert specs == {'ISO_19005_1', 'ISO_19005_2', 'ISO_19005_3'}
    assert len(rules) > 400


def test_every_rule_has_a_disposition():
    rules = set(load_rules())
    dispositions = load_dispositions()
    assert rules - set(dispositions) == set()
    assert set(dispositions) - rules == set()


def test_disposition_shape():
    for rule_id, disposition in load_dispositions().items():
        assert disposition['status'] in STATUSES, rule_id
        assert disposition.get('by'), rule_id


def test_schema_verapdf_ids_exist():
    rules = load_rules()
    for path in _schema_files():
        schema = json.loads(path.read_text())
        for ids in _walk_annotations(schema, 'x-verapdf'):
            assert isinstance(ids, list), path
            for rule_id in ids:
                assert rule_id in rules, f"{path.name}: {rule_id}"


def test_schema_verapdf_ids_are_checked_rules():
    dispositions = load_dispositions()
    for path in _schema_files():
        schema = json.loads(path.read_text())
        for ids in _walk_annotations(schema, 'x-verapdf'):
            for rule_id in ids:
                assert dispositions[rule_id]['status'] not in {
                    'writer',
                    'not_applicable',
                }, rule_id


@pytest.mark.parametrize('flavour', list(Flavour))
def test_implemented_dispositions_name_known_roles(flavour):
    """Implemented and denied rules must name existing roles or functions.

    ``by`` is a comma-separated list of ``role:<Role>`` and
    ``python:<module>.<attribute>`` references.
    """
    schemas = SchemaSet.for_flavour(flavour)
    roles = schemas.roles()
    for rule_id, disposition in load_dispositions().items():
        if not rule_id.startswith(flavour.spec + ':'):
            continue
        if disposition['status'] not in {'implemented', 'denied_on_presence'}:
            continue
        by = disposition['by']
        for part in by.split(','):
            part = part.strip()
            if part.startswith('role:'):
                assert part.removeprefix('role:') in roles, (rule_id, part)
            elif part.startswith('python:'):
                module, _, func = part.removeprefix('python:').partition('.')
                package = 'pikepdf.pdfa'
                mod = importlib.import_module(
                    package if module == '__init__' else f'{package}.{module}'
                )
                target = mod
                for attr in func.split('.'):
                    target = getattr(target, attr)
            else:
                pytest.fail(f"{rule_id}: cannot interpret {part!r}")


def test_todo_dispositions_name_a_step():
    for rule_id, disposition in load_dispositions().items():
        if disposition['status'] == 'todo':
            assert disposition['by'].startswith('step '), rule_id


def test_describe_rule():
    text = describe_rule('ISO_19005_2:6.2.8-3')
    assert 'Interpolate' in text
    assert 'unknown' in describe_rule('ISO_19005_2:99.99-1').lower()
