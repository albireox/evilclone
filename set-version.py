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

    if '/' in product:
        product, version = product.split('/')

    path = get_modulefile_path(product, version)

    if version is None:
        return

    module_dir = os.path.dirname(path)
    default = os.path.join(module_dir, "default")
    if os.path.exists(default):
        os.unlink(default)

    os.symlink(path, default)
    click.echo(click.style(f"Created default symlink {default}", fg="white"))


def run(command: str, shell=True, cwd=None) -> tuple[str | None, str | None] | None:
    """Runs a command in a shell and return the stdout."""

    # This seems necessary at LCO
    if os.environ.get('OBSERVATORY', None) == "LCO":
        command = 'source /home/sdss5/config/bash/00_lmod.sh && ' + command

    cmd = subprocess.run(command, shell=shell, capture_output=True, cwd=cwd)

    if cmd.returncode != 0:
        return None

    return cmd.stdout.decode(), cmd.stderr.decode()


def get_modulefile_path(product: str, version: str | None = None):
    """Gets the path to a modulefile."""

    module = f"{product}/{version}" if version else product

    result = run(f"module show {module}")
    if result is None or result[1] is None:
        click.echo(click.style(f"Module {module} not found.", fg="red"))
        raise click.Abort()

    lines = result[1].splitlines()
    path = lines[1].strip()[:-1]

    if version:
        click.echo(click.style(f"Module found at {path}", fg="white"))
    else:
        click.echo(click.style(f"Default module is {path}", fg="white"))

    return path


if __name__ == "__main__":
    set_version()
