"""Build a Windows directory distribution without including private handoffs or raw demos."""

import argparse
import json
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def make_zip(target: Path | None = None) -> Path:
    """Portable ZIP with forward-slash entries (PowerShell 5 Compress-Archive writes backslashes)."""
    from openingroutes import __version__

    target = target or ROOT / "artifacts/desktop/OpeningRoutes"
    archive = ROOT / f"artifacts/OpeningRoutes-v{__version__}-windows.zip"
    partial = archive.with_suffix(".zip.part")
    with zipfile.ZipFile(partial, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as z:
        for path in sorted(target.rglob("*")):
            if path.is_file():
                z.write(path, f"{target.name}/{path.relative_to(target).as_posix()}")
    with zipfile.ZipFile(partial) as z:
        if z.testzip() is not None:
            raise RuntimeError("ZIP verification failed")
    partial.replace(archive)
    return archive


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--seed-from", type=Path)
    args = parser.parse_args()
    seed = ROOT / ".local/package-seed"
    if seed.exists():
        if not seed.resolve().is_relative_to((ROOT / ".local").resolve()) or seed.is_symlink():
            raise ValueError("Refusing to replace a seed directory outside the local build workspace")
        shutil.rmtree(seed)
    seed.mkdir(parents=True)
    if args.seed_from:
        from openingroutes.store import Store

        source = Store(args.seed_from)
        matches = list(source.all("matches").values())
        (seed / "matches.json").write_text(json.dumps(matches, ensure_ascii=False), encoding="utf-8")
        shutil.copytree(source.root / "timelines", seed / "timelines", dirs_exist_ok=True)
    command = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--windowed",
        "--onedir",
        "--name",
        "OpeningRoutes",
        "--distpath",
        str(ROOT / "artifacts/desktop"),
        "--workpath",
        str(ROOT / ".local/pyinstaller"),
        "--specpath",
        str(ROOT / ".local"),
        "--add-data",
        f"{ROOT / 'web/dist'};web",
        "--add-data",
        f"{seed};seed",
        "--hidden-import",
        "openingroutes.worker",
        "--collect-all",
        "demoparser2",
        "--collect-all",
        "webview",
        "--collect-all",
        "pythonnet",
        str(ROOT / "launch.py"),
    ]
    subprocess.run(command, check=True, cwd=ROOT)
    target = ROOT / "artifacts/desktop/OpeningRoutes"
    (target / "使用说明.txt").write_text(
        "OpeningRoutes v0.2.0 本地预览\n\n双击 OpeningRoutes.exe 启动。\n"
        "数据保存在 %LOCALAPPDATA%\\OpeningRoutes；请备份整个目录。\n"
        "附带的职业比赛投掷是提取记录，教学仍需补齐原片、图示及游戏内复现。\n"
        "从“数据与内容管理”导入新 Demo，在道具详情中整理教学。\n"
        "手枪局有独立入口，可查看装备、全回合路线和结果。\n"
        "区域、投法变体与异常回合复核在“数据与内容管理”和道具详情中。\n"
        "本版本不自动录制游戏，不代表已有通过复现核验的完整教程。\n",
        encoding="utf-8",
    )
    print(target)
    print(make_zip(target))


if __name__ == "__main__":
    main()
