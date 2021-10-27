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

from abc import ABC, abstractmethod
from getpass import getpass
import os
import subprocess
from typing import List, Optional, Type

from rs3f import check_binary_available


class ABCPasswordFetcher(ABC):
    priority = -1

    @abstractmethod
    def get_password(self, name: str, host: str, port: Optional[int]) -> Optional[str]:
        """Fetch the password for a volume and host pair."""


_PASSWORD_FETCHERS: List[Type[ABCPasswordFetcher]] = []


def register_fetcher(class_: Type[ABCPasswordFetcher]) -> Type[ABCPasswordFetcher]:
    global _PASSWORD_FETCHERS
    _PASSWORD_FETCHERS.append(class_)
    # Sort password fetchers, with highest priority first
    _PASSWORD_FETCHERS.sort(key=lambda pf: pf.priority, reverse=True)
    return class_


@register_fetcher
class StdinPasswordFetcher(ABCPasswordFetcher):
    """Prompt the password to the user."""

    def get_password(self, name: str, host: str, port: Optional[int]) -> Optional[str]:
        if port is not None:
            return getpass(f"gocryptfs password for {name}@{host}:{port}? ")
        return getpass(f"gocryptfs password for {name}@{host}? ")


@register_fetcher
class PassPasswordFetcher(ABCPasswordFetcher):
    """Fetch the password using pass."""

    priority = 1

    def __init__(self) -> None:
        if not check_binary_available("pass"):
            raise RuntimeError("Pass is not installed")

    def get_password(self, name: str, host: str, port: Optional[int]) -> Optional[str]:
        if port is None:
            password_key = os.getenv(
                "RS3F_PASS_PASSWORD_NAME", "rs3f/{name}@{host}"
            ).format(name=name, host=host)
        else:
            password_key = os.getenv(
                "RS3F_PASS_PASSWORD_NAME_PORT", "rs3f/{name}@{host}:{port}"
            ).format(name=name, host=host, port=port)

        pass_result = subprocess.run(
            [
                "pass",
                password_key,
            ],
            stdout=subprocess.PIPE,
        )
        if pass_result.returncode != 0:
            print("Couldn't fetch password using pass")
            return None
        return pass_result.stdout.decode()


@register_fetcher
class KeepassxcPasswordFetcher(ABCPasswordFetcher):
    """Fetch the password using keepassxc-cli."""

    priority = 1

    def __init__(self) -> None:
        if not check_binary_available("keepassxc-cli"):
            raise RuntimeError("Keepassxc is not installed")
        self.password_file_path = os.getenv(
            "RS3F_KEEPASS_DB", os.path.expanduser("~/Passwords.kdbx")
        )
        if not os.path.exists(self.password_file_path):
            raise RuntimeError("Couldn't find the password database")

    def get_password(self, name: str, host: str, port: Optional[int]) -> Optional[str]:
        if port is None:
            password_key = os.getenv(
                "RS3F_KEEPASS_PASSWORD_NAME", "rs3f/{name}@{host}"
            ).format(name=name, host=host)
        else:
            password_key = os.getenv(
                "RS3F_KEEPASS_PASSWORD_NAME_PORT", "rs3f/{name}@{host}:{port}"
            ).format(name=name, host=host, port=port)
        keepassxc = subprocess.run(
            [
                "keepassxc-cli",
                "show",
                "--attributes",
                "password",
                self.password_file_path,
                password_key,
            ],
            stdout=subprocess.PIPE,
        )
        if keepassxc.returncode != 0:
            print("Couldn't fetch password using keepassxc-cli")
            return None
        return keepassxc.stdout.decode()


def _reset_color():
    print("\x1b[0m", end="", flush=True)


def _fetcher_color():
    print("\x1b[35m", end="", flush=True)


def fetch_password(name: str, host: str, port: Optional[int]) -> str:
    """Return the password for a volume and a host."""
    for PasswordFetcher in _PASSWORD_FETCHERS:
        print(f"Using {PasswordFetcher.__name__}")
        _fetcher_color()
        try:
            fetcher = PasswordFetcher()
            _reset_color()
        except Exception as exc:
            _reset_color()
            print(f"Couldn't initialize {PasswordFetcher.__name__}: {exc}")
            continue

        _fetcher_color()
        try:
            result = fetcher.get_password(name, host, port)
            _reset_color()
            if result is not None:
                return result
        except Exception as exc:
            _reset_color()
            print(
                f"Couldn't fetch the password using {PasswordFetcher.__name__}: {exc}"
            )
            continue
    raise RuntimeError("Couldn't determine the password for the gocryptfs")
