# git-dissect: DIStributed biSECT

`git-dissect` is an alternative to `git bisect` that allows running tests on
multiple hosts in order to bisect faster.  
This is achieved by utilizing python's `fabric` library.  
It was inspired by Rob Hoelz's [git-pisect](https://github.com/hoelzro/git-pisect).

## Installation
    $ sudo pip3 install fabric3 gitpython
    $ wget https://raw.githubusercontent.com/talshorer/git-dissect/master/git-dissect.py
    $ chmod +x git-dissect.py
    $ # Install for the current user only
    $ git config --global alias.dissect '!'$(realpath git-dissect.py)
    $ # Install for everyone using the system
    $ sudo git config --system alias.dissect '!'$(realpath git-dissect.py)

## Usage
Start as you would start a normal bisect:

    $ git bisect start --no-checkout
    $ git bisect bad $BAD_COMMIT
    $ git bisect good $GOOD_COMMIT
Note: It is recommended to start `git bisect` with the `--no-checkout` option
when using `git-dissect`.

### Configuration
`git-dissect` uses a JSON configuration to manage its hosts.  
The configuration is a JSON object, where each key is of the form
`"user@hostname"` and each value is of the form `"/path/to/repository/on/host"`.  
For example:
```
{
  "root@20.0.0.2": "/tmp/dissect-example",
  "root@20.0.1.2": "/tmp/dissect-example",
  "root@20.0.2.2": "/tmp/dissect-example",
  "root@20.0.3.2": "/tmp/dissect-example",
  "root@20.0.4.2": "/tmp/dissect-example",
  "root@20.0.5.2": "/tmp/dissect-example",
  "root@20.0.6.2": "/tmp/dissect-example",
  "root@20.0.7.2": "/tmp/dissect-example"
}
```
To set the configuration file, use `git dissect config`.  
Note: In order for `fabric` to work properly, the user must be able to log in
to the hosts via SSH using a public key.

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

## Future

* Better handling of error conditions.
* Manage the hosts configuration in `git-dissect` itself. Implement an easy way to add/remove hosts.
* Add a proper python `setup.py` script to manage installation.
* Allow running on the same host in multiple paths/worktrees.
* If `git dissect collect` is interrupted after some information was collected, call `git bisect` with what we have instead of throwing everything away.
