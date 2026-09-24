#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 James R. Barlow
# SPDX-License-Identifier: MPL-2.0

"""Import veraPDF PDF/A-1b/2b/3b validation profiles into a JSON rule catalogue.

The veraPDF validation profiles are published by the veraPDF Consortium under
CC BY 4.0. This script reads them either from a directory containing
``PDFA-1B.xml``, ``PDFA-2B.xml`` and ``PDFA-3B.xml`` (as found in a checkout of
veraPDF-validation-profiles, or extracted from a veraPDF jar), or directly from
a veraPDF jar file, and writes ``src/pikepdf/pdfa/data/verapdf_rules.json``.

Usage:
    python misc/import_verapdf_profiles.py <dir-or-jar> [-o output.json]
"""

from __future__ import annotations

import argparse
import json
import sys
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

NS = {'v': 'http://www.verapdf.org/ValidationProfile'}
PROFILES = ('PDFA-1B.xml', 'PDFA-2B.xml', 'PDFA-3B.xml')
JAR_PREFIX = 'org/verapdf/pdfa/validation/'
DEFAULT_OUTPUT = (
    Path(__file__).resolve().parent.parent
    / 'src'
    / 'pikepdf'
    / 'pdfa'
    / 'data'
    / 'verapdf_rules.json'
)


def _text(elem: ET.Element | None) -> str:
    if elem is None or elem.text is None:
        return ''
    return ' '.join(elem.text.split())


def read_profiles(source: Path) -> dict[str, bytes]:
    """Return the raw XML of each profile, keyed by profile filename."""
    result: dict[str, bytes] = {}
    if source.is_dir():
        for name in PROFILES:
            candidates = list(source.rglob(name))
            if not candidates:
                sys.exit(f"{name} not found under {source}")
            result[name] = candidates[0].read_bytes()
    else:
        with zipfile.ZipFile(source) as zf:
            for name in PROFILES:
                result[name] = zf.read(JAR_PREFIX + name)
    return result


def parse_profile(xml: bytes) -> tuple[dict, dict[str, dict]]:
    """Parse one profile into its details and rules keyed by rule id."""
    root = ET.fromstring(xml)
    details_elem = root.find('v:details', NS)
    details = {
        'flavour': root.get('flavour', ''),
        'name': _text(root.find('v:details/v:name', NS)),
        'description': _text(root.find('v:details/v:description', NS)),
        'creator': details_elem.get('creator', '') if details_elem is not None else '',
        'created': details_elem.get('created', '') if details_elem is not None else '',
    }
    rules: dict[str, dict] = {}
    for rule in root.iterfind('v:rules/v:rule', NS):
        id_elem = rule.find('v:id', NS)
        assert id_elem is not None
        rule_id = (
            f"{id_elem.get('specification')}:{id_elem.get('clause')}"
            f"-{id_elem.get('testNumber')}"
        )
        rules[rule_id] = {
            'object': rule.get('object', ''),
            'description': _text(rule.find('v:description', NS)),
            'test': _text(rule.find('v:test', NS)),
            'error': _text(rule.find('v:error/v:message', NS)),
        }
    return details, rules


def main(argv: list[str] | None = None) -> None:
    """Run the command line."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        'source', type=Path, help="directory of profile XMLs or a veraPDF jar"
    )
    parser.add_argument('-o', '--output', type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args(argv)

    profiles = read_profiles(args.source)
    all_rules: dict[str, dict] = {}
    profile_details: dict[str, dict] = {}
    for name, xml in profiles.items():
        details, rules = parse_profile(xml)
        profile_details[name] = details
        for rule_id, rule in rules.items():
            existing = all_rules.get(rule_id)
            if existing is not None and existing != rule:
                sys.exit(f"Conflicting definitions for {rule_id}")
            all_rules[rule_id] = rule

    catalogue = {
        'source': {
            'title': "veraPDF validation profiles",
            'copyright': "veraPDF Consortium",
            'license': "CC BY 4.0",
            'url': "https://github.com/veraPDF/veraPDF-validation-profiles",
            'imported_from': args.source.name,
            'profiles': profile_details,
        },
        'rules': dict(sorted(all_rules.items(), key=lambda kv: _sort_key(kv[0]))),
    }
    args.output.write_text(
        json.dumps(catalogue, indent=1, ensure_ascii=False) + '\n', encoding='utf-8'
    )
    print(f"Wrote {len(all_rules)} rules to {args.output}")


def _sort_key(rule_id: str) -> tuple:
    spec, rest = rule_id.split(':', 1)
    clause, test = rest.rsplit('-', 1)
    return (spec, tuple(int(p) for p in clause.split('.')), int(test))


if __name__ == '__main__':
    main()
