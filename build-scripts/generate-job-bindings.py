# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.
#
# Copyright (C) 2022, James R. Barlow (https://github.com/jbarlow83/)

import re
from pathlib import Path
from typing import List, NamedTuple

import typer

config_includes = [
    'auto_job_c_att.hh',
    'auto_job_c_copy_att.hh',
    'auto_job_c_enc.hh',
    'auto_job_c_main.hh',
    'auto_job_c_pages.hh',
    'auto_job_c_uo.hh',
]


class Binding(NamedTuple):
    return_class: str
    function: str
    nparams: int


def _lower_replace(match):
    return '_' + match.group(1).lower()


def snake_case_from_camel_case(camel_case: str):
    return re.sub(r'([A-Z])', _lower_replace, camel_case)


TEMPLATE_PARAM0 = """\
    cl.def(
        "{pyfn}", 
        [](QPDFJob::Config &cfg) {{
            return cfg.{fn}();
        }}
    );
"""


def template_param0(binding):
    pyfn = snake_case_from_camel_case(binding.function)
    return TEMPLATE_PARAM0.format(pyfn=pyfn, fn=binding.function)


TEMPLATE_PARAM1 = """\
    cl.def(
        "{pyfn}", 
        [](QPDFJob::Config &cfg, std::string const &param) {{
            return cfg.{fn}(param);
        }}
    );
"""


def template_param1(binding):
    pyfn = snake_case_from_camel_case(binding.function)
    return TEMPLATE_PARAM1.format(pyfn=pyfn, fn=binding.function)


def process(include: Path):
    lines = include.read_text().splitlines()
    bindings: List[Binding] = []
    for n, line in enumerate(lines, start=1):
        if line.startswith('//'):
            continue
        _qpdf_dll, return_class, function_param = line.split(' ', maxsplit=2)
        return_class = return_class.replace('*', '')

        function = function_param.split('(')[0]
        if function_param.endswith('(std::string const& parameter);'):
            bindings.append(Binding(return_class, function, 1))
        elif function_param.endswith('();'):
            bindings.append(Binding(return_class, function, 0))
        else:
            raise NotImplementedError("Cannot parse line {n}")

    for binding in bindings:
        if binding.nparams == 0:
            typer.echo(template_param0(binding))
        elif binding.nparams == 1:
            typer.echo(template_param1(binding))


def main(
    qpdf_dir: Path = typer.Option(..., dir_okay=True, file_okay=False, exists=True)
):

    typer.echo("template <typename Class_>")
    typer.echo("void bind_jobconfig(Class_ &cl)")
    typer.echo("{")

    for filename in config_includes:
        include = qpdf_dir / filename
        typer.echo(f"    // {filename}")
        process(include)

    typer.echo("}")


if __name__ == '__main__':
    typer.run(main)
