# SPDX-FileCopyrightText: 2022 James R. Barlow
# SPDX-License-Identifier: MPL-2.0

from __future__ import annotations

try:
    import tomllib
except ModuleNotFoundError:
    import tomli as tomllib  # type: ignore

with open('pyproject.toml', 'rb') as f:
    t = tomllib.load(f)
env = t['tool']['cibuildwheel']['environment']
print('\n'.join(f'{k}={v}' for k, v in env.items()))
