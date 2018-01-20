# git-dissect: DIStributed biSECT

`git-dissect` is an alternative to `git bisect` that allows running tests on
multiple hosts in order to bisect faster.  
It was inspired by Rob Hoelz's [git-pisect](https://github.com/hoelzro/git-pisect).

## Installation
    $ sudo pip3 install asyncssh gitpython
    $ git clone https://github.com/talshorer/git-dissect.git
    $ cd git-dissect
    $ # Install for the current user only
    $ ./setup.py install --user
    $ git config --global alias.dissect '!python3 -m git-dissect'
    $ # Install for everyone using the system
    $ sudo ./setup.py install
    $ sudo git config --system alias.dissect '!python3 -m git-dissect'

## Usage
Start as you would start a normal bisect:

    $ git bisect start --no-checkout
    $ git bisect bad $BAD_COMMIT
    $ git bisect good $GOOD_COMMIT
Note: It is recommended to start `git bisect` with the `--no-checkout` option
when using `git-dissect`.

### Configuration
__WARNING__: The configuration scheme is not final and will likely be moved into
`git config` at some point to allow for easier management across multiple
repositories.  
`git-dissect` uses a JSON configuration to manage its hosts.  
The configuration is a JSON object, where each member represents one host.  
It is best demonstrated with an example:
```
{
  "20.0.0.2": {
    "user": "root",
    "path": "/tmp/dissect-example"
  },
  "horse": {
    "hostname": "20.0.1.2",
    "user": "root",
    "path": "/root/dissect-example"
  },
  "zebra": {
    "path": "dissect-example"
  },
  "giraffe1": {
    "hostname": "giraffe",
    "user": "root",
    "path": "repos/dissect-example1"
  },
  "giraffe2": {
    "hostname": "giraffe",
    "user": "root",
    "path": "repos/dissect-example2"
  }
}
```
Paths may be absolute or relative to the user's home directory.  
Not specifying `user` defaults to the current user.  
Not specifying `hostname` defaults to the host's JSON key.  
It is possible to specify the same machine multiple types with different JSON
keys and paths.

To set the configuration file, use `git dissect config`.  
Note: In order for `git-dissect` to work properly, the user must be able to
log in to the hosts via SSH using a public key.

### `git-dissect` commands:

Command | Description
--- | ---
`git dissect config <path-to-json>` | Set `<path-to-json>` as the configuration file.
`git dissect execute <cmd>` | Run `<cmd>` on all hosts. The remote repository path is used as the working directory.
`git dissect fetch` | Run `git fetch` on all hosts.
`git dissect checkout` | Choose a commit for each host and run `git checkout` on all hosts.
`git dissect collect <cmd>` | Run `<cmd>` on all hosts and use the exit code to determine if a commit is good or bad.
`git dissect step <cmd>` | Equivalent to running `git dissect checkout; git dissect collect <cmd>`.
`git dissect run <cmd>` | Equivalent to running `git dissect step <cmd>` until the bad commit is found.
`git dissect signal {wait\|good\|bad}` | See "Manual mode" below.

### Manual mode

When not supplying a command to `git dissect {execute|collect|step|run}`,
`git-dissect` will run in "manual mode".  
The actual command that's executed on the hosts is `git dissect signal wait`,
which waits for the user to invoke `git dissect signal {good|bad}` _on the host_
to indicate whether the checked out commit is good or bad. Execution of
`git-dissect` then continues normally as if the remote command succeeded or
failed as indicated by the user.  
This is equivalent to calling `git bisect {good|bad}` after running tests
manually.  
Note: Since `git dissect signal` runs _on the host_, `git-dissect` must be
installed on it in order to use manual mode.

Alternatively, if you don't want to install `git-dissect` on the hosts, you can
run `git bisect {good|bad} dissect/<host>` to manually mark the commit checked
out on `<host>` as good or bad.  
Note that this does not remove the host from the list of hosts that
`git dissect collect` runs on. To achieve that, run
`git update-ref -d refs/dissect/<host>`.

## Future

* Better handling of error conditions.
* Move configuration into `gitconfig`.
  * Implement an easy way to add/remove hosts.
  * Fill in missing configuration values from `sshconfig`.
* If `git dissect collect` is interrupted after some information was collected,
call `git bisect` with what we have instead of throwing everything away.
