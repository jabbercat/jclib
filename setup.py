#!/usr/bin/env python3
import os.path

from setuptools import setup, find_packages

here = os.path.abspath(os.path.dirname(__file__))

with open(os.path.join(here, "README.rst"), encoding="utf-8") as f:
    long_description = f.read()

setup(
    name="jclib",
    version="0.1.0",
    description="Core library for the JabberCat XMPP IM client.",
    long_description=long_description,
    url="https://github.com/jabbercat/jclib",
    author="Jonas Wielicki",
    author_email="jonas@wielicki.name",
    license="GPL",
    classifiers=[
        "Development Status :: 2 - Pre-Alpha",
        "Intended Audience :: Developers",
        "License :: OSI Approved :: "
        "GNU General Public License v3 or later (GPLv3+)",
        "Operating System :: POSIX",
        "Programming Language :: Python :: 3 :: Only",
        "Programming Language :: Python :: 3.4",
        "Programming Language :: Python :: 3.5",
        "Programming Language :: Python :: 3.6",
        "Topic :: Communications :: Chat",
    ],
    keywords="asyncio xmpp client aioxmpp",
    packages=find_packages(exclude=["tests"]),
    install_requires=[
        "hsluv~=0.0.2"
    ]
)
