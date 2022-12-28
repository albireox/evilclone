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
@click.argument("VERSION", type=str)
def set_version(product: str, version: str):
    """Sets a modulefile version as default."""

    path = get_modulefile_path(product, version)

    module_dir = os.path.dirname(path)
    default = os.path.join(module_dir, "default")
    if os.path.exists(default):
        os.unlink(default)

    os.symlink(path, default)
    click.echo(click.style(f"Created default symlink {default}", fg="white"))


def run(command: str, shell=True, cwd=None) -> str | None:
    """Runs a command in a shell and return the stdout."""

    cmd = subprocess.run(command, shell=shell, capture_output=True, cwd=cwd)

    if cmd.returncode != 0:
        return None

    return cmd.stdout.decode(), cmd.stderr.decode()


def get_modulefile_path(product: str, version: str):
    """Gets the path to a modulefile."""

    module = f"{product}/{version}"

    result = run(f"module show {module}")
    if result is None:
        click.echo(click.style(f"Module {module} not found.", fg="red"))
        raise click.Abort()

    lines = result[1].splitlines()
    path = lines[1].strip()[:-1]

    click.echo(click.style(f"Module found at {path}", fg="white"))

    return path


if __name__ == "__main__":
    set_version()
