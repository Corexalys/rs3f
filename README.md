# RS3F client

RS3F is the file sharing tool used at Corexalys.

It is based on `sshfs` + `gocryptfs` to share files in a zero-trust architecture.

It relies on keepassxc or pass to fetch the password for a volume. If none are available, it falls back to a simple stdin password prompt.

## How to install RS3F

### Debian based systems

- Fetch the latest `rs3f_all.deb` from the [releases page](https://github.com/Corexalys/rs3f/releases/latest)
- Install it by double clicking on it (if your DE supports it)
  OR
  Copy the deb file to /tmp/rs3f.deb and run `sudo apt-get install -y -f /tmp/rs3f.deb`

## How to use RS3F

```bash
# Mount a volume

rs3fc mount volname@server:port target
rs3fc mount volname@server target
rs3fc mount volname target
rs3fc mount volname

# Unmount a volume

rs3fc umount target
```

You can use a config file to specify the default server/port, the default mountpoint target, the "password pattern" or the keepassxc database path.

Here is an example configuration file:

```ini
# ~/.config/rs3f/config.ini
# or
# ~/.rs3f.ini

[rs3f]
mountpoint=./{volume}
fetchers=keepassxc,stdin
password_pattern=rs3f/{volume}@{server}:{port}
keepassxc_database=~/Passwords.kdbx
server=my_rs3f_server.com
port=22
```

## How to setup the server

At the moment the source code is not yet published. Once fully reviewed internally, it will be available at [github.com/Corexalys/rs3f\_server](https://github.com/Corexalys/rs3f_server).

## How it really works inside

A volume is represented on the server as a user.

- `rs3fc` first connects to the server using `sshfs` as the desired user
- it then mounts a `gocryptfs` that is available in the volume's home
