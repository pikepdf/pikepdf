# SPDX-FileCopyrightText: 2026 James R. Barlow
# SPDX-License-Identifier: MPL-2.0

"""Resolve type references that name pikepdf's private extension module.

pikepdf._core is a single extension module at runtime, but its type stubs are
split into one submodule per C++ translation unit (see
src/pikepdf/_core/__init__.pyi). sphinx-autoapi reads those stubs, so a type
that this documentation publishes as ``pikepdf.Object`` reaches Sphinx as
``pikepdf._core._object.Object``, which resolves to nothing and renders as that
whole private path.

Retarget any such reference at the name the documentation does publish, and
render it under its bare class name, the way an annotation naming a type from
its own module always did. A name the documentation does not publish at all --
a type variable, say -- keeps its bare name without becoming a link.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from docutils import nodes

if TYPE_CHECKING:
    from docutils.nodes import Element, Node, TextElement
    from sphinx.addnodes import pending_xref
    from sphinx.application import Sphinx
    from sphinx.environment import BuildEnvironment

PRIVATE_PREFIX = 'pikepdf._core.'


def _shortened(contnode: TextElement, name: str) -> TextElement:
    """Copy ``contnode`` with its text replaced by ``name``."""
    short = contnode.deepcopy()
    if isinstance(short, nodes.Text):
        return nodes.Text(name)
    del short[:]
    short += nodes.Text(name)
    return short


def missing_reference(
    app: Sphinx,
    env: BuildEnvironment,
    node: pending_xref,
    contnode: TextElement,
) -> Element | None:
    """Retry an unresolved pikepdf._core reference under its published name."""
    if node.get('refdomain') != 'py':
        return None
    target = node.get('reftarget', '')
    if not target.startswith(PRIVATE_PREFIX):
        return None
    name = target.rpartition('.')[2]
    domain = env.domains['py']
    for candidate in (f'pikepdf.{name}', f'{PRIVATE_PREFIX}{name}'):
        if candidate == target:
            continue
        node['reftarget'] = candidate
        found = domain.resolve_xref(
            env,
            node.get('refdoc', ''),
            app.builder,
            node.get('reftype', 'class'),
            candidate,
            node,
            _shortened(contnode, name),
        )
        if found is not None:
            return found
    # Nothing published under that name -- a type variable, or a class pikepdf
    # keeps private. Drop the private path anyway and show the bare name.
    node['reftarget'] = target
    return _shortened(contnode, name)


def setup(app: Sphinx) -> dict[str, Node | bool]:
    app.connect('missing-reference', missing_reference)
    return {'parallel_read_safe': True, 'parallel_write_safe': True}
