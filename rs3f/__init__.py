# Copyright (C) 2021 Corexalys.
#
# This file is part of rs3f.
#
# rs3f is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# rs3f is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with rs3f.  If not, see <https://www.gnu.org/licenses/>.

import getpass
import hashlib
import logging
import os
import shlex
import socket
import subprocess
from typing import Callable, List, Optional, Union

__version__ = "1.1.0"

UIDFILE = """\
{local_username}:{remote_uid}
root:0
"""

# 999 is hardcoded to sftp_users in the rs3f server
GIDFILE = """\
users:999
root:0
"""

logger = logging.getLogger("rs3f")
logger.setLevel(logging.DEBUG)


class RS3FRuntimeError(RuntimeError):
    """Base runtime error class for all rs3f errors."""


class NetworkingError(RS3FRuntimeError):
    """Raised when a network error occurred."""

    def __str__(self) -> str:
        return "A network error occurred: " + super().__str__()


class InvalidSSHCredentials(RS3FRuntimeError):
    """Raised if we sent invalid credentials to the SSH server."""

    def __str__(self) -> str:
        return "Invalid credentials for the SSH server: " + super().__str__()


class InvalidPassword(RS3FRuntimeError):
    """Raised if the password for the gocryptfs is invalid."""

    def __str__(self) -> str:
        return "Invalid credentials for the gocryptfs volume: " + super().__str__()


class EnvironmentNotSetError(RS3FRuntimeError):
    """Raised when an environment variable was expected but not set."""

    def __str__(self) -> str:
        return "An environment variable isn't correctly set: " + super().__str__()


class BinaryMissingError(RS3FRuntimeError):
    """Raised when a required program is missing from the system."""

    def __str__(self) -> str:
        return "A program is missing: " + super().__str__()


def get_mount_key(mountpoint: str) -> str:
    """Return the mount key for a given mountpoint."""
    key = os.path.abspath(mountpoint)
    return hashlib.sha256(key.encode()).hexdigest()[:8]


def get_runtime_dir() -> os.PathLike:
    """Return the temporary runtime directory for this user."""
    runtime_dir = os.getenv("XDG_RUNTIME_DIR", None)
    if runtime_dir is None:
        raise EnvironmentNotSetError(
            "$XDG_RUNTIME_DIR is not set, cannot determine runtime path"
        )
    return runtime_dir


def get_raw_mount_path(mountpoint: str) -> os.PathLike:
    """Return the raw mount path for a given mountpoint."""
    mount_key = get_mount_key(mountpoint)
    raw_mount_path = os.path.join(get_runtime_dir(), f"rs3f_{mount_key}")
    logger.debug(
        "Using raw mount path %r for mountpoint %r.",
        raw_mount_path,
        os.path.abspath(mountpoint),
    )
    return raw_mount_path  # type: ignore


def check_binary_available(name: str) -> bool:
    """Return if a binary is available in $PATH."""
    paths = os.getenv("PATH", None)
    if paths is None:
        raise EnvironmentNotSetError("$PATH is not set")
    for path in paths.split(":"):
        if os.path.exists(os.path.join(path, name)):
            return True
    return False


def _check_ssh_server_is_up(target_user: str, server: str, port: Optional[int]) -> None:
    """Check if an SSH server is reachable, raise NetworkingError otherwise."""
    logger.info("Checking if %s@%s:%s is reachable.", target_user, server, port)
    options = {
        # Disable keyboard interactions
        "BatchMode": "yes",  # TODO maybe not in case the host key changes?
        # Disable all authentication methods
        "HostBasedAuthentication": "no",
        "PasswordAuthentication": "no",
        "PubkeyAuthentication": "no",
        # Define a timeout
        "ConnectTimeout": 60,
    }
    command = ["ssh"]
    for key, value in options.items():
        command.extend(["-o", f"{key}={value}"])
    command.append(f"{target_user}@{server}")
    if port is not None:
        command.extend(["-p", str(port)])

    ssh = subprocess.run(command, capture_output=True, check=False)

    if b"Permission denied" not in ssh.stderr:
        # If permission isn't denied, the connection probably failed
        logger.debug("Command line: %s", command)
        logger.debug("ssh exit code %d:", ssh.returncode)
        logger.debug("%s", ssh.stderr)
        raise NetworkingError("Could not reach SSH server")


def _get_remote_uid(target_user: str, server: str, port: Optional[int]) -> int:
    """Return the UID of a volume's user (using the owner of gocryptfs_root)."""
    logger.debug("Fetching the remote uid.")
    args = (
        [
            "sftp",
            "-q",
            "-b",
            "-",
        ]
        + (
            [
                "-P",
                port,
            ]
            if port is not None
            else []
        )
        + [
            f"{target_user}@{server}",
        ]
    )
    logger.debug("CALLING PROCESS: %s", " ".join(args))
    sftp = subprocess.run(
        args,
        capture_output=True,
        check=False,
        input=b"ls -ln",
    )
    if sftp.returncode != 0:
        # Probably a credentials error since we checked for reachability before
        logger.debug("SFTP exit code %d:", sftp.returncode)
        logger.debug("%s", sftp.stderr)
        raise InvalidSSHCredentials("Invalid SSH username or password.")

    remote_uid: Optional[int] = None
    for line in sftp.stdout.split(b"\n")[1:]:
        # Parsing the output of ls isn't great, but I haven't found a better way
        parts = line.split()
        name = parts[-1]
        if name == b"gocryptfs_root":
            remote_uid = int(parts[2])
            break

    if remote_uid is None:
        raise RS3FRuntimeError(
            "Could not find gocryptfs_root directory, is the volume a valid rs3f volume?"
        )
    logger.debug("Remote UID is %d.", remote_uid)
    return remote_uid


def connect(
    target_user: str,
    server: str,
    mountpoint: str,
    password: Union[str, Callable[[], str]],
    *,
    port: Optional[int] = None,
    allow_init: bool = False,
    sshfs_extra_args: Optional[List[str]] = None,
    gocryptfs_extra_args: Optional[List[str]] = None,
) -> None:
    """Connect to a remote rs3f share and mount it."""
    logger.info("Connecting to %s@%s:%s.", target_user, server, port)

    # Check for missing binaries
    logger.debug("Checking for missing binaries.")
    if not check_binary_available("sshfs"):
        raise BinaryMissingError("SSHFS is not installed")
    if not check_binary_available("gocryptfs"):
        raise BinaryMissingError("Gocryptfs is not installed")

    # Cleanup eventual invalid state
    logger.debug("Checking for eventual invalid state.")
    needs_cleanup = False
    if os.path.exists(mountpoint):
        needs_cleanup = True
        logger.warning("Actual mount path already exists.")

    raw_mount_path = get_raw_mount_path(mountpoint)
    if os.path.exists(raw_mount_path):
        needs_cleanup = True
        logger.warning("Raw mount path already exists.")

    if needs_cleanup:
        disconnect(mountpoint)

    # Check SSH server is reachable
    _check_ssh_server_is_up(target_user, server, port)

    # Fetch target user ID
    remote_uid = _get_remote_uid(target_user, server, port)

    # Write sshfs uidfile and gidfile
    uidfile_path = os.path.join(
        get_runtime_dir(), "uidfile_" + get_mount_key(mountpoint)
    )
    gidfile_path = os.path.join(
        get_runtime_dir(), "gidfile_" + get_mount_key(mountpoint)
    )
    logger.debug(
        "Writing uidfile and gidfile to %r and %r respectively.",
        uidfile_path,
        gidfile_path,
    )

    with open(uidfile_path, "w") as uidfile:
        local_username = getpass.getuser()
        uidfile.write(
            UIDFILE.format(local_username=local_username, remote_uid=remote_uid)
        )
    with open(gidfile_path, "w") as gidfile:
        gidfile.write(GIDFILE)
    os.chmod(uidfile_path, 0o600)
    os.chmod(gidfile_path, 0o600)

    # Raw mount
    logger.debug("Mounting raw volume to %r.", raw_mount_path)
    os.makedirs(raw_mount_path, 0o700)
    options = [
        "reconnect",
        "ServerAliveInterval=10",
        "ServerAliveCountMax=1",
        "IPQoS=lowdelay",
        "idmap=file",
        f"uidfile={uidfile_path}",
        f"gidfile={gidfile_path}",
        "nomap=ignore",
    ]
    if port is not None:
        options.append(f"port={port}")
    args = [
        "sshfs",
        "-o",
        ",".join(options),
    ]
    if sshfs_extra_args is not None:
        logger.debug("Including sshfs additional args %s", shlex.join(sshfs_extra_args))
        args.extend(sshfs_extra_args)
    args.extend(
        [
            f"{target_user}@{server}:/",
            raw_mount_path,
        ]
    )
    logger.debug("CALLING PROCESS: %s", shlex.join(args))
    sshfs = subprocess.run(
        args,
        capture_output=True,
        check=False,
    )
    if sshfs.returncode != 0:
        # The server is up and the crendentials are valid, unknown cause.
        logger.debug("SSHFS exit code %d:", sshfs.returncode)
        logger.debug("%s", sshfs.stderr)
        raise RS3FRuntimeError(
            "Could not mount raw volume (but server is up and credentials are "
            "valid). Maybe the network is unstable?"
        )
    logger.debug("Mounted raw volume")

    logger.debug("Checking for a gocryptfs volume")
    cryptfs_dir = os.path.join(raw_mount_path, "gocryptfs_root")
    if not os.path.exists(os.path.join(cryptfs_dir, "gocryptfs.conf")):
        logger.warning("Gocryptfs is not initialized")
        if allow_init:
            print("Please choose a password for this volume:")
            crypt_init = subprocess.run(
                ["gocryptfs", "-init", cryptfs_dir], check=False
            )
            if crypt_init.returncode != 0:
                logger.debug("gocryptfs -init exit code %d:", crypt_init.returncode)
                logger.debug("%s", crypt_init.stderr)
                raise RS3FRuntimeError("Could not initialize volume")
        else:
            raise RS3FRuntimeError("Volume is not initialized")

    logger.debug("Fetching a password for the volume")
    password_str = password if isinstance(password, str) else password()

    # Actual mount
    logger.debug("Mounting the gocryptfs volume")
    os.makedirs(mountpoint, 0o700)
    gocryptfs_args = [
        os.path.join(raw_mount_path, "gocryptfs_root"),
        mountpoint,
    ]
    if gocryptfs_extra_args is not None:
        logger.debug(
            "Including gocryptfs additional args %s", shlex.join(gocryptfs_extra_args)
        )
        gocryptfs_args = gocryptfs_extra_args + gocryptfs_args
    gocryptfs_args.insert(0, "gocryptfs")
    logger.debug("CALLING PROCESS: %s", shlex.join(gocryptfs_args))
    gocryptfs = subprocess.run(
        gocryptfs_args,
        capture_output=True,
        input=password_str.encode(),
        check=False,
    )
    if gocryptfs.returncode != 0:
        logger.debug("GoCryptFS exit code %d:", gocryptfs.returncode)
        logger.debug("%s", gocryptfs.stderr)
        # See gocryptfs manpage for exit codes
        if gocryptfs.returncode in (12, 22):
            raise InvalidPassword("Invalid or empty gocryptfs password")
        raise RS3FRuntimeError("Couldn't mount gocryptfs")
    logger.info("RS3F volume mounted.")


def _umount_fuse_fs(mountpoint: Union[str, os.PathLike], display_name: str) -> None:
    """Unmount a single fuser fs."""
    abspath = os.path.abspath(mountpoint)
    parent, name = os.path.split(abspath)
    logger.debug("Unmounting %s volume at %r.", display_name, abspath)
    # We aren't using os.path.exists since it skips files that can't be stated.
    # This happens if gocryptfs/sshfs exists improperly
    mountpoint_exists = name in os.listdir(parent)
    if mountpoint_exists:
        # "not exists" -> cannot be stated, not properly unmounted
        if not os.path.exists(abspath) or os.path.ismount(abspath):
            fusermount = subprocess.run(
                ["fusermount", "-u", abspath],
                capture_output=True,
                check=False,
            )
            if fusermount.returncode != 0:
                logger.debug("fusermount exit code %d:", fusermount.returncode)
                logger.debug("%s", fusermount.stderr)
                raise RS3FRuntimeError(f"Couldn't unmount the {display_name} volume")
        else:
            logger.warning("Volume %s already unmounted", display_name)
        os.rmdir(abspath)
    else:
        logger.warning("Mount folder %r is missing.", mountpoint)


def disconnect(mountpoint: str) -> None:
    """Unmount a folder from a remote rs3f share."""
    logger.info("Unmounting %r.", mountpoint)
    # Initial checks
    logger.debug("Checking for missing binaries.")
    if not check_binary_available("fusermount"):
        raise BinaryMissingError("FUSE is not installed")

    # Unmount raw volume
    _umount_fuse_fs(mountpoint, "gocryptfs")

    # Unmount sshfs volume
    raw_mount_path = get_raw_mount_path(mountpoint)
    _umount_fuse_fs(raw_mount_path, "raw")
