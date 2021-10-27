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
    friendly_name = "UNSET"

    def __init__(self, **kwargs) -> None:
        pass

    @abstractmethod
    def get_password(self, password_key: str) -> Optional[str]:
        """Fetch the password for a volume and host pair."""


_PASSWORD_FETCHERS: List[Type[ABCPasswordFetcher]] = []


def register_fetcher(class_: Type[ABCPasswordFetcher]) -> Type[ABCPasswordFetcher]:
    global _PASSWORD_FETCHERS
    _PASSWORD_FETCHERS.append(class_)
    # Sort password fetchers, with highest priority first
    _PASSWORD_FETCHERS.sort(key=lambda pf: pf.priority, reverse=True)
    return class_


def get_default_fetchers_order() -> str:
    """Return the friendly_names of the fetchers in the default order."""
    return ",".join([Fetcher.friendly_name for Fetcher in _PASSWORD_FETCHERS])


@register_fetcher
class StdinPasswordFetcher(ABCPasswordFetcher):
    """Prompt the password to the user."""

    friendly_name = "stdin"

    def get_password(self, password_key: str) -> Optional[str]:
        return getpass(f"gocryptfs password for {password_key}? ")


@register_fetcher
class PassPasswordFetcher(ABCPasswordFetcher):
    """Fetch the password using pass."""

    priority = 1
    friendly_name = "pass"

    def __init__(self, **kwargs) -> None:
        if not check_binary_available("pass"):
            raise RuntimeError("Pass is not installed")

    def get_password(self, password_key: str) -> Optional[str]:
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

    priority = 2
    friendly_name = "keepassxc"

    def __init__(self, **kwargs) -> None:
        if not check_binary_available("keepassxc-cli"):
            raise RuntimeError("Keepassxc is not installed")
        if kwargs.get("keepassxc_database", None) is None:
            raise RuntimeError("No Keepassxc password database specified")
        self.password_file_path = kwargs["keepassxc_database"]
        if not os.path.exists(self.password_file_path):
            raise RuntimeError("Couldn't find the password database")

    def get_password(self, password_key: str) -> Optional[str]:
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


def fetch_password(password_key: str, fetchers: str, **kwargs) -> str:
    """Return the password for a volume and a host."""
    fetchers_names = [
        fetcher_name.lower().strip() for fetcher_name in fetchers.split(",")
    ]
    for fetcher_name in fetchers_names:
        Fetcher = None
        for PasswordFetcher in _PASSWORD_FETCHERS:
            if PasswordFetcher.friendly_name == fetcher_name:
                Fetcher = PasswordFetcher
        if Fetcher is None:
            print(f"Unknown fetcher: {fetcher_name}")
            continue

        print(f"Using {Fetcher.friendly_name}")
        _fetcher_color()
        try:
            fetcher = Fetcher(**kwargs)
            _reset_color()
        except Exception as exc:
            _reset_color()
            print(f"Couldn't initialize {Fetcher.friendly_name}: {exc}")
            continue

        _fetcher_color()
        try:
            result = fetcher.get_password(password_key)
            _reset_color()
            if result is not None:
                return result
        except Exception as exc:
            _reset_color()
            print(f"Couldn't fetch the password using {Fetcher.friendly_name}: {exc}")
            continue
    raise RuntimeError("Couldn't determine the password for the gocryptfs")
