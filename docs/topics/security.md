(security)=

# PDF security

## Password security

Password security in PDFs is widely supported, including by pikepdf. Unfortunately,
its security has limitations and may offer more security theatre than real
security, depending on your needs.

Note the following limitations of password security in PDFs:

- anyone with the user password *or* the owner password can open the PDF, extract
  its contents, and produce a visually identical PDF;
- if the user password is an empty string, everyone has the user password;
- setting a user password and leaving the owner password blank is useless;
- the only thing you can not do if you have the user password and not the owner
  password is create a new PDF encrypted with the same owner password;
- `pikepdf.Permissions` restrictions depend entirely on the PDF viewer software
  to enforce the restrictions – libraries like pikepdf can bypass those restrictions;
- cracking PDF passwords is easier than many other forms of cracking because
  a motivated person has unlimited chances to guess the password on a static file.

While the AES encryption algorithm is strong, password-protected PDFs have
significant practical weaknesses.

In view of all of this, the most useful option is to set the owner password to a
strong password, and the user password to blank. This allows anyone to view the PDF
while allowing you to prove that you (or your software's user) generated the PDF by
producing the strong owner password.

(pdf-encryption-weaknesses)=

### What PDF encryption does not protect against

The weaknesses below are properties of the PDF format, not of pikepdf or of any
particular PDF application. They apply no matter how strong your password is or
which cryptographic library does the work. If your threat model includes any of
them, PDF encryption is the wrong tool and you should encrypt the file with
something else, or not distribute it.

**Unlimited offline guessing.** An encrypted PDF is data at rest. An attacker
who has the file can try passwords as fast as their hardware allows, forever,
with no server to rate-limit them and no way for you to revoke access. This is
categorically weaker than a system that authenticates against a service.

**Content can be exfiltrated without the password.** The format permits a single
document to mix encrypted and unencrypted content. An attacker who can modify
an encrypted file — without being able to read it — can wrap the encrypted parts
in content they control, so that opening the file in a normal viewer sends the
decrypted text back to them, via a form submission, a hyperlink or JavaScript.

**Encrypted content can be tampered with.** PDF's AES-CBC encryption carries no
integrity protection, which makes ciphertext malleable: an attacker can alter
encrypted content, or construct "CBC gadgets" that cause a document to exfiltrate
itself. Encryption in PDF proves nothing about who wrote the content or whether
it has been changed.

The researchers who catalogued these attacks tested 27 widely used PDF viewers
and found every one of them vulnerable to at least one variant.

**Either password removes the protection.** Anyone holding the user *or* owner
password can decrypt the document and save an unencrypted copy. Permissions
({class}`pikepdf.Permissions`) are advisory flags that only cooperating viewers
honour; see {ref}`pdf-content-restrictions`.

Newer editions of the standard address the cryptographic weaknesses.
[ISO/TS 32003:2023](https://www.iso.org/standard/45876.html) adds AES-GCM, an
authenticated cipher, and ISO/TS 32004:2024 adds document-level integrity
protection through a message authentication code. **pikepdf cannot produce or
read these**, because qpdf does not implement them; the strongest encryption
pikepdf supports is AES-256 in CBC mode (`R=6`). Tampering and exfiltration
remain applicable to every file pikepdf can write.

Further reading:

- [PDFex: Major Security Flaws in PDF Encryption](https://web-in-security.blogspot.com/2019/09/pdfex-major-security-flaws-in-pdf.html)
  — accessible summary of the attacks above
- Müller et al., [Practical Decryption exFiltration: Breaking PDF Encryption](https://dl.acm.org/doi/10.1145/3319535.3354214),
  ACM CCS 2019 — the underlying paper
- [pdf-insecurity.org](https://pdf-insecurity.org/) — the research group's
  ongoing catalogue, including later work on signatures (Shadow Attacks, 2020)
  and certification (IEEE S&P 2021)

### Unicode in passwords

For widest compatibility, passwords should be composed of only characters in the
ASCII character set, since the {{ pdfrm }} is unclear about how non-ASCII
passwords are supposed to be encoded. See the documentation on {meth}`pikepdf.Pdf.save`
for more details. pikepdf encodes passwords as UTF-8.

(pdf-content-restrictions)=

## PDF content restrictions

If you are developing a PDF application, you should enforce the restrictions in
{class}`pikepdf.Permissions`, and not permit people who have only the user password
to access restricted content. If the PDF is opened with the owner password,
any content may be accessed without enforcing restrictions.
{attr}`pikepdf.Pdf.user_password_matched` and {attr}`pikepdf.Pdf.owner_password_matched`
can be used to check which password opened the PDF.

It is up to the application developer to implement the restrictions. pikepdf or
any PDF manipulation library can be used to bypass restrictions.

## Cryptographic providers

pikepdf does not implement cryptography itself. It inherits whatever provider
qpdf was built against, which is one of qpdf's own *native* implementation,
OpenSSL, or GnuTLS. Which one you have depends on how you installed pikepdf:

| How you installed pikepdf | Provider |
| --- | --- |
| PyPI wheel on Windows | OpenSSL, statically linked into qpdf's DLL |
| PyPI wheel on Linux or macOS | qpdf native |
| Distribution package (e.g. Debian/Ubuntu `python3-pikepdf`) | whatever that distribution's `libqpdf` uses — commonly GnuTLS |
| Built from source | whichever provider your qpdf was configured with |

### Why the wheels mostly use native crypto

PDF encryption depends on obsolete primitives. Documents using `/R` 2, 3 or 4 —
still common in the wild — require RC4 and MD5. Mainstream cryptographic
libraries are deliberately withdrawing these: OpenSSL 3 moved them into a
"legacy" provider that is not loaded by default. When Homebrew's OpenSSL made
that change, macOS wheels stopped being able to open legacy encrypted PDFs at
all ({issue}`520`).

qpdf's native provider implements these algorithms directly, so no upstream
deprecation can withdraw them. That is why pikepdf's Linux and macOS wheels use
it: it is the option that reliably opens the files users actually have.

### What that costs

Native crypto is a tradeoff, and it is worth being explicit about the downside.
qpdf's implementations of MD5, RC4, SHA-2 and AES receive far less review,
fuzzing and independent analysis than OpenSSL or GnuTLS, which are audited
continuously and used at enormous scale. They also provide no hardware
acceleration and no FIPS-validated mode. qpdf's own manual recommends external
providers "in nearly all cases", while describing native as fully supported.

### Choosing a different provider

If you need higher assurance — typically because a policy requires a validated
or actively audited cryptographic module — and you do not need to open documents
that use the obsolete algorithms, you have two options:

- **Install a distribution-packaged pikepdf.** On Debian and Ubuntu,
  `python3-pikepdf` links the system `libqpdf`, which is built against GnuTLS
  and patched by the distribution's security team.
- **Build qpdf and pikepdf yourself**, configuring qpdf with
  `-DREQUIRE_CRYPTO_OPENSSL=1` or `-DREQUIRE_CRYPTO_GNUTLS=1`. See
  {ref}`source-build`.

Where more than one provider was compiled into your qpdf, the
`QPDF_CRYPTO_PROVIDER` environment variable selects between them at runtime.
This is useful on Windows wheels, which contain both `openssl` and `native`.
It cannot add a provider that was not compiled in, so it has no effect on
pikepdf's Linux and macOS wheels.

### Keeping this in proportion

Before switching providers, weigh what it actually buys you. The provider is
rarely the weakest part of an encrypted PDF. None of the attacks described in
{ref}`pdf-encryption-weaknesses`
target the cipher implementation — offline password guessing, exfiltration
through partial encryption, and CBC malleability all work identically against a
flawlessly implemented AES. A more heavily audited AES does not make an
encrypted PDF meaningfully harder to break.

The provider choice matters most for compliance obligations and for defence in
depth, not as the difference between a safe and an unsafe document. If the
confidentiality of the content genuinely matters, the right response is to not
rely on PDF encryption for it.

## Digital signatures and certificates

PDFs signed with a digital signature can mitigate some of these security issues.
pikepdf does not support digital signatures at this time.
