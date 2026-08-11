from __future__ import annotations

import hashlib
import os
import stat
from collections.abc import Iterator
from pathlib import Path
from random import Random


SUPPORTED_SUFFIXES = frozenset({".png", ".jpg", ".jpeg", ".gif", ".webp"})


class ImagePool:
    def __init__(self, root: Path, rng: Random) -> None:
        self.root = root.absolute()
        self._rng = rng
        self._paths: list[Path] = []
        self._last_by_session: dict[str, Path] = {}

    def refresh(self) -> int:
        if self._path_is_reparse(self.root) or not self.root.is_dir():
            self._paths = []
            return 0

        candidates: list[Path] = []
        for path in self._walk_files():
            try:
                if (
                    path.suffix.lower() not in SUPPORTED_SUFFIXES
                    or path.stat().st_size == 0
                ):
                    continue
            except OSError:
                continue
            candidates.append(path.resolve())

        unique: list[Path] = []
        seen_digests: set[bytes] = set()
        for path in sorted(candidates, key=str):
            try:
                digest = self._digest(path)
            except OSError:
                continue
            if digest in seen_digests:
                continue
            seen_digests.add(digest)
            unique.append(path)
        self._paths = unique
        return len(self._paths)

    def choose(self, session_key: str) -> Path | None:
        available = [path for path in self._paths if path.is_file()]
        if not available:
            self.refresh()
            available = [path for path in self._paths if path.is_file()]
        if not available:
            return None
        previous = self._last_by_session.get(session_key)
        candidates = [path for path in available if path != previous] or available
        chosen = self._rng.choice(candidates)
        self._last_by_session[session_key] = chosen
        return chosen

    def discard(self, path: Path) -> None:
        try:
            target = path.resolve()
        except OSError:
            return
        self._paths = [entry for entry in self._paths if entry != target]

    def _walk_files(self) -> Iterator[Path]:
        stack = [self.root]
        while stack:
            directory = stack.pop()
            if self._path_is_reparse(directory):
                continue
            try:
                with os.scandir(directory) as entries:
                    directories: list[Path] = []
                    for entry in entries:
                        if entry.name.startswith(".") or self._entry_is_reparse(entry):
                            continue
                        try:
                            if entry.is_dir(follow_symlinks=False):
                                directories.append(Path(entry.path))
                            elif entry.is_file(follow_symlinks=False):
                                yield Path(entry.path)
                        except OSError:
                            continue
            except OSError:
                continue
            stack.extend(sorted(directories, key=str, reverse=True))

    @staticmethod
    def _entry_is_reparse(entry: os.DirEntry[str]) -> bool:
        try:
            if entry.is_symlink():
                return True
            attributes = getattr(
                entry.stat(follow_symlinks=False), "st_file_attributes", 0
            )
        except OSError:
            return True
        return bool(attributes & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0))

    @staticmethod
    def _path_is_reparse(path: Path) -> bool:
        try:
            if path.is_symlink() or path.is_junction():
                return True
            attributes = getattr(path.stat(follow_symlinks=False), "st_file_attributes", 0)
        except OSError:
            return True
        return bool(attributes & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0))

    @staticmethod
    def _digest(path: Path) -> bytes:
        digest = hashlib.sha256()
        with path.open("rb") as image_file:
            for chunk in iter(lambda: image_file.read(128 * 1024), b""):
                digest.update(chunk)
        return digest.digest()
