from __future__ import annotations

import hashlib
from pathlib import Path
from random import Random


SUPPORTED_SUFFIXES = frozenset({".png", ".jpg", ".jpeg", ".gif", ".webp"})


class ImagePool:
    def __init__(self, root: Path, rng: Random) -> None:
        self.root = root.resolve()
        self._rng = rng
        self._paths: list[Path] = []
        self._last_by_session: dict[str, Path] = {}

    def refresh(self) -> int:
        if not self.root.is_dir():
            self._paths = []
            return 0

        candidates: list[Path] = []
        for path in self.root.rglob("*"):
            relative = path.relative_to(self.root)
            if any(part.startswith(".") for part in relative.parts):
                continue
            if self._has_reparse_component(path):
                continue
            try:
                if (
                    not path.is_file()
                    or path.suffix.lower() not in SUPPORTED_SUFFIXES
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

    def _has_reparse_component(self, path: Path) -> bool:
        current = path
        while current != self.root:
            try:
                if current.is_symlink() or current.is_junction():
                    return True
            except OSError:
                return True
            current = current.parent
        return False

    @staticmethod
    def _digest(path: Path) -> bytes:
        digest = hashlib.sha256()
        with path.open("rb") as image_file:
            for chunk in iter(lambda: image_file.read(128 * 1024), b""):
                digest.update(chunk)
        return digest.digest()
