# SPDX-FileCopyrightText: 2026 James R. Barlow
# SPDX-License-Identifier: MPL-2.0

"""Thread safety of pages, content stream parsing and object graph walks.

Stress tests in the manner of the second half of test_threading.py, aimed at
the bindings of Page, the content stream instruction classes, token filters,
ObjectSet and the walks of the object graph. Each starts its threads from a
common barrier and asserts on invariants that hold however they interleave.
Keep each one short: the ThreadSanitizer job runs them too.
"""

from __future__ import annotations

from io import BytesIO

import pytest
from test_threading import RESOURCES, run_n, run_threads

import pikepdf
from pikepdf import (
    Array,
    ContentStreamInlineImage,
    ContentStreamInstruction,
    Dictionary,
    Name,
    ObjectSet,
    Operator,
    Page,
    Pdf,
    Token,
    TokenFilter,
    TokenType,
    _core,
)

pytestmark = pytest.mark.timeout(120, method='thread')

N_PAGES = 8


@pytest.fixture(scope='module')
def content_pdf_bytes():
    """A saved Pdf whose pages have content, and resources held indirectly.

    Each page draws an inline image whose colour space is named in the page's
    /Resources, a form XObject, and text shown from an array. Nothing below
    the page tree is resolved when the file is opened.
    """
    pdf = Pdf.new()
    for n in range(N_PAGES):
        page = pdf.add_blank_page(page_size=(100 + n, 200 + n))
        form = pdf.make_stream(
            f'{n} 0 0 {n} 0 0 cm'.encode(),
            Type=Name.XObject,
            Subtype=Name.Form,
            BBox=[0, 0, 10, 10],
            Resources=pdf.make_indirect(Dictionary()),
        )
        page.obj.Resources = pdf.make_indirect(
            Dictionary(
                ColorSpace=pdf.make_indirect(
                    Dictionary(Cs1=pdf.make_indirect(Array([Name.CalGray, {}])))
                ),
                XObject=pdf.make_indirect(Dictionary(Fx0=form)),
            )
        )
        page.Contents = pdf.make_stream(
            f'q {n} 0 0 1 0 0 cm /Fx0 Do Q\n'.encode()
            + b'BT /F1 12 Tf [(page) -120 ('
            + str(n).encode()
            + b')] TJ ET\n'
            + b'BI /W 1 /H 1 /CS /Cs1 /BPC 8 ID \xff EI\n'
            + b'0 0 10 10 re f'
        )
    out = BytesIO()
    pdf.save(out)
    return out.getvalue()


def describe_instruction(instruction):
    """Read an instruction through each of its accessors, as plain values."""
    operands, operator = instruction
    assert len(instruction) == 2
    assert instruction[0] == instruction.operands == operands
    assert instruction[1] == instruction.operator == operator
    if isinstance(instruction, ContentStreamInlineImage):
        image = instruction.iimage
        assert repr(instruction).startswith('<pikepdf.ContentStreamInlineImage(')
        return (
            'inline',
            str(operator),
            image.width,
            image.height,
            repr(image.colorspace),
        )
    unparsed = pikepdf.unparse_content_stream([instruction])
    return ('instruction', str(operator), unparsed, repr(instruction))


def test_stress_instructions_shared_between_threads(content_pdf_bytes):
    """Instructions parsed by one thread and read by many."""
    with Pdf.open(BytesIO(content_pdf_bytes)) as reference:
        expected = [
            [describe_instruction(i) for i in pikepdf.parse_content_stream(page)]
            for page in reference.pages
        ]
    assert any(e[0] == 'inline' for e in expected[0])

    for _ in range(3):
        with Pdf.open(BytesIO(content_pdf_bytes)) as pdf:
            # Parsed here, but the resources that the inline images refer to
            # are first resolved by whichever thread gets to them
            parsed = [pikepdf.parse_content_stream(page) for page in pdf.pages]

            def read(i, parsed=parsed):
                for k in range(N_PAGES):
                    n = (i + k) % N_PAGES
                    described = [describe_instruction(inst) for inst in parsed[n]]
                    assert described == expected[n]

            run_n(read)


def test_stress_parse_and_unparse_cold_pages(content_pdf_bytes):
    """Parsing and serializing the pages of a freshly opened Pdf."""
    with Pdf.open(BytesIO(content_pdf_bytes)) as reference:
        expected = [
            pikepdf.unparse_content_stream(pikepdf.parse_content_stream(page))
            for page in reference.pages
        ]

    for _ in range(3):
        with Pdf.open(BytesIO(content_pdf_bytes)) as pdf:
            pages = list(pdf.pages)

            def work(i, pages=pages):
                for k in range(N_PAGES):
                    n = (i + k) % N_PAGES
                    instructions = pikepdf.parse_content_stream(pages[n])
                    assert pikepdf.unparse_content_stream(instructions) == expected[n]
                    only_text = pikepdf.parse_content_stream(pages[n], 'TJ Tf')
                    assert [str(op) for _, op in only_text] == ['Tf', 'TJ']
                    rebuilt = [
                        ContentStreamInstruction(inst)
                        if isinstance(inst, ContentStreamInstruction)
                        else ContentStreamInlineImage(inst.iimage)
                        for inst in instructions
                    ]
                    assert pikepdf.unparse_content_stream(rebuilt) == expected[n]

            run_n(work)


def test_stress_instruction_operand_mutated_while_read():
    """An array operand grown by some threads while others read the instruction."""
    pdf = Pdf.new()
    page = pdf.add_blank_page()
    page.Contents = pdf.make_stream(b'BT [(a) 1 (b)] TJ ET')
    instruction = pikepdf.parse_content_stream(page, 'TJ')[0]
    array = instruction.operands[0]
    assert len(array) == 3
    per_thread = 40

    def grow(i):
        for n in range(per_thread):
            array.append(n)

    def read(i):
        for _ in range(per_thread):
            text = pikepdf.unparse_content_stream([instruction])
            assert text.startswith(b'[ (a) 1 (b)') and text.endswith(b'] TJ')
            assert repr(instruction).startswith('pikepdf.ContentStreamInstruction(')
            copied = ContentStreamInstruction(instruction)
            assert len(copied.operands[0]) >= 3
            made = ContentStreamInstruction([array, 5], Operator('TJ'))
            assert len(made.operands) == 2

    run_threads(*[lambda i=i: (grow if i % 2 else read)(i) for i in range(8)])
    assert len(array) == 3 + 4 * per_thread
    assert len(instruction.operands[0]) == 3 + 4 * per_thread


def checker():
    return _core._ContentChecker(
        {'q': '', 'Q': '', 'cm': 'nnnnnn', 'Do': 'N', 'Tf': 'Nn', 'TJ': 'a'},
        {'cm': True, 'Do': True, 'q': False},
        min_integer=-(2**31),
        max_integer=2**31 - 1,
        max_real=32767.0,
        min_real=0.0,
        max_string=32767,
        max_name=127,
        max_array=8191,
        max_dict=4095,
        max_nesting=28,
    )


def describe_check(result):
    events, count = result
    return (
        [
            tuple(
                repr(part) if not isinstance(part, ContentStreamInlineImage) else 'ii'
                for part in event
            )
            for event in events
        ],
        count,
    )


def test_stress_content_checker_shared(content_pdf_bytes):
    """One content checker used by every thread on the streams of a cold Pdf."""
    shared = checker()
    with Pdf.open(BytesIO(content_pdf_bytes)) as reference:
        expected = [
            describe_check(shared.check(page.Contents)) for page in reference.pages
        ]
    assert expected[0][1] > 5

    for _ in range(3):
        with Pdf.open(BytesIO(content_pdf_bytes)) as pdf:
            pages = list(pdf.pages)

            def work(i, pages=pages):
                for k in range(N_PAGES):
                    n = (i + k) % N_PAGES
                    stream = pages[n].Contents
                    assert describe_check(shared.check(stream)) == expected[n]
                    raw = stream.read_bytes()
                    assert _core._scan_raw_content(raw, [b'\xff']) == []

            run_n(work)


class Spacer(TokenFilter):
    """Stateless filter, safe to use from several threads at once."""

    def handle_token(self, token):
        if token.type_ == TokenType.integer:
            return [token, Token(TokenType.space, b' ')]
        if token == Token(TokenType.word, b'f'):
            return None
        return token


def test_stress_shared_token_filter_one_pdf(content_pdf_bytes):
    """One token filter instance filtering every page of a cold Pdf."""
    shared = Spacer()
    with Pdf.open(BytesIO(content_pdf_bytes)) as reference:
        expected = [page.get_filtered_contents(shared) for page in reference.pages]
    assert all(expected)

    for _ in range(3):
        with Pdf.open(BytesIO(content_pdf_bytes)) as pdf:
            pages = list(pdf.pages)

            def work(i, pages=pages):
                for k in range(N_PAGES):
                    n = (i + k) % N_PAGES
                    assert pages[n].get_filtered_contents(shared) == expected[n]

            run_n(work)


def test_stress_attached_token_filters(content_pdf_bytes):
    """Token filters attached to pages by many threads, then run by a save."""
    with Pdf.open(BytesIO(content_pdf_bytes)) as pdf:
        pages = list(pdf.pages)
        before = [page.Contents.read_bytes() for page in pages]

        def attach(i):
            pages[i].add_content_token_filter(Spacer())
            # Reading the stream runs the filter under the Pdf's lock
            assert b' f' not in pages[i].Contents.read_bytes()

        run_n(attach, N_PAGES)
        assert len(pdf._token_filter_refs) == N_PAGES
        out = BytesIO()
        pdf.save(out)
    with Pdf.open(BytesIO(out.getvalue())) as saved:
        for page, original in zip(saved.pages, before, strict=True):
            data = page.Contents.read_bytes()
            assert data != original and b'BT' in data


def test_stress_page_dictionary_access_same_page():
    """The dictionary-style accessors of one page, from every thread."""
    pdf = Pdf.new()
    page = pdf.add_blank_page(page_size=(100, 100))
    per_thread = 50

    def work(i):
        key = f'/Key{i}'
        attr = f'Attr{i}'
        for n in range(per_thread):
            page[key] = n
            assert page[key] == n
            assert page.get(key) == n
            assert page.get(Name(key), 'missing') == n
            assert key in page
            setattr(page, attr, [n, i])
            assert list(getattr(page, attr)) == [n, i]
            assert Name('/' + attr) in page
            assert page.get('/Nope', i) == i
            assert page.Type == Name.Page
            if n % 2:
                del page[key]
                delattr(page, attr)
                assert key not in page
                assert page.get(key) is None
            # A property of Page, which __setattr__ hands to its setter
            page.cropbox = [0, 0, 50 + i, 50 + i]
            assert float(page.cropbox[2]) >= 50

    run_n(work)
    for i in range(8):
        assert f'/Key{i}' not in page
        assert f'/Attr{i}' not in page


def test_stress_page_values_cross_two_pdfs():
    """Two pages of different Pdfs, each assigned values read from the other.

    Each assignment involves both Pdfs. Their locks have to be taken together
    and in a consistent order, or the two directions deadlock.
    """
    a = Pdf.new()
    b = Pdf.new()
    page_a = a.add_blank_page(page_size=(100, 100))
    page_b = b.add_blank_page(page_size=(200, 200))
    page_a.obj.Info = Dictionary(Owner=Name.A, Key=Name.FromB, Sizes=[1, 2, 3])
    page_b.obj.Info = Dictionary(Owner=Name.B, Key=Name.FromA, Sizes=[4, 5, 6])

    def copy(target, source, owner):
        for _ in range(60):
            # A name that belongs to the other Pdf, as a value and as a key.
            # Scalars are copied in.
            target.FromOther = source.Info.Owner
            target[source.Info.Key] = source.Info.Owner
            assert target.FromOther == owner
            assert target[source.Info.Key] == owner
            assert target.get(source.Info.Key) == owner
            assert source.Info.Key in target
            # Containers of another Pdf are refused, after a look at them
            with pytest.raises(pikepdf.ForeignObjectError):
                target.mediabox = source.mediabox
            with pytest.raises(pikepdf.ForeignObjectError):
                target.Sizes = source.Info.Sizes
            with pytest.raises(pikepdf.ForeignObjectError):
                target['/Sizes'] = source.Info
            source.Info.Sizes.append(0)
            del source.Info.Sizes[-1]

    run_threads(
        lambda: copy(page_a, page_b, Name.B),
        lambda: copy(page_b, page_a, Name.A),
        lambda: copy(page_a, page_b, Name.B),
        lambda: copy(page_b, page_a, Name.A),
    )
    assert sorted(page_a.keys() - page_b.keys()) == ['/FromA']
    assert sorted(page_b.keys() - page_a.keys()) == ['/FromB']
    # Nothing was shared: each Pdf still has its own
    assert page_a.Info.Owner == Name.A
    assert page_b.Info.Owner == Name.B
    assert len(page_a.Info.Sizes) == len(page_b.Info.Sizes) == 3


def test_stress_copy_annotations_both_ways():
    """Annotations copied between two Pdfs in both directions at once."""
    a = Pdf.open(RESOURCES / 'form.pdf')
    b = Pdf.open(RESOURCES / 'form.pdf')
    n_annots = len(a.pages[0].Annots)
    assert n_annots > 0
    rounds = 4

    def copy(target, source):
        for _ in range(rounds):
            # Only the annotations the source started with
            fresh = Page(Dictionary(Type=Name.Page, Annots=source.Annots[:n_annots]))
            assert len(fresh.Annots) == n_annots
            target.copy_annotations(source)
            assert len(target.Annots) > n_annots

    run_threads(
        lambda: copy(a.pages[0], b.pages[0]),
        lambda: copy(b.pages[0], a.pages[0]),
    )
    for pdf in (a, b):
        assert len(pdf.pages[0].Annots) > n_annots
        out = BytesIO()
        pdf.save(out)


def test_stress_object_set_shared(content_pdf_bytes):
    """One ObjectSet filled from every thread with the objects of two Pdfs."""
    for _ in range(3):
        a = Pdf.open(BytesIO(content_pdf_bytes))
        b = Pdf.open(BytesIO(content_pdf_bytes))
        objects = (
            list(a.pages)
            + list(b.pages)
            + [a.Root, b.Root, a.trailer, b.trailer]
            + [Dictionary(N=n) for n in range(8)]
        )
        seen = ObjectSet()
        new = [0] * 8

        def work(i, a=a, b=b, objects=objects, seen=seen, new=new):
            for k in range(len(objects)):
                obj = objects[(i * 5 + k) % len(objects)]
                if seen.add(obj):
                    new[i] += 1
                assert obj in seen
                assert len(seen) <= len(objects)
                assert repr(seen).startswith('<pikepdf.ObjectSet of ')
            # A page and its dictionary are the same object
            assert a.pages[i].obj in seen
            assert not seen.add(b.pages[i].obj)
            assert Dictionary() not in seen
            mine = ObjectSet(page for page in a.pages)
            assert len(mine) == N_PAGES
            mine.discard(a.pages[i])
            assert len(mine) == N_PAGES - 1
            mine.clear()
            assert len(mine) == 0

        run_n(work)
        # Each object was reported as new to exactly one thread
        assert sum(new) == len(objects) == len(seen)
        a.close()
        b.close()


def test_stress_object_set_add_and_discard():
    """Objects added to and discarded from one set by different threads."""
    pdf = Pdf.new()
    objects = [pdf.make_indirect(Dictionary(N=n)) for n in range(32)]
    seen = ObjectSet()

    def work(i):
        mine = objects[i * 4 : i * 4 + 4]
        for _ in range(50):
            for obj in mine:
                assert seen.add(obj)
                assert not seen.add(obj)
            for obj in mine:
                assert obj in seen
                seen.discard(obj)
                assert obj not in seen

    run_n(work)
    assert len(seen) == 0


def scope_key(scope):
    kind, content, resources = scope
    return (int(kind), content.objgen, None if resources is None else resources.objgen)


def test_stress_content_scope_walk_shared(content_pdf_bytes):
    """One content scope walk given the pages of a cold Pdf by every thread."""
    everything = 63
    with Pdf.open(BytesIO(content_pdf_bytes)) as reference:
        walk = _core._ContentScopeWalk()
        expected = sorted(
            scope_key(scope)
            for page in reference.pages
            for scope in walk.walk(page, everything)
        )
        scopes = len(list(reference.content_scopes()))
    assert len(expected) == scopes == 2 * N_PAGES

    for _ in range(3):
        with Pdf.open(BytesIO(content_pdf_bytes)) as pdf:
            pages = list(pdf.pages)
            walk = _core._ContentScopeWalk()
            found = [[] for _ in range(8)]

            def work(i, pages=pages, walk=walk, found=found):
                for k in range(N_PAGES):
                    page = pages[(i + k) % N_PAGES]
                    found[i].extend(scope_key(s) for s in walk.walk(page, everything))
                assert len(list(pdf.content_scopes())) == scopes

            run_n(work)
            # Each scope was reported once, to whichever thread got there first
            assert sorted(key for part in found for key in part) == expected


def test_stress_content_scope_walk_two_pdfs(content_pdf_bytes):
    """One content scope walk given pages of two Pdfs by different threads."""
    a = Pdf.open(BytesIO(content_pdf_bytes))
    b = Pdf.open(BytesIO(content_pdf_bytes))
    walk = _core._ContentScopeWalk()
    counts = [0] * 4

    def work(i):
        pdf = (a, b)[i % 2]
        for page in pdf.pages:
            counts[i] += len(walk.walk(page, 63))

    run_n(work, 4)
    assert sum(counts) == 2 * 2 * N_PAGES
    a.close()
    b.close()


def test_stress_object_graph_walks_cold(content_pdf_bytes):
    """Walks of the object graph of a cold Pdf from every thread."""
    with Pdf.open(BytesIO(content_pdf_bytes)) as reference:
        expected = [
            obj.objgen for obj in _core._reachable_objects(reference, [reference.Root])
        ]
    assert len(expected) > 5 * N_PAGES

    for _ in range(3):
        with Pdf.open(BytesIO(content_pdf_bytes)) as pdf:
            first = pdf.make_indirect(
                Dictionary(
                    S=Name.JavaScript,
                    Next=[
                        pdf.make_indirect(Dictionary(S=Name.GoTo, N=n))
                        for n in range(6)
                    ],
                )
            )
            # A cycle, which the walk must not follow twice
            first.Next[5].Next = first

            def work(i, pdf=pdf, first=first):
                for _ in range(3):
                    reached = _core._reachable_objects(pdf, [pdf.Root])
                    assert [obj.objgen for obj in reached] == expected
                    chain = _core._action_chain(first)
                    assert len(chain) == 7
                    assert chain[0].S == Name.JavaScript
                    assert [int(action.N) for action in chain[1:]] == list(range(6))
                    assert _core._reachable_objects(pdf, [pdf.pages[i].obj])

            run_n(work)
