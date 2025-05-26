# v2.16.1

- `unparse_content_stream` is now less strict about whether elements are lists
  or tuples, matching its v2.15.1 behavior.

# v2.16.0

- Performance improvement for `unparse_content_stream`.
- Fixed some linter warnings.
- Tightened pybind11 dependencies so we don't accept new minor revisions automatically.
- Updated docs on FreeBSD.

# v2.15.1

- Fixed compatibility with pybind11 2.7.0 - some tests fail when previous versions of
  pikepdf are compiled with that version.
- Fixed a coverage code exclusion.
- Added a note missing "version added" comment to documentation.
- Fixed license string not appearing in metadata - thanks @mara004.

# v2.15.0

- Improved our `pdfdoc` codec to raise `UnicodeEncodeError` identifying the
  problem, instead of a less specific `ValueError`. Thanks to @regebro. {issue}`218`
- We now implement stream reader/writer and incremental encoder/decoder for
  our `pdfdoc` codec, making it useful in more places.
- Fixed an issue with extracting JBIG2 images on Windows, due to Windows temporary
  file behavior. Thanks to @kraptor. {issue}`219`

# v2.14.2

- Fixed a syntax error in type hints.

# v2.14.1

- Fixed the ReadTheDocs documentation build, which had broken after the `setup.cfg`
  changes in v2.13.0.
- Amended the Makefile with steps for building Apple Silicon wheels.
- No manual Apple Silicon release since there are no functional changes.

# v2.14.0

- Implemented a major new feature: overlays (watermarks, page composition). This
  makes it easier to solve many common tasks that involve copying content from
  pages to other pages, applying watermarks, headers/footers, etc. {issue}`42`
- Added {meth}`pikepdf.Object.with_same_owner_as` to simplify creating objects
  that have the same owner as another object.
- Many improvements to type hints for classes implemented in C++. {issue}`213, 214`

# v2.13.0

- Build system modernized to use `setup.cfg` instead of `setup.py` as much as
  reasonable.
- The `requirements/*.txt` files are now deprecated. Instead use
  `pip install pikepdf[test,docs]` to install optional extras.
- Extended test coverage for a few tests that affect global state, using `pytest-forked`
  to isolate them.
- All C++ autoformatted with clang-format.
- We now imbue all C++ stringstreams with the C locale, to avoid formatting output
  incorrectly if another Python extension written in C++ happens to change the global
  `std::locale`.

# v2.12.2

- Rebuild wheels against libqpdf 10.3.2.
- Enabled building Linux PyPy x86_64 wheels.
- Fixed a minor issue where the inline images would have their abbreviations
  expanded when unparsed. While unlikely to be problematic, inline images usually
  use abbreviations in their metadata and should be kept that way.
- Added notes to documentation about loading PDFs through Python file streams
  and cases that can lead to poor performance.

# v2.12.1

- Fixed documentation typo and updated precommit settings.
- Ongoing improvements to code coverage: now related to image handling.

# v2.12.0

- Complete bindings for `pikepdf.Annotation` (useful for interpreting PDF
  form widgets, comments, etc.)
- Ongoing improvements to code coverage: minor bug fixes, unreachable code removal,
  more coverage.

# v2.11.4

- Fix {issue}`160`, 'Tried to call pure virtual function "TokenFilter::handle_token"';
  this was a Python/C++ reference counting problem.

# v2.11.3

- Check for versions of jbig2dec that are too old to be supported (lacking the
  necessary command line arguments to extract an image from a PDF).
- Fix setup.py typo: cmd_class changed to cmdclass.

# v2.11.2

- Added missing documentation for `Pdf.is_encrypted`.
- Added some documentation annotations about when certain APIs were added or
  changed, going back to 2.0.

# v2.11.1

- Fixed an issue with `Object.emplace()` not retaining the original object's
  /Parent.
- Code coverage improvements.

# v2.11.0

- Add new functions: `Pdf.generate_appearance_streams` and `Pdf.flatten_annotations`,
  to support common work with PDF forms.
- Fixed an issue with `pip install` on platforms that lack proper multiprocessing
  support.
- Additional documentation improvements from @m-holger - thanks again!

# v2.10.0

- Fixed a XML External Entity (XXE) processing vulnerability in PDF XMP metadata
  parsing. (Reported by Eric Therond of Sonarsource.) All users should upgrade
  to get this security update. [CVE-2021-29421](https://nvd.nist.gov/vuln/detail/CVE-2021-29421)
  was assigned to this issue.
- Bind new functions to check, when a PDF is opened, whether the password used
  to open the PDF matched the owner password, user password, or both:
  `Pdf.user_password_matched` and `Pdf.owner_password_matched`.

# v2.9.2

- Further expansion of test coverage of several functions, and minor bug fixes
  along the way.
- Improve parameter validation for some outline-related functions.
- Fixed overloaded `__repr__` functions in `_methods.py` not being applied.
- Some proofreading of the documentation by @m-holger - thanks!

# v2.9.1

- Further expansion of test coverage.
- Fixed function signatures for `_repr_mimebundle_` functions to match IPython's
  spec.
- Fixed some error messages regarding attempts to do strange things with
  `pikepdf.Name`, like `pikepdf.Name.Foo = 3`.
- Eliminated code to handle an exception that provably does not occur.
- Test suite is now better at closing open file handles.
- Ensure that any demo code in README.md is valid and works.
- Embedded QPDF version in pikepdf Python wheels increased to 10.3.1.

# v2.9.0

- We now issue a warning when attempting to use `pikepdf.open` on a `bytes`
  object where it could be either a PDF loaded into memory or a filename.
- `pikepdf.Page.label` will now return the "ordinary" page number if no special
  rules for pages are defined.
- Many improvements to tests and test coverage. Code coverage for both Python and
  C++ is now automatically published to codecov.io; previously coverage was only
  checked on the developer's machine.
- An obsolete private function `Object._roundtrip` was removed.

# v2.8.0

- Fixed an issue with extracting data from images that had their DecodeParms
  structured as a list of dictionaries.
- Fixed an issue where a dangling stream object is created if we fail to create
  the requested stream dictionary.
- Calling `Dictionary()` and `Array()` on objects which are already of that
  type returns a shallow copy rather than throwing an exception, in keeping with
  Python semantics.
- **v2.8.0.post1**: The CI system was changed from Azure Pipelines to GitHub Actions,
  a transition we made to support generating binary wheels for more platforms.
  This post-release was the first release made with GitHub Actions. It ought to be
  functionally identical, but could different in some subtle way, for example
  because parts of it may have been built with different compiler versions.
- **v2.8.0.post2**: The previous .post1 release caused binary wheels for Linux to
  grow much larger, causing problems for AWS Lambda who require small file sizes.
  This change strips the binaries of debug symbols, also mitigates a rare PyPy
  test failure.
- Unfortunately, it appears that the transition from Azure Pipelines to GitHub
  Actions broke compatibility with macOS 10.13 and older. macOS 10.13 and older
  are considered end of life by Apple. No version of pikepdf v2.x ever promised
  support for macOS 10.13 – 10.14+ has always been an explicit requirement.
  It just so happens that for some time, pikepdf did actually work on 10.13.

# v2.7.0

- Added an option to tell `Pdf.save` to recompress flate streams, and a global
  option to set the flate compression level. This option can be use to force
  the recompression of flate streams if they are not well compressed.
- Fixed "TypeError: only pages can be inserted" when attempting to an insert an
  unowned page using QPDF 10.2.0 or later.

# v2.6.0

- Rebuild wheels against QPDF 10.2.0.

# v2.5.2

- Fixed support for PyPy 3.7 on macOS.

# v2.5.1

- Rebuild wheels against recently released pybind11 v2.6.2.
- Improved support for building against PyPy 3.6/7.3.1.

# v2.5.0

- PyPy3 is now supported.
- Improved test coverage for some metadata issues.

# v2.4.0

- The DocumentInfo dictionary can now be deleted with `del pdf.docinfo`.
- Fixed issues with updating the `dc:creator` XMP metadata entry.
- Improved error messages on attempting to encode strings containing Unicode
  surrogates.
- Fixed a rare random test failure related to strings containing Unicode
  surrogates.

# v2.3.0

- Fixed two tests that failed with libqpdf 10.1.0.
- Add new function `pikepdf.Page.add_resource` which helps with adding a new object
  to the /Resources dictionary.
- Binary wheels now provide libqpdf 10.1.0.

# v2.2.5

- Changed how one C++ function is called to support libqpdf 10.1.0.

# v2.2.4

- Fixed another case where pikepdf should not be warning about metadata updates.

# v2.2.3

- Fixed a warning that was incorrectly issued in v2.2.2 when pikepdf updates XMP
  metadata on the user's behalf.
- Fixed a rare test suite failure that occurred if two test files were generated with
  a different timestamp, due to timing of the tests.
- Hopefully fixed build on Cygwin (not tested, based on user report).

# v2.2.2

- Fixed {issue}`150`, adding author metadata breaks PDF/A conformance. We now log an
  error when this metadata is set incorrectly.
- Improve type checking in ocrmypdf.models.metadata module.
- Improve documentation for custom builds.

# v2.2.1

- Fixed {issue}`143`, PDF/A validation with veraPDF failing due to missing prefix on
  DocumentInfo dates.

# v2.2.0

- Added features to look up the index of an page in the document and page labels
- Enable parallel compiling (again)
- Make it easier to create a `pikepdf.Stream` with a dictionary or from an existing
  dictionary.
- Converted most `.format()` strings to f-strings.
- Fixed incorrect behavior when assigning `Object.stream_dict`; this use to create
  a dictionary in the wrong place instead of overriding a stream's dictionary.

# v2.1.2

- Fixed an issue the XMP metadata would not have a timezone set when updated.
  According to the XMP specification, the timezone should be included. Note that
  pikepdf will include the local machine timezone, unless explicitly directed
  otherwise.

# v2.1.1

- The previous release inadvertently changed the type of exception in certain
  situations, notably throwing `ForeignObjectError` when this was not the correct
  error to throw. This release fixes that.

# v2.1.0

- Improved error messages and documentation around `Pdf.copy_foreign`.
- Opt-in to mypy typing.

# v2.0.0

This description includes changes in v2.0 beta releases.

**Breaking changes**

- We now require at least these versions or newer:
  \- Python 3.6
  \- pybind11 2.6.0
  \- QPDF 10.0.3
  \- For macOS users, macOS 10.14 (Mojave)
- Attempting to modifying `Stream.Length` will raise an exception instead of a
  warning. pikepdf automatically calculates the length of the stream when a PDF is
  saved, so there is never a reason to modify this.
- `pikepdf.Stream()` can no longer parse content streams. That never made sense,
  since this class supports streams in general, and many streams are not content
  streams. Use `pikepdf.parse_content_stream` to a parse a content stream.
- `pikepdf.Permissions` is now represented as a `NamedTuple`. Probably not a
  concern unless some user made strong assumptions about this class and its superclass.
- Fixed the behavior of the `__eq__` on several classes to return
  `NotImplemented` for uncomparable objects, instead of `False`.
- The instance variable `PdfJpxImage.pil` is now a private variable.

**New features**

- Python 3.9 is supported.
- Significantly improved type hinting, including hints for functions written in C++.
- Documentation updates

**Deprecations**
\- `Pdf.root` is deprecated. Use `Pdf.Root`.

## v2.0.0b2

- We now require QPDF 10.0.3.

## v2.0.0b1

**Breaking changes**

- We now require at least these versions or newer:
  \- Python 3.6
  \- pybind11 2.6.0
  \- QPDF 10.0.1
  \- For macOS users, macOS 10.14 (Mojave)
- Attempting to modifying `Stream.Length` will raise an exception instead of a
  warning.
- `pikepdf.Stream()` can no longer parse content streams. That never made sense,
  since this class supports streams in general, and many streams are not content
  streams. Use `pikepdf.parse_content_stream` to a parse a content stream.
- `pikepdf.Permissions` is now represented as a `NamedTuple`. Probably not a
  concern unless some user made strong assumptions about this class and its superclass.
- Fixed the behavior of the `__eq__` on several classes to return
  `NotImplemented` for uncomparable objects, instead of `False`.

**New features**

- Python 3.9 is supported.
- Significantly improved type hinting, including hints for functions written in C++.
