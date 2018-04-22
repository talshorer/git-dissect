# git-dissect: DIStributed biSECT

`git-dissect` is an alternative to `git bisect` that allows running tests on
multiple hosts in order to bisect faster.  
It was inspired by Rob Hoelz's [git-pisect](https://github.com/hoelzro/git-pisect).

## Installation
    $ git clone https://github.com/talshorer/git-dissect.git
    $ cd git-dissect
    $ # Install for the current user only
    $ ./setup.py install --user
    $ # Install for everyone using the system
    $ sudo ./setup.py install

## Usage
Start as you would start a normal bisect:

    $ git bisect start --no-checkout
    $ git bisect bad $BAD_COMMIT
    $ git bisect good $GOOD_COMMIT
Note: It is recommended to start `git bisect` with the `--no-checkout` option
when using `git-dissect`.

### Configuration
`git-dissect` uses git's configuration to describe its hosts.
Each host is described by a subsection called `dissect.<host>`, containing the
following values:

Value | Description | Mandatory | Default
--- | --- | --- | ---
`enabled` | Whether to include this host when performnig operations | no | true
`path` | Path to the repository on the host. Can be absolute or relative to the user's home directory | yes | -
`user` | User to log in with | no | Current user
`hostname` | Alternative hostname/address to connect to (similar to `sshconfig`) | no | Subsection's name
`port` | SSH port used to connect to the host | no | 22
`stricthostkeychecking` | Use SSH known_hosts mechanism. **Disabling this can pose a security risk** | no | true

`git-dissect` will use all hosts with a `path` value.  
It is possible to specify the same machine multiple types with different
subsection names and paths.  
It is recommended to set `hostname` and `user` globally (see example) for easier
management of multiple repositories using the same hosts.  
Note: In order for `git-dissect` to work properly, the user must be able to
log in to the hosts via SSH using a public key.

#### Examples
##### Adding a new host
    $ git config --global dissect.bravo.user tal
    $ git config --global dissect.bravo.hostname 20.0.1.2
    $ git config dissect.bravo.path /home/tal/dissect-example
##### Removing a host
    $ git config --unset dissect.bravo.path
*Note: you might want to disable a host instead of removing it*
#### Disabling a host
    $ git config --bool dissect.bravo.enabled false
#### Enabling a host
    $ git config --bool dissect.bravo.enabled true
##### Complete configuration
```
[disect "20.0.0.2"]
	path = /tmp/dissect-example
	user = root
	port = 7400
	stricthostkeychecking = false
[disect "alpha"]
	path = dissect-example
	stricthostkeychecking = true
[disect "bravo"]
	enabled = true
	path = /home/tal/dissect-example
	user = tal
	hostname = 20.0.1.2
	port = 7401
[disect "charlie1"]
	enabled = false
	path = repos/dissect-example1
	user = tals
	hostname = charlie
[disect "charlie2"]
	path = repos/dissect-example2
	user = tals
	hostname = charlie
```
### `git-dissect` commands:

Command | Description
--- | ---
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
* Add subcommands for easier host management.
* Fill in missing configuration values from `sshconfig`.
* If `git dissect collect` is interrupted after some information was collected,
call `git bisect` with what we have instead of throwing everything away.
* Upload to PyPI and update installation accordingly.
