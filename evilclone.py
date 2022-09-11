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
from glob import glob
from shutil import rmtree
from typing import Tuple, cast

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
@click.option("-t", "--tag", type=str, help="Tag to checkout.")
@click.option("-e", "--environment", type=str, help="Name of the virtual environment.")
@click.option("-y", "--yes", is_flag=True, help="Accept default values.")
def evilclone(
    product: str,
    clone=False,
    environment: str | None = None,
    branch: str = "main",
    tag: str | None = None,
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

    name = get_name(product, is_repo=clone)

    if clone:
        product = get_repo_path(product)
        environment = create_environment(
            environment,
            product,
            is_repo=True,
            branch=branch,
            tag=tag,
            name=name,
            yes=yes,
        )
        repo_path = clone_repo(
            product,
            environment,
            product_dir=product_dir,
            branch=branch,
            tag=tag,
            yes=yes,
        )
        install_repo(repo_path, environment, yes=yes)

    else:
        environment = create_environment(
            environment,
            product,
            is_repo=False,
            name=name,
            yes=yes,
        )
        click.echo(click.style("pip-installing product.", fg="blue"))
        run_with_pyenv(f"pip install {product}", environment)

    create_modulefile(
        product,
        environment,
        is_repo=clone,
        branch=branch,
        tag=tag,
        name=name,
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


def run_with_pyenv(command: str, environment: str, **kwargs):
    """Runs a command in a valid pyenv environment."""

    # This is a hack but it seems to be necessary when running in a subprocess.

    env_path = get_env_path(environment)

    full_command = (
        'eval "$(pyenv init --path -)" && '
        'export PATH="$PYENV_ROOT/bin:$PATH" && '
        'export PATH="$PYENV_ROOT/shims:$PATH" && '
        'eval "$(pyenv init -)" && '
        f"pyenv shell {environment} && "
        f"export VIRTUAL_ENV='{env_path}' && "
        f"{command}"
    )

    run(full_command, **kwargs)


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


def get_name(product: str, is_repo=False) -> str:
    """Prompts for the product name."""

    if not is_repo:
        name, _ = get_product_parts(product)
    else:
        name = product.split("/")[-1]

    name = click.prompt("Product name", default=name)

    return name


def get_repo_path(product: str):
    """Returns the path to the repository."""

    if product.startswith("http"):
        fail("Repositories must use git@github.com paths.")

    if not product.startswith("git@"):
        product = "git@github.com:" + product

    return product


def get_product_parts(product: str) -> Tuple[str, str]:
    """Split dependency specification into name and version."""

    match = re.match(r"([a-zA-Z0-9_-]+)[><=~!]*([0-9.]*)", product)
    assert match and (match.group(2) is None or match.group(2) != "")
    return cast(Tuple[str, str], match.groups())


def create_environment(
    environment: str | None,
    product: str,
    is_repo: bool = False,
    branch: str = "main",
    tag: str | None = None,
    name: str | None = None,
    yes: bool = False,
) -> str:
    """Creates the virtual environment."""

    if tag is not None:
        branch = tag

    if environment is None:
        if is_repo:
            branch_safe = branch.replace("/", "_")
            environment = product.split("/")[-1] + "-" + branch_safe
        else:
            auto_name, version = get_product_parts(product)
            name = name or auto_name
            if version:
                environment = name + "-" + version

    environment = click.prompt("Environment name", default=environment)
    if not environment:
        fail()

    pyenv_versions = run("pyenv versions --bare")
    versions = list(map(lambda x: x.strip(), pyenv_versions.splitlines()))

    pyenv_global = run("pyenv global").strip()

    if environment in versions:
        if yn("Environment already exists. Use it?", yes=yes):
            return environment
        else:
            fail()
    else:
        base_version = click.prompt("Base version", default=pyenv_global)
        click.echo(
            click.style(
                f"Creating virtual environment {environment}.",
                fg="blue",
            )
        )

        run(f"pyenv virtualenv {base_version} {environment}")

        run_with_pyenv("pip install -U pip setuptools wheel", environment)

        return environment


def clone_repo(
    repo_url: str,
    environment: str,
    product_dir: str = PRODUCT_DIR,
    branch: str = "main",
    tag: str | None = None,
    yes: bool = False,
):
    """Clones a repo."""

    is_tag = False

    if tag is not None:
        branch = tag
        is_tag = True

    name = repo_url.split("/")[-1]
    default_path = os.path.join(product_dir, name, branch.replace("/", "_"))

    if yes:
        path = default_path
    else:
        path = click.prompt("Path for cloned repository?", default=default_path)

    if os.path.exists(path):
        if yn("Path already exists. Use it?"):
            return path
        else:
            fail()

    click.echo(click.style("Cloning repository.", fg="blue"))
    run(f"git clone {repo_url} {path}")

    os.chdir(path)

    branch_output = run("git status --branch --porcelain")
    match = re.match(r"## (.+)\.\.\..+", branch_output)
    if not match:
        fail("Cannot parse current branch")
    current_branch = match.groups()[0]

    if current_branch != branch:
        if is_tag:
            run(f"git checkout -b {branch} {tag}")
        else:
            run(f"git checkout -b {branch} origin/{branch}")

    with open(".python-version", "w") as f:
        f.write(environment)

    if is_tag:
        rmtree(os.path.join(path, ".git"))

    return path


def get_env_path(environment: str):
    """Get the environment path."""

    python_versions = run("pyenv versions --bare --skip-aliases").splitlines()

    env_path = None

    for version in python_versions:
        if environment in version:
            env_path = os.path.join(os.environ["PYENV_ROOT"], "versions", version)

    if env_path is None:
        fail("Cannot find environment.")

    return env_path


def install_repo(repo_path: str, environment: str, yes=False) -> bool:
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
            return False

    if yn(prompt, yes=yes):
        click.echo(click.style("Running installation.", fg="blue"))
        run_with_pyenv(command, environment)
        return True

    return False


def create_modulefile(
    product: str,
    environment: str,
    is_repo: bool = False,
    branch: str = "main",
    tag: str | None = None,
    name: str | None = None,
    repo_path: str | None = None,
    envvars={},
    modulepath: str | None = None,
    yes: bool = False,
):
    """Creates the modulefile."""

    if not yn("Create modulefile?", yes=yes):
        fail()

    if modulepath is None:
        modulepath = "/home/sdss5/software/modulefiles"

    if is_repo:
        name = name or product.split("/")[-1]
        version = tag or branch
    else:
        if name:
            _, version = get_product_parts(product)
        else:
            name, version = get_product_parts(product)

    assert name
    modulepath = os.path.join(modulepath, name, version + ".lua")

    if yes is False:
        modulepath = click.prompt("Module path", default=modulepath)
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

    if repo_path:
        if yn("Add PYTHONPATH?", default="n"):
            pythonpath = click.prompt("PYTHONATH to use", default="repo_path")
            envvars["PYTHONPATH"] = pythonpath

    if yn("Add to PATH?", default="n") and repo_path:
        default_path = os.path.join(repo_path, "bin")
        path = click.prompt("PYTHONATH to use", default=default_path)
        envvars["PATH"] = path

    lines = [f"conflict('{name}')", ""]

    if deps:
        for dep in deps:
            lines += [f"load('{dep}')", f"prereq('{dep}')", ""]

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
