# SPDX-FileCopyrightText: 2026 James R. Barlow
# SPDX-License-Identifier: MPL-2.0

"""Role-aware traversal of the PDF object graph.

The walker starts at the trailer, knows the role of every object it reaches,
checks the object's shallow JSON against the role schema and then follows the
keys the schema declares in ``x-children``. Objects whose role is not
recognized are never approved: every key must be allowed by some role.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from typing import Any, NamedTuple

import pikepdf
from pikepdf.pdfa._colour import check_image_colour, resolve_colourspace
from pikepdf.pdfa._content import ContentWalker
from pikepdf.pdfa._context import ValidationContext
from pikepdf.pdfa._cos import check_objects
from pikepdf.pdfa._fonts import finalize_fonts, load_font
from pikepdf.pdfa._icc import COMPONENTS, IccHeader, check_output_profile
from pikepdf.pdfa._limits import check_document_limits
from pikepdf.pdfa._schemas import ChildSpec, SchemaSet
from pikepdf.pdfa._shallow import shallow_json_of

MIN_BOX_SIZE = 3
MAX_BOX_SIZE = 14400
PAGE_BOXES = ('/MediaBox', '/CropBox', '/BleedBox', '/TrimBox', '/ArtBox')
INHERITABLE_BOXES = frozenset({'/MediaBox', '/CropBox'})
ANNOTATION_ROLES = ('LinkAnnot', 'TextAnnot', 'PopupAnnot', 'MarkupAnnot')
MAX_STRUCTURE_ELEMENTS = 1_000_000

# Annotation flags (ISO 32000-1 Table 165)
ANNOT_INVISIBLE = 1
ANNOT_HIDDEN = 2
ANNOT_PRINT = 4
ANNOT_NOVIEW = 32
ANNOT_TOGGLE_NOVIEW = 256


class _Item(NamedTuple):
    obj: Any
    role: str
    depth: int
    where: str


def _kind_of(obj: Any) -> str:
    if isinstance(obj, pikepdf.Stream):
        return 'stream'
    if isinstance(obj, pikepdf.Dictionary):
        return 'dict'
    if isinstance(obj, pikepdf.Array):
        return 'array'
    return 'scalar'


class DocumentWalker:
    """Walk a PDF from its trailer, checking each object against its role.

    Args:
        ctx: Validation context; findings are added to ``ctx.report``.
        schemas: Role schemas for ``ctx.flavour``.
        skip_roles: Roles that are neither checked nor descended into. Meant
            for tests that exercise part of the graph.
    """

    def __init__(
        self,
        ctx: ValidationContext,
        schemas: SchemaSet,
        skip_roles: frozenset[str] = frozenset(),
    ):
        self.ctx = ctx
        self.schemas = schemas
        self.skip_roles = skip_roles
        self._roles_seen: dict[tuple[int, int], str] = {}
        self._stack: list[_Item] = []
        self._hooks: dict[str, Callable[[Any, str, int], None]] = {
            'Catalog': self._on_catalog,
            'OutputIntents': self._on_output_intents,
            'ICCOutputProfile': self._on_output_profile,
            'Page': self._on_page,
            'ImageXObject': self._on_image,
            'TransparencyGroup': self._on_group,
            'ColorSpace': self._on_colour_space,
            'ExtGState': self._on_extgstate,
            'SoftMaskDict': self._on_soft_mask,
            'Font': self._on_font_role,
            'FormXObject': self._on_form,
            'StructTreeRoot': self._on_struct_tree_root,
        }
        for role in ANNOTATION_ROLES:
            self._hooks[role] = self._on_annot
        self.content = ContentWalker(ctx)
        self.content.check_images = 'ImageXObject' not in skip_roles
        self._images: list[tuple[Any, str]] = []

    def walk(self) -> None:
        """Check every object reachable from the trailer, then the glyphs used."""
        self._stack = [_Item(self.ctx.pdf.trailer, 'Trailer', 0, 'trailer')]
        while self._stack:
            self._visit(self._stack.pop())
        self._check_unpainted_images()
        if 'Pages' not in self.skip_roles:
            self._check_page_tree()
        check_document_limits(self.ctx)
        check_objects(self.ctx)
        finalize_fonts(self.ctx)

    # --- traversal ---------------------------------------------------------

    def _visit(self, item: _Item) -> None:
        obj, role, depth, where = item
        ctx = self.ctx
        if role in self.skip_roles:
            return
        if depth > ctx.max_depth:
            ctx.deny(
                'pikepdf:depth',
                where,
                f"object graph nested deeper than {ctx.max_depth}",
                'unsupported',
            )
            return
        if isinstance(obj, pikepdf.Object) and obj.is_indirect:
            key = obj.objgen
            seen_as = self._roles_seen.get(key)
            if seen_as is not None:
                if seen_as != role:
                    ctx.deny(
                        'pikepdf:role-conflict',
                        f'{ctx.describe(obj)} ({role})',
                        f"object already checked as {seen_as}",
                        'unsupported',
                    )
                return
            self._roles_seen[key] = role
            ctx.visited.add(key)
            where = ctx.describe(obj)

        base_where = where
        where = f'{base_where} ({role})'
        shallow: Any
        if role == 'Trailer' and depth == 0:
            shallow = ctx.model.trailer_json(obj)
        else:
            shallow = shallow_json_of(obj, ctx.model)
        while (dispatch := self.schemas.dispatch(role)) is not None:
            if not self._check(role, obj, shallow, where):
                return
            target = dispatch.roles.get(shallow.get(dispatch.key))
            if target is None:
                ctx.deny(
                    f'pikepdf:schema-{role}', where, "cannot determine the object role"
                )
                return
            role = target
            where = f'{base_where} ({role})'
            if role in self.skip_roles:
                return

        if not self._check(role, obj, shallow, where):
            return
        hook = self._hooks.get(role)
        if hook is not None:
            hook(obj, where, depth)
        children = list(self._children(obj, role, depth, where))
        self._stack.extend(reversed(children))

    def _check(self, role: str, obj: Any, shallow: Any, where: str) -> bool:
        expected = self.schemas.kind(role)
        actual = _kind_of(obj)
        if expected != 'any' and expected != actual:
            self.ctx.deny(
                f'pikepdf:schema-{role}',
                where,
                f"expected a {expected}, not a {actual}",
            )
            return False
        return self.schemas.check(role, shallow, self.ctx, where)

    def _children(self, obj: Any, role: str, depth: int, where: str) -> Iterable[_Item]:
        for key, spec in self.schemas.children(role).items():
            if key == '*':
                yield from self._each(obj, spec._replace(values=True), depth, where)
                continue
            if key not in obj:
                continue
            value = obj.get(key)
            if value is None:
                continue
            child_where = f'{where} {key}'
            if spec.each:
                yield from self._each(value, spec, depth, child_where)
            else:
                yield self._child(value, spec, depth, child_where)

    def _each(
        self, value: Any, spec: ChildSpec, depth: int, where: str
    ) -> Iterable[_Item]:
        """Yield each element of an array, or the value itself.

        A dictionary is one child unless *spec* says its values are the
        children (``"values": true``, for maps such as resource categories).
        """
        if isinstance(value, pikepdf.Array):
            for index, element in enumerate(value):
                yield self._child(element, spec, depth, f'{where}[{index}]')
        elif (
            spec.values
            and isinstance(value, pikepdf.Dictionary)
            and not isinstance(value, pikepdf.Stream)
        ):
            for key, element in value.items():
                yield self._child(element, spec, depth, f'{where}{key}')
        else:
            yield self._child(value, spec, depth, where)

    @staticmethod
    def _child(value: Any, spec: ChildSpec, depth: int, where: str) -> _Item:
        return _Item(value, spec.role, depth if spec.sibling else depth + 1, where)

    # --- hooks -------------------------------------------------------------

    def _on_catalog(self, obj: Any, where: str, depth: int) -> None:
        if '/OutputIntents' not in obj and 'OutputIntents' not in self.skip_roles:
            self.ctx.deny(
                'pikepdf:output-intent',
                where,
                "no OutputIntents; device colour cannot be checked",
                'unsupported',
            )

    def _on_output_intents(self, obj: Any, where: str, depth: int) -> None:
        profiles: set[tuple[int, int]] = set()
        for intent in obj:
            if not isinstance(intent, pikepdf.Dictionary):
                continue
            profile = intent.get('/DestOutputProfile')
            if profile is None:
                continue
            if not profile.is_indirect:
                self.ctx.deny(
                    'pikepdf:schema-OutputIntent',
                    where,
                    "/DestOutputProfile is not an indirect stream",
                )
                continue
            profiles.add(profile.objgen)
        if len(profiles) > 1:
            self.ctx.deny(
                self.ctx.rule('6.2.2-2', '6.2.3-2'),
                where,
                "OutputIntents refer to different destination profiles "
                f"{sorted(profiles)}",
            )

    def _on_output_profile(self, obj: Any, where: str, depth: int) -> None:
        ctx = self.ctx
        try:
            data = obj.read_bytes()
        except pikepdf.PdfError as e:
            ctx.deny(
                'pikepdf:icc', where, f"cannot read ICC profile: {e}", 'unsupported'
            )
            return
        try:
            header = IccHeader.parse(data)
        except ValueError as e:
            ctx.deny(ctx.rule('6.2.2-1', '6.2.3-1'), where, str(e))
            return
        if not check_output_profile(header, ctx.flavour, ctx, where):
            return
        n = obj.get('/N')
        if COMPONENTS.get(header.colour_space) != n:
            ctx.deny(
                'pikepdf:icc-components',
                where,
                f"/N {n} does not match ICC colour space {header.colour_space!r}",
                'unsupported',
            )
            return
        if ctx.output_intent_cs is None:
            ctx.output_intent_cs = header.colour_space

    def _inherited(self, obj: Any, key: str) -> Any:
        """Look up an inheritable page attribute through /Parent links."""
        node = obj
        seen: set[tuple[int, int]] = set()
        for _ in range(self.ctx.max_depth):
            if key in node:
                return node.get(key)
            parent = node.get('/Parent')
            if not isinstance(parent, pikepdf.Dictionary) or parent.objgen in seen:
                return None
            seen.add(parent.objgen)
            node = parent
        return None

    def _check_box(self, name: str, box: Any, where: str) -> None:
        ctx = self.ctx
        values: list[float] = []
        if isinstance(box, pikepdf.Array) and len(box) == 4:
            try:
                values = [float(v) for v in box]
            except (TypeError, ValueError):
                values = []
        if len(values) != 4:
            ctx.deny('pikepdf:schema-Page', where, f"{name} is not a rectangle")
            return
        width = abs(values[2] - values[0])
        height = abs(values[3] - values[1])
        for size in (width, height):
            if not MIN_BOX_SIZE <= size <= MAX_BOX_SIZE:
                ctx.deny(
                    ctx.rule(None, '6.1.13-11', 'page-box-size'),
                    where,
                    f"{name} is {width:g} x {height:g}; each side must be "
                    f"{MIN_BOX_SIZE}-{MAX_BOX_SIZE} units",
                )
                return

    def _on_page(self, obj: Any, where: str, depth: int) -> None:
        ctx = self.ctx
        if self._inherited(obj, '/MediaBox') is None:
            ctx.deny('pikepdf:schema-Page', where, "page has no /MediaBox")
        for name in PAGE_BOXES:
            if name in INHERITABLE_BOXES:
                box = self._inherited(obj, name)
            else:
                box = obj.get(name)
            if box is not None:
                self._check_box(name, box, where)
        if '/Resources' not in obj:
            resources = self._inherited(obj, '/Resources')
            if resources is not None:
                self._stack.append(
                    _Item(resources, 'Resources', depth + 1, f'{where} inherited')
                )
        self.on_page_content(pikepdf.Page(obj), where)

    def _check_page_tree(self) -> None:
        """Check that the page tree has pages and that every /Count is right."""
        ctx = self.ctx
        root = ctx.pdf.Root.get('/Pages')
        if not isinstance(root, pikepdf.Dictionary):
            return
        seen: set[tuple[int, int]] = set()

        def leaves(node: pikepdf.Dictionary, depth: int) -> int | None:
            """Count the pages under *node*, or None if the tree is unusable."""
            if depth > ctx.max_depth:
                return None  # reported by the walker
            if node.is_indirect:
                if node.objgen in seen:
                    return None  # reported by the walker as a role conflict
                seen.add(node.objgen)
            if node.get('/Type') == pikepdf.Name.Page:
                return 1
            kids = node.get('/Kids')
            if not isinstance(kids, pikepdf.Array):
                return None
            total = 0
            for kid in kids:
                if not isinstance(kid, pikepdf.Dictionary):
                    return None
                pages = leaves(kid, depth + 1)
                if pages is None:
                    return None
                total += pages
            count = node.get('/Count')
            where = f'{ctx.describe(node)} (Pages)'
            if not isinstance(count, int) or isinstance(count, bool):
                ctx.deny('pikepdf:page-tree', where, "/Count is not an integer")
            elif count != total:
                ctx.deny(
                    'pikepdf:page-tree',
                    where,
                    f"/Count is {count} but the node has {total} pages",
                )
            return total

        if leaves(root, 0) == 0:
            ctx.deny('pikepdf:page-tree', 'document', "the document has no pages")

    def _on_image(self, obj: Any, where: str, depth: int) -> None:
        mask = obj.get('/Mask')
        if isinstance(mask, pikepdf.Stream):
            self._stack.append(_Item(mask, 'MaskImage', depth + 1, f'{where} /Mask'))
        # The colour space is checked when a content stream paints the image,
        # with that stream's /Default* colour spaces, or at the end.
        self._images.append((obj, where))

    def _check_unpainted_images(self) -> None:
        for image, where in self._images:
            if image.objgen not in self.content.painted_images:
                check_image_colour(image, None, self.ctx, where)

    def _on_group(self, obj: Any, where: str, depth: int) -> None:
        colour_space = obj.get('/CS')
        if colour_space is not None:
            resolve_colourspace(
                colour_space, None, self.ctx, f'{where} /CS', allow_names=False
            )

    def _on_colour_space(self, obj: Any, where: str, depth: int) -> None:
        # Resources only declare colour spaces: their use is checked by the
        # content streams, so device colour spaces are accepted here.
        resolve_colourspace(
            obj, None, self.ctx, where, allow_names=False, check_device=False
        )

    def _on_extgstate(self, obj: Any, where: str, depth: int) -> None:
        soft_mask = obj.get('/SMask')
        if self.ctx.flavour.part != 1 and isinstance(soft_mask, pikepdf.Dictionary):
            self._stack.append(
                _Item(soft_mask, 'SoftMaskDict', depth + 1, f'{where} /SMask')
            )

    def _on_soft_mask(self, obj: Any, where: str, depth: int) -> None:
        group = obj.get('/G')
        attrs = group.get('/Group') if isinstance(group, pikepdf.Stream) else None
        if (
            not isinstance(attrs, pikepdf.Dictionary)
            or attrs.get('/S') != pikepdf.Name.Transparency
        ):
            self.ctx.deny(
                'pikepdf:schema-SoftMaskDict',
                where,
                "soft mask /G shall be a transparency group Form XObject",
            )

    def _on_annot(self, obj: Any, where: str, depth: int) -> None:
        ctx = self.ctx
        part1 = ctx.flavour.part == 1
        subtype = obj.get('/Subtype')
        flags = obj.get('/F')
        if isinstance(flags, int) and not isinstance(flags, bool):
            forbidden = ANNOT_INVISIBLE | ANNOT_HIDDEN | ANNOT_NOVIEW
            if not part1:
                forbidden |= ANNOT_TOGGLE_NOVIEW
            if not flags & ANNOT_PRINT or flags & forbidden:
                ctx.deny(
                    ctx.rule('6.5.3-2', '6.3.2-2'),
                    where,
                    f"annotation flags {flags} shall set Print and clear "
                    "Hidden, Invisible and NoView",
                )
        appearance = obj.get('/AP')
        if (
            isinstance(appearance, pikepdf.Dictionary)
            and '/N' in appearance
            and not isinstance(appearance.get('/N'), pikepdf.Stream)
        ):
            ctx.deny(
                ctx.rule('6.5.3-6', '6.3.3-4'),
                where,
                "the normal appearance (/N) shall be a stream",
            )
        if (
            not part1
            and appearance is None
            and subtype not in (pikepdf.Name.Popup, pikepdf.Name.Link)
            and _rect_has_area(obj.get('/Rect'))
        ):
            ctx.deny(
                ctx.rule(None, '6.3.3-1'),
                where,
                f"{subtype} annotation has no appearance dictionary",
            )
        if part1:
            opacity = obj.get('/CA')
            if opacity is not None and opacity != 1:
                ctx.deny(ctx.rule('6.5.3-1', None), where, f"/CA is {opacity}, not 1")
            if ('/C' in obj or '/IC' in obj) and ctx.output_intent_cs != 'RGB ':
                ctx.deny(
                    ctx.rule('6.5.3-3', None),
                    where,
                    "/C and /IC require an RGB PDF/A OutputIntent",
                )

    def _on_struct_tree_root(self, obj: Any, where: str, depth: int) -> None:
        """Check that structure type names are valid UTF-8.

        Only the /S names of the structure elements and the /RoleMap are
        read; the structure itself is not validated.
        """
        ctx = self.ctx
        if ctx.flavour.part == 1:
            return
        rule = ctx.rule(None, '6.1.8-1')
        role_map = obj.get('/RoleMap')
        if isinstance(role_map, pikepdf.Dictionary):
            for key, value in role_map.items():
                if not _utf8_key(key) or (
                    isinstance(value, pikepdf.Name) and not _utf8_name(value)
                ):
                    ctx.deny(
                        rule,
                        f'{where} /RoleMap',
                        "structure type name is not valid UTF-8",
                    )
                    break
        pending: list[Any] = [obj.get('/K')]
        seen: set[tuple[int, int]] = set()
        count = 0
        while pending:
            node = pending.pop()
            if isinstance(node, pikepdf.Array):
                pending.extend(node)
                continue
            if not isinstance(node, pikepdf.Dictionary):
                continue
            if node.is_indirect:
                if node.objgen in seen:
                    continue
                seen.add(node.objgen)
            count += 1
            if count > MAX_STRUCTURE_ELEMENTS:
                ctx.deny(
                    'pikepdf:structure-size',
                    where,
                    f"more than {MAX_STRUCTURE_ELEMENTS} structure elements",
                    'unsupported',
                )
                return
            kind = node.get('/S')
            if isinstance(kind, pikepdf.Name) and not _utf8_name(kind):
                ctx.deny(
                    rule,
                    ctx.describe(node),
                    "structure type name is not valid UTF-8",
                )
            if '/K' in node:
                pending.append(node.get('/K'))

    def _on_font_role(self, obj: Any, where: str, depth: int) -> None:
        self.on_font(obj, where)

    def _on_form(self, obj: Any, where: str, depth: int) -> None:
        self.content.walk_unreached_form(obj)

    # --- the content and font tiers ------------------------------------------

    def on_page_content(self, page: pikepdf.Page, where: str = 'page') -> None:
        """Check a page's content streams and the forms they draw."""
        self.content.walk_page(page, where)

    def on_font(self, obj: pikepdf.Object, where: str = 'font') -> None:
        """Check a font dictionary reached through a resource dictionary."""
        load_font(obj, self.ctx, where)


def _rect_has_area(rect: Any) -> bool:
    """False only for a rectangle of zero width and zero height."""
    if not isinstance(rect, pikepdf.Array) or len(rect) != 4:
        return True
    try:
        x1, y1, x2, y2 = (float(v) for v in rect)
    except (TypeError, ValueError):
        return True
    return not (x1 == x2 and y1 == y2)


def _utf8_name(name: pikepdf.Name) -> bool:
    try:
        str(name)
    except UnicodeDecodeError:
        return False
    return True


def _utf8_key(key: str) -> bool:
    try:
        key.encode('utf-8')
    except UnicodeEncodeError:
        return False
    return True
