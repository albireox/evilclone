#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# @Author: José Sánchez-Gallego (gallegoj@uw.edu)
# @Date: 2021-08-11
# @Filename: evilclone.py
# @License: BSD 3-clause (http://www.opensource.org/licenses/BSD-3-Clause)

from __future__ import annotations

import os
import re
import subprocess
import sys
from getpass import getuser
from glob import glob
from shutil import rmtree

try:
    import click
except ImportError:
    print("Click needs to be installed.")
    sys.exit(1)

PRODUCT_DIR = "/home/sdss5/software/"


@click.command()
@click.argument("PRODUCT", type=str)
@click.option("--clone", is_flag=True, help="Clone the a repository.")
@click.option(
    "-d",
    "--dir",
    type=click.Path(exists=True, file_okay=False),
    help="Root of the products directory.",
)
@click.option(
    "-m",
    "--modulepath",
    type=click.Path(exists=True, file_okay=False),
    help="Root of the modulefiles path.",
)
@click.option("-b", "--branch", type=str, default="main", help="Branch to checkout.")
@click.option("-e", "--environment", type=str, help="Name of the virtual environment.")
@click.option("-y", "--yes", is_flag=True, help="Accept default values.")
def evilclone(
    product: str,
    clone=False,
    environment: str = None,
    branch: str = "main",
    dir: str | None = None,
    modulepath: str | None = None,
    yes=False,
):
    """Install operations software à la SDSS."""

    if dir:
        product_dir = str(dir)
    else:
        product_dir = PRODUCT_DIR

    lmod_envvars = {}
    repo_path = None

    if clone:
        product = get_repo_path(product, branch=branch)
        env = create_environment(
            environment,
            product,
            is_repo=True,
            branch=branch,
            yes=yes,
        )
        repo_path = clone_repo(
            product,
            env,
            product_dir=product_dir,
            branch=branch,
            yes=yes,
        )
        install_repo(repo_path, env, yes=yes)
        lmod_envvars["PATH"] = os.path.join(repo_path, "bin")
        lmod_envvars["PYTHONPATH"] = repo_path

    else:
        env = create_environment(environment, product, is_repo=False, yes=yes)
        click.echo(click.style("pip-installing product.", fg="blue"))
        run(
            'eval "$(pyenv init -)" && '
            'eval "$(pyenv virtualenv-init -)" && '
            f"pyenv shell {env} && "
            f"pip install {product}"
        )

    create_modulefile(
        product,
        env,
        is_repo=clone,
        branch=branch,
        repo_path=repo_path,
        envvars=lmod_envvars,
        modulepath=modulepath,
        yes=yes,
    )


def fail(msg: str | None = None):
    if msg:
        click.echo(click.style(msg, fg="red"))
    raise click.Abort()


def run(command: str, shell=True, cwd=None) -> str:
    """Runs a command in a shell and return the stdout."""

    cmd = subprocess.run(command, shell=shell, capture_output=True, cwd=cwd)

    if cmd.returncode != 0:
        fail(f"Command {command} failed with error: {cmd.stderr.decode()}")

    return cmd.stdout.decode()


def yn(msg: str, default="y", yes=False) -> bool:
    """Yes/no prompt."""

    if yes:
        return True

    res = click.prompt(
        msg,
        type=click.Choice(["Y", "n"], case_sensitive=False),
        default=default.upper(),
        show_choices=False,
        value_proc=lambda x: x.lower(),
    )

    return True if res == "y" else False


def get_repo_path(product: str, branch="main"):
    """Returns the path to the repository."""

    if product.startswith("http"):
        fail("Repositories must use git@github.com paths.")

    if not product.startswith("git@"):
        product = "git@github.com:" + product

    return product


def get_product_parts(product: str):
    """Split dependency specification into name and version."""

    match = re.match(r"([a-zA-Z0-9_-]+)[><=~!]*([0-9.]*)", product)
    assert match and (match.group(2) is None or match.group(2) != "")
    return match.groups()


def create_environment(
    environment: str | None,
    product: str,
    is_repo=False,
    branch="main",
    yes=False,
) -> str:
    """Creates the virtual environment."""

    pyenv_versions = run("pyenv versions")
    versions = list(map(lambda x: x.strip(), pyenv_versions.splitlines()))

    if environment is None:
        if is_repo:
            environment = getuser() + "-" + product.split("/")[-1] + "-" + branch
        else:
            name, version = get_product_parts(product)
            if version:
                environment = getuser() + "-" + name + "-" + version

    if environment in versions:
        if yn("Environment already exists. Use it?", yes=yes):
            return environment
        else:
            fail()
    else:
        if environment is None or not yn(f"Create environment {environment}?", yes=yes):
            environment = click.prompt("Environment name:")
            if not environment:
                fail()

        click.echo(
            click.style(
                f"Creating virtual environment {environment}.",
                fg="blue",
            )
        )

        pyenv_global = run("pyenv global").strip()
        run(f"pyenv virtualenv {pyenv_global} {environment}")
        run(
            'eval "$(pyenv init -)" && '
            f"pyenv shell {environment} && "
            "pip install -U pip setuptools wheel"
        )

        return environment


def clone_repo(
    repo_url: str,
    environment: str,
    product_dir=PRODUCT_DIR,
    branch="main",
    yes=False,
):
    """Clones a repo."""

    name = repo_url.split("/")[-1]
    default_path = os.path.join(product_dir, name, branch)

    if yes:
        path = default_path
    else:
        path = click.prompt("Path for cloned repository?", default=default_path)

    if os.path.exists(path):
        fail("Path already exists.")

    click.echo(click.style("Cloning repository.", fg="blue"))
    run(f"git clone {repo_url} {path}")

    os.chdir(path)

    branch_output = run("git status --branch --porcelain")
    match = re.match(r"## (.+)\.\.\..+", branch_output)
    if not match:
        fail("Cannot parse current branch")
    current_branch = match.groups()[0]

    if current_branch != branch:
        run(f"git checkout -b {branch}")

    with open(".python-version", "w") as f:
        f.write(environment)

    tags = map(lambda x: x.strip(), run("git tag").splitlines())
    if branch in tags:
        rmtree(os.path.join(path, ".git"))

    return path


def install_repo(repo_path: str, environment: str, yes=False):
    """Install the repository."""

    os.chdir(repo_path)
    files = glob("*")

    if "pyproject.toml" in files:
        command = "poetry install"
        prompt = "Poetry install?"
    elif "setup.py" in files:
        command = "pip install -e ."
        prompt = "Pip install repository?"
    else:
        if not yn("Cannot find setup.py or pyproject.py. Continue?", yes=yes):
            fail()
        else:
            return

    if yn(prompt, yes=yes):

        if command == "poetry install":
            click.echo(
                click.style(
                    "Poetry installation is not currently supported. "
                    "Install the product manually.",
                    fg="yellow",
                )
            )

        else:
            click.echo(click.style("Running installation.", fg="blue"))
            run(
                'eval "$(pyenv init -)" && '
                'eval "$(pyenv virtualenv-init -)" && '
                f"cd {repo_path} && "
                f"pyenv shell --unset && "
                f"{command}",
            )

    return


def create_modulefile(
    product: str,
    environment: str,
    is_repo=False,
    branch="main",
    repo_path: str | None = None,
    envvars={},
    modulepath: str | None = None,
    yes=False,
):
    """Creates the modulefile."""

    if not yn("Create modulefile?", yes=yes):
        fail()

    if modulepath is None:
        modulepath = os.environ["MODULEPATH"]
    else:
        modulepath = str(modulepath)

    if is_repo:
        name = product.split("/")[-1]
        version = branch
    else:
        name, version = get_product_parts(product)

    modulepath = os.path.join(modulepath, name, version + ".lua")

    if yes is False:
        modulepath = click.prompt("Module path:", default=modulepath)
    if not modulepath:
        fail()
    if os.path.exists(modulepath):
        fail("Module path already exists.")

    dep_prompt = click.prompt(
        "Space-separated modules to load with this product",
        default="",
    )
    if not dep_prompt:
        deps = None
    else:
        deps = dep_prompt.split()

    lines = [f"conflict('{name}')", ""]

    if deps:
        for dep in deps:
            lines += [f"load({dep})", f"prereq({dep})", ""]

    if is_repo and repo_path:
        lines += [f"setenv('{name.upper()}_DIR', '{repo_path}')"]

    for env in envvars:
        if env.endswith("PATH") and not os.path.exists(envvars[env]):
            continue
        lines += [
            f"prepend_path{{'{env.upper()}', '{envvars[env]}', "
            "delim=':', priority='0'}"
        ]

    if lines[-1] != "":
        lines += [""]

    lines += [f"setenv('PYENV_VERSION', '{environment}')", ""]

    dirpath = os.path.realpath(os.path.dirname(modulepath))
    os.makedirs(dirpath, exist_ok=True)

    with open(modulepath, "w") as modulefile:
        data = "\n".join(lines)
        modulefile.write(data)

    click.echo(click.style(f"Created modulefile {modulepath}.", fg="blue"))

    if yn("Make default?"):
        dest = os.path.join(dirpath, "default")
        if os.path.exists(dest):
            os.unlink(dest)
        os.symlink(modulepath, dest)


if __name__ == "__main__":
    evilclone()
