#!/usr/bin/env python3

import re
from tempfile import NamedTemporaryFile

from itertools import tee

def pairwise(iterable):
    "s -> (s0,s1), (s1,s2), (s2, s3), ..."
    a, b = tee(iterable)
    next(b, None)
    return zip(a, b)


def _find_main_offsets(mm):
    offsets = {}

    # Order is: xref, trailer, startxref
    # start at the end and work backwards
    # startxref has the offset of xref
    # trailer comes right before startxref

    offsets['startxref'] = mm.rfind(b"startxref")
    cursor = offsets['startxref'] + len(b"startxref")

    # Search for the integer (ascii-encoded) that follows "startxref"
    # this is the xref offset
    m = re.search(br"\s+(\d+)", mm[cursor:], flags=re.MULTILINE)
    offsets['xref'] = int(m.group(1))

    # Search for the trailer between xref and startxref
    # no risk of collisions
    offsets['trailer'] = mm.rfind(
        b"trailer", offsets['xref'], offsets['startxref'])

    return offsets


def _parse_xref_table(mm, xref_offset):
    mm.seek(xref_offset)
    xref_line = mm.readline()
    assert xref_line.strip() == b"xref", xref_line

    obj_table = mm.readline()
    hopefully_zero, obj_count = obj_table.strip().split(b' ')
    if hopefully_zero != b'0':
        raise NotImplementedError("PDF has a complex xref table, can't fix")
    obj_count = int(obj_count)

    obj_offsets = []
    for n in range(obj_count):
        offsetline = mm.readline().strip()
        str_offset, genid, flags = offsetline.split(b' ')

        if str_offset == b"0000000000" and genid != b"65535":
            raise NotImplementedError("PDF has a complex xref table, can't fix")

        obj_offsets.append(int(str_offset))

    return obj_offsets


def _rewrite_endstreams(mm, obj_ranges, output):
    new_offsets = []
    mm.seek(0)
    for n, ranges in enumerate(obj_ranges):
        start, end = ranges
        m = re.search(br"(endstream)\nendobj", mm[start:end],
                      flags=re.MULTILINE)
        if m:
            # Adjust for the presence of an endstream with newline prefix
            offset_endstream = m.span(1)[0] + start
            output.write(mm[start:offset_endstream])
            output.write(b'\n')
            output.write(mm[offset_endstream:end])
        else:
            output.write(mm[start:end])
        new_offsets.append(output.tell())

    return new_offsets


def _write_xref(offsets, output):
    num_objects = len(offsets) + 1  # one for 0000000 entry
    output.write("xref\n0 {}\n".format(num_objects).encode())

    def make_xref_entry(offset, genid, flags):
        s = '{:010d} {:05d} {} \n'.format(offset, genid, flags)
        s = s.encode()
        assert len(s) == 20, "must be exactly 20 bytes long"
        assert s[18:20] == b' \n', "must end with space LF"
        return s

    output.write(make_xref_entry(0, 65535, 'f'))

    for offset in offsets:
        output.write(make_xref_entry(offset, 0, 'n'))


def _write_trailer(mm, original_offsets, output):
    trailer = original_offsets['trailer']
    startxref = original_offsets['startxref']
    output.write(mm[trailer:startxref])


def _write_startxref(new_xref_offset, output):
    output.write(b'startxref\n')
    output.write('{:d}\n'.format(new_xref_offset).encode())


def repair_pdfa(filename):
    """Repair "missing EOL before endstream" errors in PDF/A

    QPDF generates PDFs without putting an EOL before the endstream keyword.

    1.
    stream
    dostuffdostuffdostuff_endstream <-- PDF/A error, missing LF
    endobj

    2.
    << /Length 5 ... >>
    stream
    1234      <-- 4 characters + LF
    endstream <-- PDF/A error, missing LF because it is read as part of stream
    endobj

    This is legal, PDF/A requires the EOL. Specifically it requires that
    at least one EOL appears after reading /Length bytes from the stream,
    so a stream that happens to terminate on an EOL character will not pass.

    This assumes a simple PDF with no updates in the xref table, as would
    normally be the case after one is passed through QPDF.

    It also cannot find improperly laid out content streams inside object
    streams so object streams need to be disabled.

    """
    import mmap
    from shutil import copy2

    with NamedTemporaryFile(suffix='.pdf', mode='r+b') as temp:
        copy2(filename, temp.name)
        temp.flush()
        temp.seek(0)
        mm = mmap.mmap(temp.fileno(), 0)

        offsets = _find_main_offsets(mm)
        obj_offsets = _parse_xref_table(mm, offsets['xref'])

        # Append xref's offset as the final offset to account for range
        # between start of last object and start of xref
        obj_offsets.append(offsets['xref'])
        obj_ranges = pairwise((offset for offset in obj_offsets))

        with NamedTemporaryFile(suffix='.pdf') as output:
            new_offsets = _rewrite_endstreams(mm, obj_ranges, output)
            new_xref_offset = new_offsets.pop()
            _write_xref(new_offsets, output)
            _write_trailer(mm, offsets, output)
            _write_startxref(new_xref_offset, output)
            output.write(b'%%EOF\n')
            output.flush()

            # Succeeded
            copy2(output.name, filename)

        mm.close()

