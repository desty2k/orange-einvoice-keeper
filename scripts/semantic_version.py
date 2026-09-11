#!/usr/bin/env python3
"""Calculate the next semantic version from conventional commits.

Release signals: BREAKING CHANGE/type! -> major, feat -> minor, fix/perf -> patch.
Without a release signal the script emits publish=false.
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

VERSION_PATTERN = re.compile(r"^v?(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$")
BREAKING_HEADER = re.compile(r"^[a-z]+(?:\([^)]+\))?!:", re.MULTILINE)
FEATURE_HEADER = re.compile(r"^feat(?:\([^)]+\))?:", re.MULTILINE)
PATCH_HEADER = re.compile(r"^(?:fix|perf)(?:\([^)]+\))?:", re.MULTILINE)


@dataclass(frozen=True)
class Version:
    major: int
    minor: int
    patch: int

    @classmethod
    def parse(cls, value: str) -> Version:
        match = VERSION_PATTERN.fullmatch(value)
        if match is None:
            raise ValueError(f"invalid semantic version: {value}")
        return cls(*(int(part) for part in match.groups()))

    def bump(self, level: str) -> Version:
        if level == "major":
            return Version(self.major + 1, 0, 0)
        if level == "minor":
            return Version(self.major, self.minor + 1, 0)
        if level == "patch":
            return Version(self.major, self.minor, self.patch + 1)
        raise ValueError(f"unknown release level: {level}")

    def __str__(self) -> str:
        return f"{self.major}.{self.minor}.{self.patch}"


def git(*args: str) -> str:
    return subprocess.check_output(["git", *args], text=True).strip()


def latest_tag() -> str | None:
    tags = git("tag", "--list", "v[0-9]*", "--sort=-version:refname").splitlines()
    return next((tag for tag in tags if VERSION_PATTERN.fullmatch(tag)), None)


def commits_since(tag: str | None) -> str:
    revision = f"{tag}..HEAD" if tag else "HEAD"
    return git("log", "--format=%B%x1e", revision)


def release_level(commits: str) -> str | None:
    if "BREAKING CHANGE:" in commits or BREAKING_HEADER.search(commits):
        return "major"
    if FEATURE_HEADER.search(commits):
        return "minor"
    if PATCH_HEADER.search(commits):
        return "patch"
    return None


def write_output(values: dict[str, str]) -> None:
    destination = os.environ.get("GITHUB_OUTPUT")
    lines = [f"{key}={value}" for key, value in values.items()]
    if destination:
        with Path(destination).open("a", encoding="utf-8") as output:
            output.write("\n".join(lines) + "\n")
    else:
        print("\n".join(lines))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--current-version", help="Override the latest Git tag for local checks")
    parser.add_argument("--commits-file", type=Path, help="Use commit text from a file for local checks")
    args = parser.parse_args()

    tag = None if args.current_version else latest_tag()
    current = Version.parse(args.current_version or tag or "0.0.0")
    commits = args.commits_file.read_text(encoding="utf-8") if args.commits_file else commits_since(tag)
    level = release_level(commits)
    if level is None:
        write_output({"publish": "false", "version": str(current)})
        return 0

    next_version = current.bump(level)
    write_output(
        {
            "publish": "true",
            "version": str(next_version),
            "tag": f"v{next_version}",
            "minor_tag": f"{next_version.major}.{next_version.minor}",
            "major_tag": str(next_version.major),
            "level": level,
        }
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
