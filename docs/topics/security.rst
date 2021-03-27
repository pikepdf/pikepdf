.. _security:

PDF security
************

Password security
=================

Password security in PDFs is widely supported, including by pikepdf. Unfortunately,
its security has limitations and may offer more security theatre than real
security, depending on your needs.

Note the following limitations of password security in PDFs:

- anyone with the user password *or* the owner password can open the PDF, extract
  its contents, and produce a visually identical PDF;
- if the user password is an empty string, everyone has the user password;
- setting a user password and leaving the owner password blank is useless;
- the only thing you can do not do if you have the user password and not the owner
  password is create a new PDF encrypted with the same owner password;
- ``pikepdf.Permissions`` restrictions depend entirely on the PDF viewer software
  enforce the restrictions – libraries like pikepdf can bypass those restrictions;
- cracking PDF passwords is easier than many other forms of cracking because,
  a motivated person has unlimited chances to guess the password on a static file.

This is to say, while the AES encryption algorithm is strong, password-protected
PDFs have significant practical weaknesses.

Despite, the most useful situation is to set the owner password to a strong
password, and the user password to blank. This allows anyone to view the PDF,
but you can prove that you (or your software's user) generated the PDF by
producing a strong owner password.

Unicode in passwords
--------------------

For widest compatibility, passwords should be composed of only characters in the
ASCII character set, since the PDF reference manual is unclear about how non-ASCII
passwords are supposed to be encoded. See the documentation on ``Pdf.save()``
for more details. pikepdf encodes passwords as UTF-8.

PDF content restrictions
========================

If you are developing a PDF application, you should enforce the restrictions in
``pikepdf.Permissions``, and not permit people who have only the user password
to access restricted content. If the PDF is opened with the owner password,
any content may be accessed without enforcing restrictions.

It is up to the application developer to implement the restrictions. pikepdf or
any PDF manipulation library can be used to bypass restrictions.

Digital signatures and certificates
===================================

PDFs signed with a digital signature can mitigate some of these security issues.
pikepdf does not support digital signatures at this time.
