#!/usr/bin/env python3
import codecs
import os.path

from setuptools import setup

here = os.path.abspath(os.path.dirname(__file__))

with open(os.path.join(here, "README.rst"), encoding="utf-8") as f:
    long_description = f.read()

setup(
    name="mlxc",
    version="0.0.1",
    description="My little XMPP client, an XMPP client based on aioxmpp",
    long_description=long_description,
    url="https://github.com/horazont/mlxc",
    author="Jonas Wielicki",
    author_email="jonas@wielicki.name",
    license="GPL",
    classifiers=[
        "Development Status :: 2 - Pre-Alpha",
        "Intended Audience :: End Users/Desktop",
        "License :: OSI Approved :: GNU General Public License v3 or later (GPLv3+)",
        "Operating System :: POSIX",
        "Programming Language :: Python :: 3 :: Only",
        "Programming Language :: Python :: 3.3",
        "Programming Language :: Python :: 3.4",
        "Topic :: Communications :: Chat",
    ],
    keywords="asyncio xmpp client qt",
    packages=["mlxc"],
)
