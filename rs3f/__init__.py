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
import os
import subprocess
from typing import Callable, Optional, Union
import warnings

__version__ = "1.0.5"


class RS3FRuntimeWarning(RuntimeWarning):
    """Base runtime warning class for all rs3f warnings."""


class RS3FRuntimeError(RuntimeError):
    """Base runtime error class for all rs3f errors."""


class EnvironmentNotSetError(RS3FRuntimeError):
    """Raised when an environment variable was expected but not set."""


class BinaryMissingError(RS3FRuntimeError):
    """Raised when a required program is missing from the system."""


def get_raw_mount_path(mountpoint: str) -> os.PathLike:
    """Return the raw mount path for a given user/server pair."""
    runtime_dir = os.getenv("XDG_RUNTIME_DIR", None)
    if runtime_dir is None:
        raise EnvironmentNotSetError(
            "$XDG_RUNTIME_DIR is not set, cannot determine raw mount path"
        )
    key = os.path.abspath(mountpoint)
    key_hash = hashlib.sha256(key.encode()).hexdigest()
    return os.path.join(runtime_dir, f"rs3f_{key_hash}")  # type: ignore


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
    # Initial checks
    if not check_binary_available("sshfs"):
        raise BinaryMissingError("SSHFS is not installed")
    if not check_binary_available("gocryptfs"):
        raise BinaryMissingError("Gocryptfs is not installed")

    if os.path.exists(mountpoint):
        raise RS3FRuntimeError("Actual mount path already exists")

    raw_mount_path = get_raw_mount_path(mountpoint)
    if os.path.exists(raw_mount_path):
        raise RS3FRuntimeError("Raw mount path already exists")

    # Raw mount
    os.makedirs(raw_mount_path, 0o700)
    options = ["reconnect", "ServerAliveInterval=15", "ServerAliveCountMax=3"]
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
    )
    if sshfs.returncode != 0:
        print(sshfs.stderr)
        raise RS3FRuntimeError("Couldn't connect to the server")
    print("Mounted raw disk")

    cryptfs_dir = os.path.join(raw_mount_path, "gocryptfs_root")
    if not os.path.exists(os.path.join(cryptfs_dir, "gocryptfs.conf")):
        print("Gocryptfs is not initialized")
        if allow_init:
            print("Please choose a password for this volume:")
            crypt_init = subprocess.run(["gocryptfs", "-init", cryptfs_dir])
            if crypt_init.returncode != 0:
                raise RS3FRuntimeError("Could not initialize volume")
        else:
            raise RS3FRuntimeError("Volume is not initialized")

    password_str = password if isinstance(password, str) else password()

    # Actual mount
    os.makedirs(mountpoint, 0o700)
    gocryptfs = subprocess.run(
        [
            "gocryptfs",
            os.path.join(raw_mount_path, "gocryptfs_root"),
            mountpoint,
        ],
        capture_output=True,
        input=password_str.encode(),
    )
    if gocryptfs.returncode != 0:
        print(gocryptfs.stderr)
        raise RS3FRuntimeError("Couldn't mount gocryptfs")
    print("RS3F volume mounted.")


def disconnect(mountpoint: str) -> None:
    """Unmount a folder from a remote rs3f share."""
    # Initial checks
    if not check_binary_available("fusermount"):
        raise BinaryMissingError("FUSE is not installed")

    if not os.path.exists(mountpoint):
        warnings.warn("Mount folder is missing", RS3FRuntimeWarning)
    else:
        if not os.path.ismount(mountpoint):
            warnings.warn("Mount folder already unmounted", RS3FRuntimeWarning)
        else:
            fusermount = subprocess.run(
                ["fusermount", "-u", mountpoint], capture_output=True
            )
            if fusermount.returncode != 0:
                print(fusermount.stderr)
                raise RS3FRuntimeError("Couldn't unmount the gocryptfs.")

        os.rmdir(mountpoint)

    raw_mount_path = get_raw_mount_path(mountpoint)
    if not os.path.exists(raw_mount_path):
        warnings.warn("Raw mount folder is missing", RS3FRuntimeWarning)
    else:
        if not os.path.ismount(raw_mount_path):
            warnings.warn("Raw mount folder is already unmounted", RS3FRuntimeWarning)
        else:
            fusermount = subprocess.run(
                ["fusermount", "-u", raw_mount_path], capture_output=True
            )
            if fusermount.returncode != 0:
                print(fusermount.stderr)
                raise RS3FRuntimeError("Couldn't unmount the raw mount.")
        os.rmdir(raw_mount_path)
    print("RS3F volume unmounted.")
