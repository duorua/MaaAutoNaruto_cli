#!/usr/bin/env python3
"""Build MaaAutoNaruto CLI package (MaaPiCli based)."""

from __future__ import annotations

import argparse
import re
import shutil
import sys
import urllib.request
import zipfile
from pathlib import Path

try:
    import jsonc as json_lib  # type: ignore
except ImportError:
    import json as json_lib  # type: ignore


OCR_DOWNLOAD_URL = (
    "https://download.maafw.xyz/MaaCommonAssets/OCR/ppocr_v6/ppocr_v6-small.zip"
)


def require_path(p: Path, label: str) -> Path:
    if not p.exists():
        raise FileNotFoundError(f"{label} not found: {p}")
    return p


def strip_html_tags(text: str) -> str:
    text = re.sub(r"<br\s*/?>", "\n", text, flags=re.IGNORECASE)
    return re.sub(r"<[^>]+>", "", text)


def strip_html_from(obj):
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k == "description" and isinstance(v, str):
                obj[k] = strip_html_tags(v)
            elif isinstance(v, (dict, list)):
                strip_html_from(v)
    elif isinstance(obj, list):
        for item in obj:
            if isinstance(item, (dict, list)):
                strip_html_from(item)


def install_maafw(deps_dir: Path, output_dir: Path) -> None:
    """从 MaaXYZ/MaaFramework 复制 C 库，排除 MaaPiCli 本体。"""
    shutil.copytree(
        require_path(deps_dir / "bin", "MaaFramework bin"),
        output_dir,
        dirs_exist_ok=True,
        ignore=shutil.ignore_patterns(
            "*MaaDbgControlUnit*",
            "*MaaThriftControlUnit*",
            "*MaaRpc*",
            "*MaaHttp*",
            "MaaPiCli*",  # 用 duorua 修正版，排除官方 MaaPiCli
        ),
    )
    shutil.copytree(
        require_path(deps_dir / "share" / "MaaAgentBinary", "MaaAgentBinary"),
        output_dir / "MaaAgentBinary",
        dirs_exist_ok=True,
    )


def install_resource(source_dir: Path, output_dir: Path, version: str) -> None:
    shutil.copytree(
        require_path(source_dir / "assets" / "resource", "resource"),
        output_dir / "resource",
        dirs_exist_ok=True,
    )
    shutil.copytree(
        require_path(source_dir / "assets" / "tasks", "tasks"),
        output_dir / "tasks",
        dirs_exist_ok=True,
    )
    shutil.copy2(
        require_path(source_dir / "assets" / "interface.json", "interface.json"),
        output_dir / "interface.json",
    )

    with open(output_dir / "interface.json", encoding="utf-8") as f:
        interface = json_lib.load(f)
    interface["version"] = version
    interface["title"] = f"MaaAutoNaruto {version} | 火影忍者手游小助手"
    strip_html_from(interface)
    with open(output_dir / "interface.json", "w", encoding="utf-8") as f:
        json_lib.dump(interface, f, ensure_ascii=False, indent=4)
        f.write("\n")

    for jf in (output_dir / "tasks").rglob("*.json"):
        with open(jf, encoding="utf-8") as f:
            data = json_lib.load(f)
        strip_html_from(data)
        with open(jf, "w", encoding="utf-8") as f:
            json_lib.dump(data, f, ensure_ascii=False, indent=4)
            f.write("\n")


def configure_ocr_model(output_dir: Path) -> None:
    ocr_dir = output_dir / "resource" / "base" / "model" / "ocr"
    if ocr_dir.exists() and any(ocr_dir.iterdir()):
        print(f"OCR model already exists, skip: {ocr_dir}")
        return

    print(f"Downloading OCR model from {OCR_DOWNLOAD_URL}...")
    ocr_dir.mkdir(parents=True, exist_ok=True)
    zip_path = output_dir / "resource" / "base" / "model" / "ocr.zip"
    urllib.request.urlretrieve(OCR_DOWNLOAD_URL, zip_path)

    print("Extracting OCR model...")
    with zipfile.ZipFile(zip_path, "r") as zip_ref:
        zip_ref.extractall(ocr_dir)
    zip_path.unlink()
    print(f"OCR model installed to {ocr_dir}")


def install_agent(source_dir: Path, output_dir: Path, platform: str) -> None:
    shutil.copytree(
        require_path(source_dir / "agent", "agent"),
        output_dir / "agent",
        dirs_exist_ok=True,
    )

    if platform.startswith("win"):
        child_exec = "python/python.exe"
    else:
        child_exec = "python/bin/python3"

    with open(output_dir / "interface.json", encoding="utf-8") as f:
        interface = json_lib.load(f)

    agent_cfg = interface.get("agent")
    if isinstance(agent_cfg, dict):
        agent_cfg = [agent_cfg]
    if not isinstance(agent_cfg, list):
        raise RuntimeError("interface.json must contain an agent object or list")

    for cfg in agent_cfg:
        cfg["child_exec"] = child_exec
        cfg["child_args"] = ["-u", "agent/main.py"]

    with open(output_dir / "interface.json", "w", encoding="utf-8") as f:
        json_lib.dump(interface, f, ensure_ascii=False, indent=4)
        f.write("\n")


def install_chores(source_dir: Path, output_dir: Path) -> None:
    # 不复制 requirements.txt（依赖已预装到包内 Python）
    for name in ["README.md", "LICENSE", "CONTACT", "DISCLAIMER.md"]:
        src = source_dir / name
        if src.exists():
            shutil.copy2(src, output_dir / name)

    docs = source_dir / "docs"
    if docs.exists():
        shutil.copytree(
            docs,
            output_dir / "docs",
            dirs_exist_ok=True,
            ignore=shutil.ignore_patterns("*.yaml"),
        )
    logo = source_dir / "docs" / "imgs" / "logo.ico"
    if logo.exists():
        shutil.copy2(logo, output_dir / "resource" / "logo.ico")


def install_python(python_dir: Path, output_dir: Path) -> None:
    require_path(python_dir, "embedded python")
    shutil.copytree(python_dir, output_dir / "python", dirs_exist_ok=True)


def install_picli(picli_dir: Path, output_dir: Path, platform: str) -> None:
    exe_name = "MaaPiCli.exe" if platform.startswith("win") else "MaaPiCli"
    candidates = list(picli_dir.rglob(exe_name))
    if not candidates:
        raise RuntimeError(f"MaaPiCli binary not found under {picli_dir}")
    src = candidates[0]
    dst_name = "MaaAutoNaruto.exe" if platform.startswith("win") else "MaaAutoNaruto"
    dst = output_dir / dst_name
    if dst.exists():
        dst.unlink()
    shutil.copy2(src, dst)
    if not platform.startswith("win"):
        dst.chmod(dst.stat().st_mode | 0o111)
    print(f"Installed {src.name} -> {dst_name}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build MaaAutoNaruto CLI package.")
    parser.add_argument("--source-dir", type=Path, required=True)
    parser.add_argument("--deps-dir", type=Path, required=True)
    parser.add_argument("--python-dir", type=Path, required=True)
    parser.add_argument("--picli-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--version", required=True)
    parser.add_argument("--platform", default=sys.platform)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    source_dir = args.source_dir.resolve()
    deps_dir = args.deps_dir.resolve()
    python_dir = args.python_dir.resolve()
    picli_dir = args.picli_dir.resolve()
    output_dir = args.output_dir.resolve()

    if output_dir.exists():
        shutil.rmtree(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    install_maafw(deps_dir, output_dir)
    install_resource(source_dir, output_dir, args.version)
    configure_ocr_model(output_dir)
    install_chores(source_dir, output_dir)
    install_agent(source_dir, output_dir, args.platform)
    install_python(python_dir, output_dir)
    install_picli(picli_dir, output_dir, args.platform)

    print(f"Install to {output_dir} successfully.")


if __name__ == "__main__":
    main()