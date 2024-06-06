# -*- coding: utf-8 -*-
import os
from setuptools import setup


def read(fname):
    return open(os.path.join(os.path.dirname(__file__), fname)).read()


def get_version():
    """Get version from the package without actually importing it."""
    init = read("jarpcdantic/__init__.py")
    for line in init.split("\n"):
        if line.startswith("__version__"):
            return eval(line.split("=")[1])


setup(
    name="jarpcdantic",
    version=get_version(),
    description="JSON Advanced RPC with Pydantic",
    packages=["jarpcdantic"],
    requires=["pydantic"],
    long_description=read("README.md"),
    long_description_content_type="text/markdown",
    maintainer="WhiteApfel",
    maintainer_email="white@pfel.ru",
    url='https://github.com/whiteapfel/jarpcdantic/',
    download_url='https://pypi.org/project/jarpcdantic/',
    license="Mozilla Public License 2.0",
    classifiers=[
        "Development Status :: 3 - Alpha",
        "Programming Language :: Python :: 3.12",
        "Intended Audience :: Developers",
        "License :: OSI Approved :: Mozilla Public License 2.0 (MPL 2.0)",
        "Topic :: Utilities",
    ],
)
