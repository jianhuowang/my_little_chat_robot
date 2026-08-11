import os
import subprocess
from pathlib import Path
from random import Random

import pytest

from plugins.chihaya_emotes.image_pool import ImagePool


def write_fixture(path: Path, payload: bytes) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)
    return path


def test_refresh_recursively_indexes_supported_nonempty_visible_files(tmp_path) -> None:
    root = tmp_path / "images"
    expected = {
        write_fixture(root / "one.PNG", b"png-one").resolve(),
        write_fixture(root / "nested" / "two.jpg", b"jpg-two").resolve(),
        write_fixture(root / "nested" / "three.JPEG", b"jpeg-three").resolve(),
        write_fixture(root / "nested" / "four.gif", b"gif-four").resolve(),
        write_fixture(root / "nested" / "five.WeBp", b"webp-five").resolve(),
    }
    write_fixture(root / ".hidden.png", b"hidden-file")
    write_fixture(root / ".hidden" / "nested.png", b"hidden-directory")
    write_fixture(root / "empty.png", b"")
    write_fixture(root / "notes.txt", b"unsupported")

    pool = ImagePool(root, Random(0))

    assert pool.refresh() == len(expected)
    assert set(pool._paths) == expected
    assert pool._paths == sorted(expected, key=str)


def test_refresh_collapses_only_byte_identical_files_by_sha256(tmp_path) -> None:
    root = tmp_path / "images"
    canonical = write_fixture(root / "a.png", b"same-bytes").resolve()
    write_fixture(root / "b.jpg", b"same-bytes")
    distinct = write_fixture(root / "c.png", b"different-bytes").resolve()
    pool = ImagePool(root, Random(0))

    assert pool.refresh() == 2
    assert pool._paths == [canonical, distinct]


def test_choose_avoids_previous_path_for_the_same_session(tmp_path) -> None:
    root = tmp_path / "images"
    write_fixture(root / "a.png", b"a")
    write_fixture(root / "b.png", b"b")
    pool = ImagePool(root, Random(0))
    pool.refresh()

    first = pool.choose("session")
    second = pool.choose("session")

    assert first is not None
    assert second is not None
    assert second != first


def test_choose_rescans_once_after_all_indexed_files_disappear(tmp_path) -> None:
    root = tmp_path / "images"
    stale = write_fixture(root / "stale.png", b"stale")
    pool = ImagePool(root, Random(0))
    pool.refresh()
    stale.unlink()
    replacement = write_fixture(root / "replacement.jpg", b"replacement").resolve()

    assert pool.choose("session") == replacement


def test_discard_removes_only_the_exact_resolved_pool_entry(tmp_path) -> None:
    root = tmp_path / "images"
    first = write_fixture(root / "one.png", b"one").resolve()
    second = write_fixture(root / "one.png.extra.jpg", b"two").resolve()
    pool = ImagePool(root, Random(0))
    pool.refresh()

    pool.discard(root / "." / "one.png")

    assert pool._paths == [second]
    pool.discard(root / "missing.png")
    assert pool._paths == [second]
    assert first not in pool._paths


def test_refresh_does_not_follow_linked_directories(tmp_path) -> None:
    root = tmp_path / "images"
    outside = tmp_path / "outside"
    visible = write_fixture(root / "visible.png", b"visible").resolve()
    write_fixture(outside / "escaped.png", b"escaped")
    root.mkdir(exist_ok=True)
    link = root / "linked"
    try:
        os.symlink(outside, link, target_is_directory=True)
    except OSError as error:
        pytest.skip(f"directory symlinks are unavailable: {error}")
    pool = ImagePool(root, Random(0))

    assert pool.refresh() == 1
    assert pool._paths == [visible]


@pytest.mark.skipif(os.name != "nt", reason="junctions are Windows reparse points")
def test_refresh_does_not_follow_directory_junctions(tmp_path) -> None:
    root = tmp_path / "images"
    outside = tmp_path / "outside"
    visible = write_fixture(root / "visible.png", b"visible").resolve()
    write_fixture(outside / "escaped.png", b"escaped")
    link = root / "junction"
    result = subprocess.run(
        ["cmd.exe", "/d", "/c", "mklink", "/J", str(link), str(outside)],
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        pytest.skip(f"directory junctions are unavailable: {result.stderr}")
    pool = ImagePool(root, Random(0))

    assert pool.refresh() == 1
    assert pool._paths == [visible]
