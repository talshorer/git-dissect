#! /usr/bin/env python3

import os
import sys
import git
import glob
import shutil
import socket
import atexit
import getpass
import asyncio
import argparse
import asyncssh
import functools
import contextlib


class ProxyCommandTunnel:
    def __init__(self, cmd):
        self.cmd = cmd

    @staticmethod
    def socketpair():
        with socket.socket() as s:
            s.bind(("127.0.0.1", 0))
            s.listen(1)
            c = socket.create_connection(s.getsockname())
            a, _ = s.accept()
            return c, a

    async def create_connection(self, session_factory, host, port):
        stdio, tunnel = self.socketpair()
        subprocess = await asyncio.create_subprocess_shell(
            self.cmd, stdin=stdio, stdout=stdio)
        loop = asyncio.get_event_loop()
        loop.create_task(subprocess.wait())
        return await loop.create_connection(session_factory, sock=tunnel)


class GitDissect:

    def __init__(self):
        self.repo = git.Repo()
        self.conf = self._read_conf()
        self.connections = {}

    class DissectDone(Exception):
        pass

    def _read_conf(self):
        config_reader = self.repo.config_reader()
        conf = {}
        section_start = "dissect \""
        if config_reader.getboolean("dissect", "usesshconfig", fallback=True):
            import paramiko
            self.sshconfig = paramiko.SSHConfig()
            for path in ("/etc/ssh/ssh_config", "~/.ssh/config"):
                try:
                    with open(os.path.expanduser(path), "r") as f:
                        self.sshconfig.parse(f)
                except FileNotFoundError:
                    pass
        else:
            self.sshconfig = argparse.Namespace()
            self.sshconfig.lookup = lambda host: {}
        for section in config_reader.sections():
            if not section.startswith(section_start):
                continue
            if not config_reader.getboolean(section, "enabled", fallback=True):
                continue
            host = section[len(section_start):-1]
            options = config_reader.options(section)
            if "path" not in options:
                continue
            conf[host] = {option: config_reader.get_value(section, option) for
                          option in options if not option.startswith("_")}
        return conf

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
        print(banner, buf.decode().strip().replace("\n", "\n" + banner + " "))

    async def _run_on_one(self, host, cmd):
        if isinstance(cmd, dict):
            cmd = cmd[host]
        cmd = "cd {}; {}".format(self.conf[host]["path"], cmd)
        print(self.banner(host, "exec"), repr(cmd))
        out_rfd, out_wfd = os.pipe()
        err_rfd, err_wfd = os.pipe()
        loop = asyncio.get_event_loop()
        loop.add_reader(out_rfd, self._print_output, out_rfd, host, "out")
        loop.add_reader(err_rfd, self._print_output, err_rfd, host, "err")
        result = await self.connections[host].run(
            cmd, stdout=os.fdopen(out_wfd), stderr=os.fdopen(err_wfd))
        print(self.banner(host, "ret"), result.exit_status)
        return result

    @staticmethod
    async def _gather(hosts, coro):
        values = await asyncio.gather(*[coro(host) for host in hosts])
        return dict(zip(hosts, values))

    def _run(self, cmd, hosts=None):
        if hosts is None:
            hosts = self.conf.keys()
        if not hosts:
            return {}
        self._connect(set(hosts) - set(self.connections.keys()))
        loop = asyncio.get_event_loop()
        return loop.run_until_complete(self._gather(
            hosts, functools.partial(self._run_on_one, cmd=cmd)))

    _DEFAULT_CONF_VALUE = object()

    def _get_conf_value_gitconfig(self, host, key, default):
        return self.conf[host].get(key, self._DEFAULT_CONF_VALUE)

    def _get_conf_value_sshconfig(self, host, key, default):
        value = self.sshconfig.lookup(host).get(key, self._DEFAULT_CONF_VALUE)
        if value is self._DEFAULT_CONF_VALUE:
            return value
        if isinstance(default, bool):
            if value == "yes":
                return True
            elif value == "no":
                return False
            else:
                raise ValueError(
                    "Invalid boolean value {}.{} in sshconfig: {}".format(
                        host, key, value))
        elif isinstance(default, int):
            return int(value)
        elif isinstance(default, str):
            return value
        raise ValueError("Can't convert value {} to type {}".format(
            value, type(default)))

    def _get_conf_value_default(self, host, key, default):
        return default

    def _get_conf_value(self, host, key, default):
        for method in (
            self._get_conf_value_gitconfig,
            self._get_conf_value_sshconfig,
            self._get_conf_value_default,
        ):
            value = method(host, key, default)
            if value is not self._DEFAULT_CONF_VALUE:
                return value
        raise ValueError("Host {} missing value for {}".format(host, key))

    def _username(self, host):
        return self._get_conf_value(host, "user", getpass.getuser())

    def _hostname(self, host):
        return self._get_conf_value(host, "hostname", host)

    def _port(self, host):
        return self._get_conf_value(host, "port", 22)

    def _known_hosts(self, host):
        if self._get_conf_value(host, "stricthostkeychecking", True):
            return ()
        else:
            return None

    def _tunnel(self, host, port, username):
        proxycommand = self._get_conf_value(host, "proxycommand", "none")
        if proxycommand.lower() == "none":
            return None
        return ProxyCommandTunnel(functools.reduce(
            lambda a, b: a.replace(*b),
            (
                ("%h", host),
                ("%p", str(port)),
                ("%r", username),
            ),
            proxycommand,
        ))

    async def _connect_one(self, host):
        port = self._port(host)
        username = self._username(host)
        conn, _ = await asyncssh.create_connection(
            client_factory=None,
            host=self._hostname(host),
            port=port,
            username=username,
            known_hosts=self._known_hosts(host),
            tunnel=self._tunnel(host, port, username),
        )
        return conn

    def _connect(self, hosts):
        loop = asyncio.get_event_loop()
        self.connections.update(loop.run_until_complete(self._gather(
            list(hosts), self._connect_one)))

    def __enter__(self):
        return self

    async def _disconnect_one(self, host):
        self.connections[host].close()
        await self.connections[host].wait_closed()

    def __exit__(self, *args):
        loop = asyncio.get_event_loop()
        loop.run_until_complete(self._gather(
            self.connections.keys(), self._disconnect_one))
        self.connections = {}

    @property
    def refs_dir(self):
        return os.path.join(self.repo.git_dir, "refs/dissect")

    def host_ref_path(self, host):
        return os.path.join(self.refs_dir, host)

    @property
    def signal_path(self):
        return os.path.join(self.repo.git_dir, "DISSECT_SIGNAL")

    @contextlib.contextmanager
    def bisect_log_append(self, prefix, sha):
        with open(os.path.join(self.repo.git_dir, "BISECT_LOG"), "a") as f:
            f.write("# {}: [{}] {}\n".format(
                prefix, sha, self.repo.commit(sha).summary))
            yield f

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
            shutil.rmtree(self.refs_dir)
        except FileNotFoundError:
            pass
        if commitmap:
            self._run({host: "git checkout {}".format(sha) for
                       host, sha in commitmap.items()}, commitmap.keys())
        os.mkdir(self.refs_dir)
        for host, sha in commitmap.items():
            with open(self.host_ref_path(host), "w") as f:
                f.write("{}\n".format(sha))
        if not commitmap:
            with self.bisect_log_append("first bad commit",
                                        self.repo.commit("bisect/bad")):
                pass
            raise self.DissectDone()

    def collect(self, cmd):
        hosts = os.listdir(self.refs_dir)
        results = self.execute(cmd, hosts)
        for host in hosts:
            with open(self.host_ref_path(host), "r") as f:
                sha = f.read().strip()
            retcode = results[host].exit_status
            bad = "bisect/bad"
            if self.repo.is_ancestor(sha, bad):
                if retcode:
                    ref = bad
                    mark = "bad"
                else:
                    ref = "bisect/good-{}".format(sha)
                    mark = "good"
                print("update ref {} to {}".format(ref, sha))
                self.repo.git.update_ref("refs/{}".format(ref), sha)
                with self.bisect_log_append(mark, sha) as f:
                    f.write("git bisect {} {}\n".format(mark, sha))
            else:
                print("{} is no longer an ancestor of {}. skipping it".format(
                    sha, bad))

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
            with self:
                getattr(self, task)(*args, **kw)
        except self.DissectDone:
            print("{} is the first bad commit".format(
                self.repo.commit("bisect/bad")))


def _main():
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="task")
    subparsers.required = True
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


if __name__ == "__main__":
    _main()
