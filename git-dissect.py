#! /usr/bin/python3

import os
import sys
import git
import glob
import json
import socket
import atexit
import asyncio
import asyncssh


class GitDissect:

    def __init__(self):
        self.repo = git.Repo()
        if os.path.exists(self.config_path):
            self.conf = json.load(open(self.config_path))

    class DissectDone(Exception):
        pass

    @staticmethod
    def banner(host, prefix):
        return "[{}] {}:".format(host, prefix)

    @classmethod
    def _print_output(cls, fd, host, prefix):
        buf = os.read(fd, 0x1000)
        if not buf:
            loop = asyncio.get_event_loop()
            loop.remove_reader(fd)
            os.close(fd)
            return
        banner = cls.banner(host, prefix)
        print(banner, buf.decode().strip().replace("\n", "\n" + banner))

    async def _run_on_one(self, host, cmd):
        if isinstance(cmd, dict):
            cmd = cmd[host]
        cmd = "cd {}; {}".format(self.conf[host]["path"], cmd)
        print(self.banner(host, "exec"), repr(cmd))
        async with asyncssh.connect(host,
                                    username=self.conf[host]["user"]) as conn:
            out_rfd, out_wfd = os.pipe()
            err_rfd, err_wfd = os.pipe()
            loop = asyncio.get_event_loop()
            loop.add_reader(out_rfd, self._print_output, out_rfd, host, "out")
            loop.add_reader(err_rfd, self._print_output, err_rfd, host, "err")
            result = await conn.run(
                cmd, stdout=os.fdopen(out_wfd), stderr=os.fdopen(err_wfd))
            print(self.banner(host, "ret"), result.exit_status)
            return result

    def _run(self, cmd, hosts=None):
        if hosts is None:
            hosts = self.conf.keys()
        if not hosts:
            return {}
        loop = asyncio.get_event_loop()
        return dict(zip(hosts, loop.run_until_complete(asyncio.gather(*[
            self._run_on_one(host, cmd) for host in hosts]))))

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

    def execute(self, cmd, *args):
        if not cmd:
            cmd = "git dissect signal wait".split()
        return self._run(" ".join(cmd), *args)

    def fetch(self):
        self._run("git fetch")

    def checkout(self):
        bad = self.repo.commit("bisect/bad")
        goods = [name[len("good-"):] for name in glob.glob1(
            os.path.join(self.repo.git_dir, "refs/bisect"), "good-*")]
        revlist = self.repo.git.rev_list(bad, "--not", *goods).splitlines()
        hosts = self.conf.keys()
        shas = set(revlist[(len(revlist) * (i + 1)) //
                           (len(hosts) + 1)] for i in range(
            len(hosts))) - set([self.repo.commit("bisect/bad").hexsha])
        commitmap = dict(zip(sorted(hosts), sorted(shas)))
        try:
            os.remove(self.commitmap_path)
        except FileNotFoundError:
            pass
        if commitmap:
            self._run({host: "git checkout {}".format(sha) for
                       host, sha in commitmap.items()}, commitmap.keys())
        json.dump(commitmap, open(self.commitmap_path, "w"))
        if not commitmap:
            raise self.DissectDone()

    def collect(self, cmd):
        commitmap = json.load(open(self.commitmap_path))
        if not commitmap:
            raise self.DissectDone()
        results = self.execute(cmd, commitmap.keys())
        for host, sha in commitmap.items():
            retcode = results[host].exit_status
            mark = "bad" if retcode else "good"
            print("mark commit {} as {}".format(sha, mark))
            if self.repo.is_ancestor(sha, "bisect/bad"):
                    self.repo.git.bisect(mark, sha)

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
    subparsers = parser.add_subparsers(dest="task")
    subparsers.required = True
    config = subparsers.add_parser("config")
    config.add_argument("path")
    # tasks without parameters
    for task in ("fetch", "checkout"):
        subparsers.add_parser(task)
    # tasks that run a command
    for task in ("execute", "collect", "step", "run"):
        p = subparsers.add_parser(task)
        p.add_argument("cmd", nargs="*")
    signal = subparsers.add_parser("signal")
    signal.add_argument("action", choices=["good", "bad", "wait"])
    args = parser.parse_args()
    GitDissect().main(**args.__dict__)
