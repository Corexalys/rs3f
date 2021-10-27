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

from .passwordfetchers import fetch_password, get_default_fetchers_order


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

    subparsers = parser.add_subparsers(title="operation", required=True)

    version_subparser = subparsers.add_parser(
        "version", help="Display the version and exit"
    )
    version_subparser.set_defaults(operation="version")

    # Mount arguments
    mount_subparser = subparsers.add_parser(
        "mount", aliases=["open"], help="Mount a remote directory"
    )
    mount_subparser.set_defaults(operation="mount")
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
    mount_subparser.add_argument(
        "--password-fetchers",
        "-p",
        nargs=1,
        help=f"The password fetchers to use (default: {get_default_fetchers_order()})",
        default=None,
    )
    mount_subparser.add_argument(
        "--password-pattern",
        nargs=1,
        help="The pattern for the name of the password in the password manager for a volume without port (default: rs3f/{volume}@{server}:{port})",
        default=None,
    )
    mount_subparser.add_argument(
        "--keepassxc-database",
        nargs=1,
        help="The path for the keepassxc database (default: ~/Passwords.kdbx)",
        default=None,
    )

    # Umount arguments
    umount_subparser = subparsers.add_parser(
        "umount", aliases=["close"], help="Umount a remote directory"
    )
    umount_subparser.set_defaults(operation="umount")
    umount_subparser.add_argument("mountpoint", help="The folder to umount")

    return parser.parse_args()


def _parse_config(cli_config_path: Optional[str]) -> ConfigParser:
    config = ConfigParser()
    config["rs3f"] = {
        "mountpoint": "./{volume}",
        "fetchers": get_default_fetchers_order(),
        "password_pattern": "rs3f/{volume}@{server}:{port}",
        "keepassxc_database": "~/Passwords.kdbx",
    }

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

        if mountpoint is None:
            mountpoint = config.get("rs3f", "mountpoint", fallback=None)
        if mountpoint is None:
            raise RuntimeError("No mountpoint specified")
        mountpoint = mountpoint.format(volume=volume)

        fetchers = args.password_fetchers
        if fetchers is None:
            fetchers = config.get("rs3f", "fetchers", fallback=None)
        if fetchers is None:
            raise RuntimeError("No fetchers specified")

        password_pattern = args.password_pattern
        if password_pattern is None:
            password_pattern = config.get("rs3f", "password_pattern", fallback=None)
        if password_pattern is None:
            raise RuntimeError("No password pattern specified")
        password_key = password_pattern.format(volume=volume, server=server, port=port)

        keepassxc_database = args.keepassxc_database
        if keepassxc_database is None:
            keepassxc_database = config.get("rs3f", "keepassxc_database", fallback=None)
        if keepassxc_database is not None:
            keepassxc_database = os.path.expanduser(keepassxc_database)

        try:
            print(f"Connecting to {password_key}.")
            connect(
                volume,
                server,
                mountpoint,
                lambda: fetch_password(
                    password_key, fetchers, keepassxc_database=keepassxc_database
                ),
                allow_init=args.allow_init,
                port=port,
            )
            print(f"Mounted {password_key} to {mountpoint}")
        except Exception as exc:
            print(f"Couldn't mount {password_key}: {exc}.")
            print("Cleaning up.")
            disconnect(mountpoint)
            sys.exit(1)
        except KeyboardInterrupt:
            print("Mount interrupted.")
            print("Cleaning up.")
            disconnect(mountpoint)
            sys.exit(1)
    elif args.operation == "umount":
        if mountpoint is None:
            raise RuntimeError("No mountpoint specified")
        disconnect(mountpoint)
        print(f"Unmounted {mountpoint}")
