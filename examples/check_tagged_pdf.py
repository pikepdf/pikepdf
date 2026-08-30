# SPDX-FileCopyrightText: 2026 Khushwant Parihar
# SPDX-License-Identifier: MIT

"""Use pikepdf to report the logical structure of a tagged PDF.

Run as: python examples/check_tagged_pdf.py file.pdf [...]
Exits non-zero if any file has structural problems.
"""

from __future__ import annotations

import sys
from collections import Counter

from pikepdf import Name, ObjectRef, Pdf


def describe(filename: str) -> int:
    with Pdf.open(filename) as pdf:
        tree = pdf.open_structure_tree()
        if not tree.exists:
            print(f"{filename}: not a tagged PDF")
            return 0

        elements = list(tree.walk())
        tags = Counter(str(elem.obj.get(Name.S)) for elem in elements)
        content = sum(len(elem.content) for elem in elements)
        objects = sum(
            1 for elem in elements for kid in elem.kids if isinstance(kid, ObjectRef)
        )

        print(f"{filename}")
        print(f"  marked as tagged: {tree.marked}")
        print(f"  elements:         {len(elements)}")
        print(f"  content refs:     {content}")
        print(f"  object refs:      {objects}")
        print(f"  parent tree keys: {len(tree.parent_tree.keys())}")
        print(f"  structure types:  {dict(tags.most_common(8))}")

        problems = tree.validate()
        if not problems:
            print("  validate():       no problems")
            return 0
        print(f"  validate():       {len(problems)} problem(s)")
        for problem in problems:
            print(f"    - {problem}")
        return 1


if __name__ == '__main__':
    if len(sys.argv) < 2:
        print(__doc__)
        raise SystemExit(2)
    raise SystemExit(max(describe(name) for name in sys.argv[1:]))
