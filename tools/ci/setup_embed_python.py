#!/usr/bin/env python3
"""
Setup embedded Python into install/python/.

- Windows: python.org embeddable zip
- macOS / Linux: astral-sh/python-build-standalone
"""

from __future__ import annotations

import os
import platform
import shutil
import stat
import subprocess
import sys
import tarfile
import urllib.request
import zipfile
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")  # type: ignore

PYTHON_VERSION = "3.13.15"
PBS_RELEASE_TAG = "20260814"
DEST_DIR = Path("install") / "python"


def fail(msg: str) -> None:
    print(f"ERROR: {msg}")
    sys.exit(1)


def download(url: str, dest: Path) -> None:
    print(f"Downloading: {url}")
    print(f"        to: {dest}")
    dest.parent.mkdir(parents=True, exist_ok=True)
    with urllib.request.urlopen(url) as resp, open(dest, "wb") as f:
        shutil.copyfileobj(resp, f)
    print("Done.")


def extract_zip(zip_path: Path, dest: Path) -> None:
    print(f"Extracting ZIP: {zip_path} -> {dest}")
    with zipfile.ZipFile(zip_path, "r") as zf:
        zf.extractall(dest)


def extract_tar(tar_path: Path, dest: Path) -> None:
    print(f"Extracting TAR: {tar_path} -> {dest}")
    with tarfile.open(tar_path, "r:*") as tf:
        tf.extractall(dest)


def get_python_exe(base: Path, os_name: str) -> Path | None:
    if os_name == "Windows":
        p = base / "python.exe"
        return p if p.exists() else None
    for name in ("python3", "python"):
        p = base / "bin" / name
        if p.exists():
            return p
    return None


def ensure_pip(python_exe: Path) -> None:
    get_pip = DEST_DIR / "get-pip.py"
    download("https://bootstrap.pypa.io/get-pip.py", get_pip)
    try:
        subprocess.run([str(python_exe), str(get_pip)], check=True)
        print("pip installed.")
    except subprocess.CalledProcessError as e:
        fail(f"pip install failed: {e}")
    finally:
        get_pip.unlink(missing_ok=True)


def setup_windows(arch: str) -> Path:
    arch_map = {
        "AMD64": "amd64",
        "x86_64": "amd64",
        "ARM64": "arm64",
        "aarch64": "arm64",
    }
    suffix = arch_map.get(arch)
    if suffix is None:
        fail(f"Unsupported Windows arch: {arch}")

    url = (
        f"https://www.python.org/ftp/python/{PYTHON_VERSION}/"
        f"python-{PYTHON_VERSION}-embed-{suffix}.zip"
    )
    zip_path = DEST_DIR / "python-embed.zip"
    download(url, zip_path)
    extract_zip(zip_path, DEST_DIR)
    zip_path.unlink(missing_ok=True)

    # 找 ._pth
    pth_files = list(DEST_DIR.glob("python*._pth"))
    if not pth_files:
        fail("No ._pth found in embeddable Python")
    pth = pth_files[0]
    content = pth.read_text(encoding="utf-8")
    content = content.replace("#import site", "import site")
    content = content.replace("# import site", "import site")
    for line in (".", "Lib", "Lib\\site-packages", "DLLs"):
        if line not in content.splitlines():
            content += f"\n{line}"
    pth.write_text(content, encoding="utf-8")

    exe = get_python_exe(DEST_DIR, "Windows")
    if exe is None:
        fail("python.exe not found after extraction")
    return exe


def setup_unix(os_name: str, arch: str) -> Path:
    arch_map = {
        "x86_64": "x86_64",
        "AMD64": "x86_64",
        "arm64": "aarch64",
        "aarch64": "aarch64",
    }
    pbs_arch = arch_map.get(arch)
    if pbs_arch is None:
        fail(f"Unsupported {os_name} arch: {arch}")

    if os_name == "Darwin":
        triple = f"{pbs_arch}-apple-darwin"
    else:
        triple = f"{pbs_arch}-unknown-linux-gnu"

    filename = (
        f"cpython-{PYTHON_VERSION}+{PBS_RELEASE_TAG}-{triple}"
        f"-install_only.tar.gz"
    )
    url = (
        f"https://github.com/astral-sh/python-build-standalone/releases/"
        f"download/{PBS_RELEASE_TAG}/{filename}"
    )
    tar_path = DEST_DIR / filename
    download(url, tar_path)

    tmp = DEST_DIR / "_tmp"
    tmp.mkdir(parents=True, exist_ok=True)
    extract_tar(tar_path, tmp)
    tar_path.unlink(missing_ok=True)

    extracted = tmp / "python"
    if not extracted.is_dir():
        fail(f"'python' dir not found under {tmp}")
    for item in extracted.iterdir():
        shutil.move(str(item), str(DEST_DIR / item.name))
    shutil.rmtree(tmp)

    bin_dir = DEST_DIR / "bin"
    if bin_dir.is_dir():
        for f in bin_dir.iterdir():
            if f.is_file():
                f.chmod(f.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)

    exe = get_python_exe(DEST_DIR, os_name)
    if exe is None:
        fail(f"python executable not found under {DEST_DIR}")
    return exe


def main() -> None:
    os_name = platform.system()
    arch = platform.machine()

    print(f"OS: {os_name}")
    print(f"Arch: {arch}")
    print(f"Target Python: {PYTHON_VERSION}")
    print(f"Install dir: {DEST_DIR}")

    if DEST_DIR.exists():
        print(f"Cleaning {DEST_DIR}")
        shutil.rmtree(DEST_DIR)
    DEST_DIR.mkdir(parents=True, exist_ok=True)

    if os_name == "Windows":
        exe = setup_windows(arch)
    elif os_name in ("Darwin", "Linux"):
        exe = setup_unix(os_name, arch)
    else:
        fail(f"Unsupported OS: {os_name}")

    print(f"Python executable: {exe}")
    ensure_pip(exe)
    print("Embedded Python setup complete.")


if __name__ == "__main__":
    main()