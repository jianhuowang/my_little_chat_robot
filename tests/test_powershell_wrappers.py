from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
POWERSHELL = shutil.which("powershell")

pytestmark = pytest.mark.skipif(
    os.name != "nt" or POWERSHELL is None,
    reason="Windows PowerShell wrapper tests require Windows PowerShell",
)


def copy_wrapper(tmp_path: Path, name: str) -> tuple[Path, Path]:
    repo = tmp_path / "repo"
    scripts = repo / "scripts"
    scripts.mkdir(parents=True)
    wrapper = scripts / name
    shutil.copy2(REPO_ROOT / "scripts" / name, wrapper)
    return repo, wrapper


def fake_astrbot_environment(tmp_path: Path, exit_code: int) -> dict[str, str]:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    (bin_dir / "astrbot.cmd").write_text(
        (
            "@echo off\r\n"
            'if defined ASTRBOT_CWD_FILE cd > "%ASTRBOT_CWD_FILE%"\r\n'
            'if defined ASTRBOT_ARGS_FILE echo %* > "%ASTRBOT_ARGS_FILE%"\r\n'
            f"exit /b {exit_code}\r\n"
        ),
        encoding="ascii",
    )
    environment = os.environ.copy()
    environment.pop("ASTRBOT_RUNTIME_DIR", None)
    environment["PATH"] = f"{bin_dir}{os.pathsep}{environment['PATH']}"
    return environment


def run_wrapper(
    wrapper: Path, *arguments: str, environment: dict[str, str]
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            str(POWERSHELL),
            "-NoProfile",
            "-NonInteractive",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(wrapper),
            *arguments,
        ],
        cwd=wrapper.parent.parent,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )


def create_junction(link: Path, target: Path) -> None:
    command = (
        "& { param($Link, $Target) "
        "New-Item -ItemType Junction -Path $Link -Target $Target | Out-Null }"
    )
    subprocess.run(
        [str(POWERSHELL), "-NoProfile", "-Command", command, str(link), str(target)],
        check=True,
        capture_output=True,
        text=True,
    )


@pytest.mark.parametrize(
    "wrapper_name", ["Initialize-AstrBot.ps1", "Start-AstrBot.ps1"]
)
def test_astrbot_wrapper_propagates_child_exit_code(
    tmp_path: Path, wrapper_name: str
) -> None:
    repo, wrapper = copy_wrapper(tmp_path, wrapper_name)
    (repo / "runtime" / "astrbot").mkdir(parents=True)
    (repo / ".env").write_text(
        "DEEPSEEK_API_KEY=sk-test-secret\n", encoding="utf-8"
    )

    result = run_wrapper(
        wrapper,
        environment=fake_astrbot_environment(tmp_path, exit_code=23),
    )

    assert result.returncode == 23, result.stdout + result.stderr


@pytest.mark.parametrize(
    "wrapper_name", ["Initialize-AstrBot.ps1", "Start-AstrBot.ps1"]
)
def test_astrbot_wrapper_rejects_junction_in_runtime_path(
    tmp_path: Path, wrapper_name: str
) -> None:
    repo, wrapper = copy_wrapper(tmp_path, wrapper_name)
    runtime = repo / "runtime"
    runtime.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    create_junction(runtime / "astrbot", outside)
    (repo / ".env").write_text(
        "DEEPSEEK_API_KEY=sk-test-secret\n", encoding="utf-8"
    )

    result = run_wrapper(
        wrapper,
        environment=fake_astrbot_environment(tmp_path, exit_code=0),
    )

    assert result.returncode != 0
    assert "reparse point" in (result.stdout + result.stderr).lower()


def test_initialize_wrapper_uses_runtime_from_repository_env(tmp_path: Path) -> None:
    repo, wrapper = copy_wrapper(tmp_path, "Initialize-AstrBot.ps1")
    (repo / ".env").write_text(
        "DEEPSEEK_API_KEY=sk-test-secret\nASTRBOT_RUNTIME_DIR=from-env/astrbot\n",
        encoding="utf-8",
    )
    cwd_file = tmp_path / "astrbot-cwd.txt"
    environment = fake_astrbot_environment(tmp_path, exit_code=0)
    environment["ASTRBOT_CWD_FILE"] = str(cwd_file)

    result = run_wrapper(wrapper, environment=environment)

    assert result.returncode == 0, result.stdout + result.stderr
    assert Path(cwd_file.read_text(encoding="utf-8").strip()) == (
        repo / "from-env" / "astrbot"
    )


def test_initialize_wrapper_explicit_runtime_overrides_repository_env(
    tmp_path: Path,
) -> None:
    repo, wrapper = copy_wrapper(tmp_path, "Initialize-AstrBot.ps1")
    (repo / ".env").write_text(
        "DEEPSEEK_API_KEY=sk-test-secret\nASTRBOT_RUNTIME_DIR=from-env/astrbot\n",
        encoding="utf-8",
    )
    cwd_file = tmp_path / "astrbot-cwd.txt"
    environment = fake_astrbot_environment(tmp_path, exit_code=0)
    environment["ASTRBOT_CWD_FILE"] = str(cwd_file)

    result = run_wrapper(
        wrapper,
        "-RuntimeDir",
        "explicit/astrbot",
        environment=environment,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert Path(cwd_file.read_text(encoding="utf-8").strip()) == (
        repo / "explicit" / "astrbot"
    )


def test_initialize_wrapper_ignores_blank_runtime_in_repository_env(
    tmp_path: Path,
) -> None:
    repo, wrapper = copy_wrapper(tmp_path, "Initialize-AstrBot.ps1")
    (repo / ".env").write_text(
        "DEEPSEEK_API_KEY=sk-test-secret\nASTRBOT_RUNTIME_DIR=   \n",
        encoding="utf-8",
    )
    cwd_file = tmp_path / "astrbot-cwd.txt"
    environment = fake_astrbot_environment(tmp_path, exit_code=0)
    environment["ASTRBOT_CWD_FILE"] = str(cwd_file)

    result = run_wrapper(wrapper, environment=environment)

    assert result.returncode == 0, result.stdout + result.stderr
    assert Path(cwd_file.read_text(encoding="utf-8").strip()) == (
        repo / "runtime" / "astrbot"
    )


def test_initialize_wrapper_skips_astrbot_confirmation_prompt(tmp_path: Path) -> None:
    _repo, wrapper = copy_wrapper(tmp_path, "Initialize-AstrBot.ps1")
    args_file = tmp_path / "astrbot-args.txt"
    environment = fake_astrbot_environment(tmp_path, exit_code=0)
    environment["ASTRBOT_ARGS_FILE"] = str(args_file)

    result = run_wrapper(wrapper, environment=environment)

    assert result.returncode == 0, result.stdout + result.stderr
    assert args_file.read_text(encoding="utf-8").strip() == "init --yes"
