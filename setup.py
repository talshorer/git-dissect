#! /usr/bin/env python3

from setuptools import setup

setup(
    name="git_dissect",
    version="0.3",
    description="Distributed git bisect",
    author="Tal Shorer",
    author_email="tal.shorer@gmail.com",
    url="https://github.com/talshorer/git-dissect",
    py_modules=["git_dissect"],
    entry_points=dict(console_scripts=[
        "git-dissect = git_dissect:_main",
    ]),
    install_requires=[
        "gitpython",
        "asyncssh",
        "paramiko",
    ],
)
