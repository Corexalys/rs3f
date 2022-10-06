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

from setuptools import setup

setup(
    name="rs3f",
    version="1.1.0",
    packages=["rs3f", "rs3fc"],
    entry_points={"console_scripts": ["rs3fc = rs3fc:main", "rs3f = rs3fc:main"]},
    python_requires=">=3.8.0",
)
