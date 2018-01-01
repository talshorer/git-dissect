#! /usr/bin/python3

import os
import sys
import git
import glob
import json
import socket
import atexit
import contextlib
import fabric.api


class GitDissect:

    def __init__(self):
        self.repo = git.Repo()
        if os.path.exists(self.config_path):
            self.conf = json.load(open(self.config_path))

    class DissectDone(Exception):
        pass

    @property
    def key(self):
        return "{}@{}".format(fabric.api.env.user, fabric.api.env.host)

    @property
    def remote_path(self):
        return self.conf[self.key]

    @property
    def commitmap_path(self):
        return os.path.join(self.repo.git_dir, "DISSECT_COMMITMAP")

    @property
    def config_path(self):
        return os.path.join(self.repo.git_dir, "DISSECT_CONFIG")

    @property
    def signal_path(self):
        return os.path.join(self.repo.git_dir, "DISSECT_SIGNAL")

    def config(self, path):
        try:
            os.remove(self.config_path)
        except FileNotFoundError:
            pass
        if not os.path.isabs(path):
            path = os.path.relpath(path, self.repo.git_dir)
        os.symlink(path, self.config_path)

    def execute(self, cmd):
        @fabric.api.task
        @fabric.api.parallel
        def execute(*cmd):
            if not cmd:
                cmd = "git dissect signal wait".split()
            with contextlib.ExitStack() as stack:
                stack.enter_context(fabric.api.settings(warn_only=True))
                stack.enter_context(fabric.api.cd(self.remote_path))
                return fabric.api.run(
                    " ".join(cmd), shell=False, shell_escape=True).return_code
        return fabric.api.execute(execute, *cmd, hosts=self.conf.keys())

    def fetch(self):
        self.execute("git fetch".split())

    def checkout(self):
        bad = self.repo.commit("bisect/bad")
        goods = [name[len("good-"):] for name in glob.glob1(
            os.path.join(self.repo.git_dir, "refs/bisect"), "good-*")]
        revlist = [line.split()[0] for line in self.repo.git.rev_list(
            bad, "--not", *goods, bisect_all=True).splitlines()]
        hosts = self.conf.keys()
        shas = set(revlist[(len(revlist) * i) // len(hosts)] for i in range(
            len(hosts))) - set([self.repo.commit("bisect/bad").hexsha])
        commitmap = dict(zip(sorted(hosts), sorted(shas)))
        try:
            os.remove(self.commitmap_path)
        except FileNotFoundError:
            pass

        @fabric.api.task
        @fabric.api.parallel
        def checkout(hash):
            with fabric.api.cd(self.remote_path):
                fabric.api.run("git checkout {}".format(commitmap[self.key]))

        if commitmap:
            fabric.api.execute(checkout, commitmap, hosts=commitmap.keys())
        json.dump(commitmap, open(self.commitmap_path, "w"))
        if not commitmap:
            raise self.DissectDone()

    def collect(self, cmd):
        commitmap = json.load(open(self.commitmap_path))
        if not commitmap:
            raise self.DissectDone()
        retcodes = self.execute(cmd)
        for key, sha in commitmap.items():
            retcode = retcodes[key]
            if retcode:
                if self.repo.is_ancestor(sha, "bisect/bad"):
                    self.repo.git.bisect("bad", sha)
            else:
                self.repo.git.bisect("good", sha)

    def step(self, cmd):
        self.checkout()
        self.collect(cmd)

    def run(self, cmd):
        while True:
            self.step(cmd)

    def signal(self, action):
        with socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM) as sock:
            if action == "wait":
                sock.bind(self.signal_path)
                atexit.register(lambda: os.remove(self.signal_path))
                retcode = ord(sock.recv(1))
                sys.exit(retcode)
            else:
                sock.connect(self.signal_path)
                retcode = {
                    "good": 0,
                    "bad": 1,
                }[action]
                sock.send(chr(retcode))

    def main(self, task, *args, **kw):
        try:
            getattr(self, task)(*args, **kw)
        except self.DissectDone:
            print("{} is the first bad commit".format(
                self.repo.commit("bisect/bad")))


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="subparser")
    subparsers.required = True
    config = subparsers.add_parser("config")
    config.add_argument("path")
    fetch = subparsers.add_parser("fetch")
    checkout = subparsers.add_parser("checkout")
    execute = subparsers.add_parser("execute")
    collect = subparsers.add_parser("collect")
    step = subparsers.add_parser("step")
    run = subparsers.add_parser("run")
    for p in (execute, collect, step, run):
        p.add_argument("cmd", nargs="*")
    signal = subparsers.add_parser("signal")
    signal.add_argument("action", choices=["good", "bad", "wait"])
    args = parser.parse_args()
    task = args.__dict__.pop("subparser")
    GitDissect().main(task, **args.__dict__)
