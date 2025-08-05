#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# @Author: José Sánchez-Gallego (gallegoj@uw.edu)
# @Date: 2022-12-27
# @Filename: set-version.py
# @License: BSD 3-clause (http://www.opensource.org/licenses/BSD-3-Clause)

from __future__ import annotations

import os
import os.path
import pathlib
import re
import subprocess
import sys

try:
    import click
except ImportError:
    print("Click needs to be installed.")
    sys.exit(1)


@click.command(name="set-version")
@click.argument("PRODUCT", type=str)
@click.argument("VERSION", type=str, required=False)
def set_version(product: str, version: str | None = None):
    """Sets a modulefile version as default."""

    if "/" in product:
        product, version = product.split("/")

    if version is None:
        get_default_version(product)
        return

    path = get_modulefile_path(product, version)

    module_dir = os.path.dirname(path)
    default = os.path.join(module_dir, "default")
    if os.path.exists(default):
        os.unlink(default)

    os.symlink(path, default)
    click.echo(f"Created default symlink {default}")


def run(command: str, shell=True, cwd=None) -> tuple[str | None, str | None] | None:
    """Runs a command in a shell and return the stdout."""

    # This seems necessary at LCO
    if os.environ.get("OBSERVATORY", None) == "LCO":
        command = "source /home/sdss5/config/bash/00_lmod.sh && " + command

    cmd = subprocess.run(command, shell=shell, capture_output=True, cwd=cwd)

    if cmd.returncode != 0:
        return None

    return cmd.stdout.decode(), cmd.stderr.decode()


def get_default_version(product: str) -> str | None:
    """Gets the default version of a product."""

    result = run(f"module --redirect -t -d avail {product}")
    if result is None or result[0] is None:
        click.echo(click.style(f"Module {product} not found.", fg="red"))
        return None

    output = result[0].strip()

    match = re.match(r"^(.+):\n(.+)$", output, re.MULTILINE)
    if not match:
        click.echo(click.style(f"Module {product} not found.", fg="red"))
        return None

    path = pathlib.Path(match.group(1).strip()) / match.group(2).strip()
    if not path.exists():
        if (lua_path := path.with_name(path.name + ".lua")).exists():
            path = lua_path
        else:
            click.echo(click.style(f"Module {product} not found.", fg="red"))
            return None

    print("Default modulefile path:", path)

    return str(path)


def get_modulefile_path(product: str, version: str):
    """Gets the path to a modulefile."""

    module = f"{product}/{version}"

    result = run(f"module --redirect show {module}")
    if result is None or result[0] is None:
        click.echo(click.style(f"Module {module} not found.", fg="red"))
        raise click.Abort()

    lines = result[0].splitlines()
    path = lines[1].strip()[:-1]

    click.echo(f"Module found at {path}")

    return path


if __name__ == "__main__":
    set_version()
