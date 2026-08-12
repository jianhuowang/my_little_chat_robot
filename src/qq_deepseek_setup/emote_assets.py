from __future__ import annotations

import hashlib
import os
import shutil
import stat
from collections.abc import Iterator, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
from uuid import uuid4

from PIL import Image, UnidentifiedImageError


SUPPORTED_SUFFIXES = frozenset({".png", ".jpg", ".jpeg", ".gif", ".webp"})


@dataclass(frozen=True)
class AssetSummary:
    discovered: int
    installed: int
    duplicates: int
    failed: int
    converted_webp: int
    destination: Path

    def to_public_dict(self) -> dict[str, object]:
        return {
            "discovered": self.discovered,
            "installed": self.installed,
            "duplicates": self.duplicates,
            "failed": self.failed,
            "converted_webp": self.converted_webp,
            "destination": str(self.destination),
        }


def prepare_emotes(
    source_dirs: Sequence[Path], destination: Path, allowed_root: Path
) -> AssetSummary:
    root = allowed_root.expanduser().absolute()
    target = destination.expanduser().absolute()
    _validate_target(root, target)
    root = root.resolve(strict=False)
    target = target.resolve(strict=False)
    _validate_target(root, target)
    sources = [_validate_source(Path(source)) for source in source_dirs]

    parent = target.parent
    parent.mkdir(parents=True, exist_ok=True)
    _validate_target(root, target)
    staging = parent / f"{target.name}.staging-{uuid4().hex}"
    _validate_managed_sibling(target, staging)
    staging.mkdir()

    discovered = installed = duplicates = failed = converted_webp = 0
    seen: set[str] = set()
    backup: Path | None = None
    try:
        for source in sources:
            for candidate in _walk_images(source):
                discovered += 1
                try:
                    output_bytes, suffix, converted = _validated_bytes(candidate)
                except (OSError, UnidentifiedImageError, ValueError):
                    failed += 1
                    continue
                digest = hashlib.sha256(output_bytes).hexdigest()
                if digest in seen:
                    duplicates += 1
                    continue
                seen.add(digest)
                (staging / f"{digest}{suffix}").write_bytes(output_bytes)
                installed += 1
                converted_webp += int(converted)

        if target.exists():
            if _path_is_reparse(target) or not target.is_dir():
                raise ValueError("destination must be a regular directory")
            timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
            backup = parent / f"{target.name}.backup-{timestamp}"
            _validate_managed_sibling(target, backup)
            os.replace(target, backup)
        try:
            os.replace(staging, target)
        except BaseException:
            if backup is not None and backup.exists() and not target.exists():
                os.replace(backup, target)
            raise
    finally:
        _remove_staging(target, staging)

    return AssetSummary(
        discovered,
        installed,
        duplicates,
        failed,
        converted_webp,
        target.resolve(),
    )


def _validate_source(source: Path) -> Path:
    absolute = source.expanduser().absolute()
    if not absolute.exists() or not absolute.is_dir():
        raise ValueError("source directory does not exist")
    _assert_no_reparse_components(
        absolute, "source directory must not traverse a reparse point"
    )
    return absolute.resolve(strict=True)


def _validate_target(root: Path, target: Path) -> None:
    if target == root or not _is_relative_to(target, root):
        raise ValueError("destination must stay inside allowed root")
    _assert_no_reparse_components(
        target, "destination must not traverse a reparse point"
    )


def _assert_no_reparse_components(path: Path, message: str) -> None:
    current = Path(path.anchor)
    for part in path.parts[1:]:
        current = current / part
        if not current.exists():
            break
        if _path_is_reparse(current):
            raise ValueError(message)


def _walk_images(root: Path) -> Iterator[Path]:
    stack = [root]
    while stack:
        directory = stack.pop()
        try:
            with os.scandir(directory) as entries:
                children: list[Path] = []
                for entry in entries:
                    if _entry_is_reparse(entry):
                        continue
                    try:
                        if entry.is_dir(follow_symlinks=False):
                            children.append(Path(entry.path))
                        elif (
                            entry.is_file(follow_symlinks=False)
                            and Path(entry.name).suffix.lower() in SUPPORTED_SUFFIXES
                        ):
                            yield Path(entry.path)
                    except OSError:
                        continue
        except OSError:
            continue
        stack.extend(sorted(children, key=str, reverse=True))


def _validated_bytes(path: Path) -> tuple[bytes, str, bool]:
    source_bytes = path.read_bytes()
    source = BytesIO(source_bytes)
    with Image.open(source) as image:
        image.verify()
    source.seek(0)
    with Image.open(source) as image:
        for frame_number in range(getattr(image, "n_frames", 1)):
            image.seek(frame_number)
            image.load()
    if path.suffix.lower() != ".webp":
        return source_bytes, path.suffix.lower(), False

    output = BytesIO()
    source.seek(0)
    with Image.open(source) as image:
        converted = image.convert("RGBA" if "A" in image.getbands() else "RGB")
        converted.save(output, format="PNG")
    return output.getvalue(), ".png", True


def _remove_staging(target: Path, staging: Path) -> None:
    if not staging.exists():
        return
    _validate_managed_sibling(target, staging)
    if _path_is_reparse(staging) or not staging.is_dir():
        raise RuntimeError("refusing to remove unexpected staging path")
    shutil.rmtree(staging)


def _validate_managed_sibling(target: Path, candidate: Path) -> None:
    if candidate.parent != target.parent or not candidate.name.startswith(
        f"{target.name}."
    ):
        raise RuntimeError("managed path is not an expected destination sibling")


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


def _entry_is_reparse(entry: os.DirEntry[str]) -> bool:
    try:
        if entry.is_symlink():
            return True
        attributes = getattr(entry.stat(follow_symlinks=False), "st_file_attributes", 0)
    except OSError:
        return True
    return bool(attributes & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0))


def _path_is_reparse(path: Path) -> bool:
    try:
        if path.is_symlink() or path.is_junction():
            return True
        attributes = getattr(path.stat(follow_symlinks=False), "st_file_attributes", 0)
    except OSError:
        return True
    return bool(attributes & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0))
