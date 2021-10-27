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

from argparse import ArgumentParser, Namespace
from configparser import ConfigParser
import os
import re
import sys
from typing import Optional

from rs3f import __version__, connect, disconnect

from .passwordfetchers import fetch_password

# TODO needs to be more restrictive on the server extraction, but this isn't
# meant to be foolproof
RE_VOLUME = re.compile(
    r"^(?P<volume>[a-z_][a-zA-Z0-9_-]{0,31})(@(?P<server>[^:@/]+?)(:(?P<port>\d{1,5}))?)?$"
)


def _parse_args() -> Namespace:
    """Parse the command line arguments."""

    parser = ArgumentParser()
    parser.add_argument(
        "--config-path",
        "-c",
        nargs=1,
        help="The path for the config path (default: ~/.config/rs3f/config.ini or ~/.rs3f.ini)",
        default=None,
    )

    subparsers = parser.add_subparsers(
        title="operation", required=True, dest="operation"
    )

    version_subparser = subparsers.add_parser(
        "version", help="Display the version and exit"
    )

    # Mount arguments
    mount_subparser = subparsers.add_parser(
        "mount", aliases=["open"], help="Mount a remote directory"
    )
    mount_subparser.add_argument(
        "volume", help="The volume to mount: volume[@server[:port]]"
    )
    mount_subparser.add_argument(
        "mountpoint",
        nargs="?",
        help="The full mount path (default: ./{volume})",
        default=None,
    )
    mount_subparser.add_argument(
        "--allow-init",
        "-i",
        help="Create the gocryptfs if necessary",
        action="store_true",
    )

    # Umount arguments
    umount_subparser = subparsers.add_parser(
        "umount", aliases=["close"], help="Umount a remote directory"
    )
    umount_subparser.add_argument("mountpoint", help="The folder to umount")

    return parser.parse_args()


def _parse_config(cli_config_path: Optional[str]) -> ConfigParser:
    config = ConfigParser()
    config["rs3f"] = {"mountpoint": "./{volume}"}

    if cli_config_path is not None:
        read_paths = config.read(cli_config_path)
        if not read_paths:
            raise RuntimeError("Could not read specified config file")
    else:
        config_paths = ["~/.config/rs3f/config.ini", "~/.rs3f.ini"]
        config.read([os.path.expanduser(path) for path in config_paths])

    return config


def main():
    args = _parse_args()
    config = _parse_config(args.config_path)

    if args.operation == "version":
        print(f"{sys.argv[0]} version {__version__}.")
        return

    mountpoint = args.mountpoint

    if args.operation == "mount":
        match = RE_VOLUME.match(args.volume)
        if match is None:
            raise RuntimeError("Invalid volume syntax")

        volume = match["volume"]
        server = match["server"]
        port = int(match["port"]) if match["port"] is not None else None
        if server is None:
            server = config.get("rs3f", "server", fallback=None)
            port = config.get("rs3f", "port", fallback=None)
        if server is None:
            raise RuntimeError("No server specified")

        full_target_string = (
            f"{volume}@{server}:{port}" if port is not None else f"{volume}@{server}"
        )

        if mountpoint is None:
            mountpoint = config.get("rs3f", "mountpoint", fallback=None)
        if mountpoint is None:
            raise RuntimeError("No mountpoint specified")
        mountpoint = mountpoint.format(volume=volume)

        try:
            print(f"Connecting to {full_target_string}.")
            connect(
                volume,
                server,
                mountpoint,
                lambda: fetch_password(volume, server, port),
                allow_init=args.allow_init,
                port=port,
            )
            print(f"Mounted {full_target_string} to {mountpoint}")
        except Exception as exc:
            print(f"Couldn't mount {full_target_string}: {exc}.")
            print("Cleaning up.")
            disconnect(mountpoint)
            sys.exit(1)
    elif args.operation == "umount":
        if mountpoint is None:
            raise RuntimeError("No mountpoint specified")
        disconnect(mountpoint)


if __name__ == "__main__":
    main()
