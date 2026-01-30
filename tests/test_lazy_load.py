import subprocess
import sys
import pytest

def test_pikepdf_import_does_not_eagerly_load_heavy_deps():
    """
    Guard against regressions that eagerly import lxml or Pillow at
    pikepdf import time.

    This test runs in a subprocess for accuracy and safety.
    """
    code = r"""
import sys
import pikepdf

assert 'pikepdf' in sys.modules
assert 'pikepdf._core' in sys.modules

for mod in sys.modules:
    if mod.startswith(("lxml", "PIL")):
        raise SystemExit(f"eager import detected: {mod}")
print("OK")
"""

    result = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr or result.stdout


def test_lang_alts_works():
    from pikepdf.models.metadata import LANG_ALTS
    with pytest.raises(ImportError):
        from pikepdf.models.metadata import THIS_DOES_NOT_EXIST

def test_lazy_xml_works():
    from pikepdf._xml import _Element, _ElementTree
    with pytest.raises(ImportError):
        from pikepdf._xml import THIS_DOES_NOT_EXIST
