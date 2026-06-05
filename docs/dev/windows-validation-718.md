# Windows validation handoff — issue #718 (bundled MSVC runtime)

> **Temporary handoff doc** for a Windows agent validating the fix for
> [pikepdf#718](https://github.com/pikepdf/pikepdf/issues/718). Not intended to be
> committed long-term — delete once the fix is validated and merged.

## Context

On Windows, `import pikepdf` could fail from a terminal with a fatal
`PyInterpreterState_Get ... the GIL is released (the current Python thread state
is NULL)` error (when another extension such as `pypdf`'s deps loaded first), or
an `ImportError` for `pikepdf._core` otherwise — yet work fine inside IDLE.

**Root cause:** the Windows wheel shipped a fixed-version copy of the Microsoft
Visual C++ runtime (`msvcp140*.dll`, `vcruntime140*.dll`, `concrt140.dll`)
*inside the `pikepdf/` package directory*. They were copied wholesale from qpdf's
prebuilt release (`cp D:\qpdf\bin\*.dll src\pikepdf`) alongside `qpdf30.dll`.
A package-local runtime that shadows / conflicts with the system runtime means
two copies of the C++ runtime load in one process; CPython keeps its per-thread
state in CRT TLS, so the mismatch reads the thread state as NULL → the fatal
abort. The whole thing is DLL-load-order dependent, which is why it reproduces in
a terminal but not IDLE.

## The fix (already applied on the working branch)

- `build-scripts/win-download-qpdf.ps1` — copies only qpdf's own DLLs, filtering
  out `msvcp140*` / `vcruntime140*` / `concrt140*`.
- `pyproject.toml` (`[tool.cibuildwheel.windows]`) — adds `delvewheel repair
  --exclude "...runtime dlls..."` as a guard.
- `src/pikepdf/__init__.py` — richer error message on `_core` import failure.
- `docs/installation.md`, `docs/releasenotes/version10.md` — document the VC++
  Redistributable requirement and the fix.

The runtime is now expected to come from the **system VC++ Redistributable
(x64)**, exactly as qpdf's own msvc build already requires.

## Goal

Prove two things on Windows:
1. The released wheel's runtime DLLs are the cause (reproduce + workaround).
2. The rebuilt wheel no longer ships those DLLs and imports cleanly.

## Prerequisites on the VM

- Windows 10/11 x64.
- **Python 3.14.0 x64** from python.org (match the reporter). Confirm:
  `python -c "import sys; print(sys.version, sys.maxsize > 2**32)"`.
- Latest **x64 VC++ Redistributable** installed: <https://aka.ms/vs/17/release/vc_redist.x64.exe>.
- `pip install psutil pypdf` (psutil is used to inspect loaded DLLs).

---

## Tier 1 — Reproduce the bug and confirm the workaround (fast, no build)

This validates the diagnosis without compiling anything.

1. Fresh venv, install the **released, broken** wheel:
   ```
   py -3.14 -m venv C:\t1 && C:\t1\Scripts\activate
   pip install pikepdf==10.5.1 psutil pypdf
   ```
2. Confirm the runtime DLLs are bundled in the package dir:
   ```
   dir C:\t1\Lib\site-packages\pikepdf\*.dll
   ```
   Expect to see `msvcp140*.dll`, `vcruntime140*.dll`, `concrt140.dll`, `qpdf30.dll`.
3. Show **which** `msvcp140.dll` actually loads (the smoking gun). Run:
   ```python
   import psutil, pikepdf  # noqa
   for m in psutil.Process().memory_maps():
       p = m.path.lower()
       if "msvcp140" in p or "vcruntime140" in p or "qpdf30" in p:
           print(m.path)
   ```
   On the broken wheel, `msvcp140.dll` resolves from **`site-packages\pikepdf\`**
   (the bug). Also try `python -c "import pypdf; import pikepdf"` from cmd and
   PowerShell — note whether the fatal `thread state is NULL` abort occurs.
   *(The fatal crash is load-order dependent and may not reproduce on every VM; the
   loaded-DLL path above is the deterministic signal.)*
4. Apply the **workaround** — delete the bundled runtime (keep `qpdf30.dll` and
   `_core*.pyd`):
   ```
   cd C:\t1\Lib\site-packages\pikepdf
   del msvcp140.dll msvcp140_1.dll msvcp140_2.dll msvcp140_atomic_wait.dll msvcp140_codecvt_ids.dll vcruntime140.dll vcruntime140_1.dll concrt140.dll
   ```
   Re-run step 3's snippet. `msvcp140.dll` should now resolve from
   **`C:\Windows\System32\`** and `import pikepdf` (and `import pypdf; import
   pikepdf`) should succeed. This confirms removing the bundled runtime is the fix.

---

## Tier 2 — Build the fixed wheel and validate

Reproduces the CI build with the patched branch.

1. Check out the fix branch and install build host deps:
   ```
   py -3.10 -m pip install tomli cibuildwheel
   ```
   (MSVC Build Tools / Visual Studio 2022 C++ workload must be installed.)
2. Read env and download qpdf (this also runs the patched copy step):
   ```
   python build-scripts/environ-from-pyproject.py   # note QPDF_VERSION
   powershell -File build-scripts/win-download-qpdf.ps1 <QPDF_VERSION> win_amd64
   ```
3. Confirm the patched copy step did **not** bring the runtime into the package:
   ```
   dir src\pikepdf\*.dll
   ```
   Expect `qpdf30.dll` (and any genuine third-party deps) but **no** `msvcp140*` /
   `vcruntime140*` / `concrt140*`.
4. Build just the cp314 wheel (fast) with cibuildwheel:
   ```
   set CIBW_BUILD=cp314-win_amd64
   set QPDF_SOURCE_TREE=d:\qpdf
   set QPDF_BUILD_LIBDIR=d:\qpdf\lib
   python -m cibuildwheel --platform windows --output-dir wheelhouse
   ```
   (cibuildwheel runs delvewheel repair + the test suite automatically.)
5. Inspect the produced wheel. The wheel is **self-contained**: delvewheel vendors
   a **name-mangled** `msvcp140` (e.g. `msvcp140-<hash>.dll`) into `pikepdf.libs/`,
   and `qpdf30.dll` is present. There must be **no un-mangled** `msvcp140.dll` /
   `vcruntime140*.dll` / `concrt140.dll` (vcruntime140 comes from CPython, not the
   wheel):
   ```
   python -c "import zipfile,glob; w=glob.glob('wheelhouse/*cp314*win_amd64.whl')[0]; print('\n'.join(n for n in zipfile.ZipFile(w).namelist() if n.lower().endswith('.dll')))"
   ```
   Expect `qpdf30.dll` plus a hash-mangled `msvcp140-*.dll` under `pikepdf.libs/`;
   do **not** expect a plain `msvcp140.dll`, `vcruntime140*.dll`, or `concrt140.dll`.
6. Install the fresh wheel into a clean venv and validate import + DLL provenance.
   To prove the wheel is genuinely self-contained, this venv does **not** require
   the VC++ redistributable for `msvcp140` (CPython still supplies `vcruntime140`):
   ```
   py -3.14 -m venv C:\t2 && C:\t2\Scripts\activate
   pip install psutil pypdf
   pip install --no-index --find-links wheelhouse pikepdf
   python -c "import pypdf; import pikepdf; print('OK', pikepdf.__version__, pikepdf.__libqpdf_version__)"
   ```
   Then re-run Tier 1 step 3's snippet: `qpdf30.dll` and the mangled `msvcp140-*.dll`
   should both load from `site-packages\pikepdf` / `site-packages\pikepdf.libs`
   (i.e. the vendored copies, **not** `site-packages\pikepdf\msvcp140.dll`), and
   `vcruntime140.dll` from the CPython install (next to `python.exe`).

---

## Pass criteria

- [ ] Tier 1: broken wheel loads `msvcp140.dll` from `site-packages\pikepdf\`;
      deleting the bundled runtime makes it load from `System32` and import succeed.
- [ ] Tier 2 step 3: `src\pikepdf` contains no `msvcp140*`/`vcruntime140*`/`concrt140*`.
- [ ] Tier 2 step 5: built wheel contains `qpdf30.dll` and a **mangled**
      `msvcp140-*.dll` in `pikepdf.libs/`, and **no** un-mangled `msvcp140.dll` /
      `vcruntime140*` / `concrt140`.
- [ ] Tier 2 step 6: `import pypdf; import pikepdf` succeeds in a venv **without**
      the VC++ redistributable; `msvcp140` resolves from the vendored mangled copy
      (not the package root); full cibuildwheel test suite passes.
- [ ] (Optional but ideal) Reproduce the original fatal abort on the broken wheel
      from a plain terminal, and confirm the rebuilt wheel does not abort.

## Report back

Paste: the loaded-DLL paths from Tier 1 (before/after) and Tier 2; the DLL list
from the rebuilt wheel; and the cibuildwheel test summary. Flag anything where an
un-mangled runtime DLL appears in `src\pikepdf` or in the wheel root, where no
mangled `msvcp140-*` is vendored, or where qpdf ships an additional third-party
DLL (e.g. jpeg/zlib) that the filter accidentally drops.
