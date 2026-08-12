from __future__ import annotations

import hashlib
import os
from pathlib import Path

import pytest


def _create_sources(root: Path) -> tuple[Path, str]:
    from PIL import Image

    first = root / "first"
    second = root / "second" / "nested"
    first.mkdir(parents=True)
    second.mkdir(parents=True)

    png = first / "private-source-name.png"
    Image.new("RGBA", (3, 2), (10, 20, 30, 255)).save(png, format="PNG")
    duplicate_name = "another-private-name.png"
    (second / duplicate_name).write_bytes(png.read_bytes())
    Image.new("RGB", (2, 3), (90, 80, 70)).save(
        second / "private-webp-name.webp", format="WEBP"
    )
    return first, duplicate_name


def test_prepare_emotes_hashes_deduplicates_and_converts_webp(tmp_path: Path) -> None:
    from PIL import Image
    from qq_deepseek_setup.emote_assets import prepare_emotes

    source_one, _ = _create_sources(tmp_path / "sources")
    source_two = tmp_path / "sources" / "second"
    allowed_root = tmp_path / "runtime"
    destination = allowed_root / "plugins" / "chihaya_emotes" / "emotes"

    summary = prepare_emotes([source_one, source_two], destination, allowed_root)

    installed = sorted(destination.iterdir())
    assert summary.discovered == 3
    assert summary.installed == 2
    assert summary.duplicates == 1
    assert summary.failed == 0
    assert summary.converted_webp == 1
    assert summary.destination == destination.resolve()
    assert len(installed) == 2
    for asset in installed:
        assert asset.name == f"{hashlib.sha256(asset.read_bytes()).hexdigest()}{asset.suffix}"
        assert asset.suffix == ".png"
        with Image.open(asset) as image:
            image.verify()


def test_prepare_emotes_rejects_destination_outside_allowed_root(
    tmp_path: Path,
) -> None:
    from qq_deepseek_setup.emote_assets import prepare_emotes

    source = tmp_path / "source"
    source.mkdir()
    allowed_root = tmp_path / "runtime"
    outside = tmp_path / "outside" / "emotes"

    with pytest.raises(ValueError, match="allowed root"):
        prepare_emotes([source], outside, allowed_root)

    assert not outside.exists()
    assert not any(tmp_path.glob("outside*staging*"))


def test_prepare_emotes_rejects_destination_equal_to_allowed_root(
    tmp_path: Path,
) -> None:
    from qq_deepseek_setup.emote_assets import prepare_emotes

    source = tmp_path / "source"
    source.mkdir()
    allowed_root = tmp_path / "runtime"

    with pytest.raises(ValueError, match="inside allowed root"):
        prepare_emotes([source], allowed_root, allowed_root)

    assert not allowed_root.exists()
    assert not any(tmp_path.glob("runtime.staging-*"))


def test_prepare_emotes_rejects_dotdot_destination_escape(tmp_path: Path) -> None:
    from qq_deepseek_setup.emote_assets import prepare_emotes

    source = tmp_path / "source"
    source.mkdir()
    allowed_root = tmp_path / "runtime"
    escaped = allowed_root / "nested" / ".." / ".." / "outside" / "emotes"

    with pytest.raises(ValueError, match="allowed root"):
        prepare_emotes([source], escaped, allowed_root)

    assert not (tmp_path / "outside").exists()


def test_prepare_emotes_skips_symlinked_source_entries(tmp_path: Path) -> None:
    from PIL import Image
    from qq_deepseek_setup.emote_assets import prepare_emotes

    source = tmp_path / "source"
    outside = tmp_path / "outside"
    source.mkdir()
    outside.mkdir()
    Image.new("RGB", (1, 1), "red").save(outside / "secret.png")
    try:
        (source / "linked").symlink_to(outside, target_is_directory=True)
    except OSError:
        pytest.skip("directory symlinks are unavailable")

    destination = tmp_path / "runtime" / "emotes"
    summary = prepare_emotes([source], destination, tmp_path / "runtime")

    assert summary.discovered == 0
    assert list(destination.iterdir()) == []


def test_prepare_emotes_preserves_source_and_counts_invalid_images(
    tmp_path: Path,
) -> None:
    from qq_deepseek_setup.emote_assets import prepare_emotes

    source = tmp_path / "source"
    source.mkdir()
    invalid = source / "not-really-an-image.png"
    original = b"not an image"
    invalid.write_bytes(original)

    destination = tmp_path / "runtime" / "emotes"
    summary = prepare_emotes([source], destination, tmp_path / "runtime")

    assert summary.discovered == 1
    assert summary.installed == 0
    assert summary.failed == 1
    assert invalid.read_bytes() == original
    assert list(destination.iterdir()) == []


def test_prepare_emotes_requires_a_complete_pixel_decode(tmp_path: Path) -> None:
    from PIL import Image
    from qq_deepseek_setup.emote_assets import prepare_emotes

    source = tmp_path / "source"
    source.mkdir()
    truncated = source / "truncated.jpg"
    complete = source / "complete.jpg"
    Image.new("RGB", (32, 32), (1, 2, 3)).save(complete, format="JPEG")
    truncated.write_bytes(complete.read_bytes()[:-1])
    complete.unlink()

    with Image.open(truncated) as image:
        image.verify()
    with pytest.raises(OSError, match="truncated"):
        with Image.open(truncated) as image:
            image.load()

    destination = tmp_path / "runtime" / "emotes"
    summary = prepare_emotes([source], destination, tmp_path / "runtime")

    assert summary.discovered == 1
    assert summary.installed == 0
    assert summary.failed == 1
    assert list(destination.iterdir()) == []


@pytest.mark.skipif(os.name != "nt", reason="junction safety is Windows-specific")
def test_prepare_emotes_rejects_junction_in_destination_path(tmp_path: Path) -> None:
    import subprocess

    from qq_deepseek_setup.emote_assets import prepare_emotes

    source = tmp_path / "source"
    allowed_root = tmp_path / "runtime"
    outside = tmp_path / "outside"
    source.mkdir()
    allowed_root.mkdir()
    outside.mkdir()
    link = allowed_root / "linked"
    subprocess.run(
        [
            "powershell",
            "-NoProfile",
            "-Command",
            (
                "& { param($Link, $Target) "
                "New-Item -ItemType Junction -Path $Link -Target $Target | Out-Null }"
            ),
            str(link),
            str(outside),
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    with pytest.raises(ValueError, match="reparse point"):
        prepare_emotes([source], link / "emotes", allowed_root)

    assert list(outside.iterdir()) == []


@pytest.mark.skipif(os.name != "nt", reason="junction safety is Windows-specific")
def test_prepare_emotes_rejects_junction_in_source_path(tmp_path: Path) -> None:
    import subprocess

    from qq_deepseek_setup.emote_assets import prepare_emotes

    sources = tmp_path / "sources"
    outside = tmp_path / "outside"
    nested = outside / "nested"
    sources.mkdir()
    nested.mkdir(parents=True)
    link = sources / "linked"
    subprocess.run(
        [
            "powershell",
            "-NoProfile",
            "-Command",
            (
                "& { param($Link, $Target) "
                "New-Item -ItemType Junction -Path $Link -Target $Target | Out-Null }"
            ),
            str(link),
            str(outside),
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    with pytest.raises(ValueError, match="reparse point"):
        prepare_emotes(
            [link / "nested"], tmp_path / "runtime" / "emotes", tmp_path / "runtime"
        )

    assert not (tmp_path / "runtime").exists()


@pytest.mark.skipif(os.name != "nt", reason="junction safety is Windows-specific")
def test_prepare_emotes_rejects_junction_above_allowed_root(tmp_path: Path) -> None:
    import subprocess

    from qq_deepseek_setup.emote_assets import prepare_emotes

    source = tmp_path / "source"
    outside = tmp_path / "outside"
    source.mkdir()
    (outside / "nested").mkdir(parents=True)
    link = tmp_path / "linked-runtime"
    subprocess.run(
        [
            "powershell",
            "-NoProfile",
            "-Command",
            (
                "& { param($Link, $Target) "
                "New-Item -ItemType Junction -Path $Link -Target $Target | Out-Null }"
            ),
            str(link),
            str(outside),
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    with pytest.raises(ValueError, match="reparse point"):
        prepare_emotes([source], link / "nested" / "emotes", link / "nested")

    assert list((outside / "nested").iterdir()) == []


def test_prepare_emotes_restores_previous_destination_when_replace_fails(
    monkeypatch, tmp_path: Path
) -> None:
    from PIL import Image
    from qq_deepseek_setup import emote_assets

    source = tmp_path / "source"
    source.mkdir()
    Image.new("RGB", (1, 1), "blue").save(source / "new.png")
    allowed_root = tmp_path / "runtime"
    destination = allowed_root / "emotes"
    destination.mkdir(parents=True)
    previous = destination / "previous.txt"
    previous.write_text("keep me", encoding="utf-8")
    real_replace = emote_assets.os.replace

    def fail_staging_replace(source_path, destination_path):
        if ".staging-" in Path(source_path).name:
            raise OSError("simulated final replace failure")
        return real_replace(source_path, destination_path)

    monkeypatch.setattr(emote_assets.os, "replace", fail_staging_replace)

    with pytest.raises(OSError, match="simulated final replace failure"):
        emote_assets.prepare_emotes([source], destination, allowed_root)

    assert previous.read_text(encoding="utf-8") == "keep me"
    assert not list(allowed_root.glob("emotes.staging-*"))
