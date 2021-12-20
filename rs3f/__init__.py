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

import hashlib
import logging
import os
import socket
import subprocess
from typing import Callable, Optional, Union

__version__ = "1.0.5"

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


def get_raw_mount_path(mountpoint: str) -> os.PathLike:
    """Return the raw mount path for a given user/server pair."""
    runtime_dir = os.getenv("XDG_RUNTIME_DIR", None)
    if runtime_dir is None:
        raise EnvironmentNotSetError(
            "$XDG_RUNTIME_DIR is not set, cannot determine raw mount path"
        )
    key = os.path.abspath(mountpoint)
    key_hash = hashlib.sha256(key.encode()).hexdigest()[:8]
    raw_mount_path = os.path.join(runtime_dir, f"rs3f_{key_hash}")
    logger.debug(
        "Using raw mount path %r for mountpoint %r.", raw_mount_path, mountpoint
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


def connect(
    target_user: str,
    server: str,
    mountpoint: str,
    password: Union[str, Callable[[], str]],
    *,
    port: Optional[int],
    allow_init: bool = False,
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
    # TODO simple tcp connection (but we need to read the SSH config file…)

    # Raw mount
    logger.debug("Mounting raw volume to %r.", raw_mount_path)
    os.makedirs(raw_mount_path, 0o700)
    options = [
        "reconnect",
        "ServerAliveInterval=15",
        "ServerAliveCountMax=3",
        "idmap=user",
    ]
    if port is not None:
        options.append(f"port={port}")
    sshfs = subprocess.run(
        [
            "sshfs",
            "-o",
            ",".join(options),
            f"{target_user}@{server}:/",
            raw_mount_path,
        ],
        capture_output=True,
        check=False,
    )
    if sshfs.returncode != 0:
        logger.debug("SSHFS exit code %d:", sshfs.returncode)
        logger.debug("%s", sshfs.stderr)
        # TODO switch to InvalidSSHCredentials when server check is implemented
        raise RS3FRuntimeError("Couldn't connect to the server")
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
    gocryptfs = subprocess.run(
        [
            "gocryptfs",
            os.path.join(raw_mount_path, "gocryptfs_root"),
            mountpoint,
        ],
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


def disconnect(mountpoint: str) -> None:
    """Unmount a folder from a remote rs3f share."""
    logger.info("Unmounting %r.", mountpoint)
    # Initial checks
    logger.debug("Checking for missing binaries.")
    if not check_binary_available("fusermount"):
        raise BinaryMissingError("FUSE is not installed")

    # Unmount gocryptfs volume
    logger.debug("Unmounting gocryptfs volume at %r.", mountpoint)
    if not os.path.exists(mountpoint):
        logger.warning("Mount folder %r is missing.", mountpoint)
    else:
        if not os.path.ismount(mountpoint):
            logger.warning("Mount folder %r already unmounted", mountpoint)
        else:
            fusermount = subprocess.run(
                ["fusermount", "-u", mountpoint],
                capture_output=True,
                check=False,
            )
            if fusermount.returncode != 0:
                logger.debug("fusermount exit code %d:", fusermount.returncode)
                logger.debug("%s", fusermount.stderr)
                raise RS3FRuntimeError("Couldn't unmount the gocryptfs.")

        os.rmdir(mountpoint)

    # Unmount raw volume
    raw_mount_path = get_raw_mount_path(mountpoint)
    logger.debug("Unmounting raw volume at %r.", raw_mount_path)
    if not os.path.exists(raw_mount_path):
        logger.warning("Raw mount folder %r is missing.", raw_mount_path)
    else:
        if not os.path.ismount(raw_mount_path):
            logger.warning("Raw mount folder %r is already unmounted.", raw_mount_path)
        else:
            fusermount = subprocess.run(
                ["fusermount", "-u", raw_mount_path],
                capture_output=True,
                check=False,
            )
            if fusermount.returncode != 0:
                logger.debug("fusermount exit code %d:", fusermount.returncode)
                logger.debug("%s", fusermount.stderr)
                raise RS3FRuntimeError("Couldn't unmount the raw mount.")
        os.rmdir(raw_mount_path)
    logger.info("RS3F volume unmounted.")
