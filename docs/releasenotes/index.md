(changelog)=

# Release notes

:::{figure} /images/pike-release.jpg
:align: right
:alt: pike fish being released to water
:figwidth: 30%

Releasing a pike.
:::

pikepdf releases use the [semantic versioning](https://semver.org)
policy.

The pikepdf API (as provided by `import pikepdf`) is stable and
is in production use. Note that the C++ extension module
`pikepdf._core` is a private interface within pikepdf that applications
should not access directly, along with any modules with a prefixed underscore.

```{toctree}
:glob: true
:maxdepth: 1
:reversed: true

version*
```
