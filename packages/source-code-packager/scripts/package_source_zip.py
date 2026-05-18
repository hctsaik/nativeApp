#!/usr/bin/env python3
"""Create clean source zips, optionally safe for Gmail attachments."""

from __future__ import annotations

import argparse
import compileall
import os
import shutil
import sys
import tempfile
import zipfile
from pathlib import Path


DEFAULT_EXCLUDE_DIRS = {
    ".git",
    ".hg",
    ".svn",
    ".venv",
    "venv",
    "env",
    "node_modules",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    "dist",
    "build",
    "tmp",
    "temp",
    "logs",
    "log",
    "images",
    "video",
    "videos",
    "outputs",
    "artifacts",
    "coverage",
    ".next",
    ".nuxt",
    ".turbo",
    "target",
    "bin",
    "obj",
}

DEFAULT_EXCLUDE_EXTS = {
    ".pyc",
    ".pyo",
    ".log",
    ".tmp",
    ".npy",
    ".npz",
    ".zip",
    ".7z",
    ".rar",
    ".tar",
    ".gz",
    ".tgz",
    ".bz2",
}

GMAIL_BLOCKED_EXTS = {
    ".ade",
    ".adp",
    ".apk",
    ".appx",
    ".appxbundle",
    ".bat",
    ".cab",
    ".chm",
    ".cmd",
    ".com",
    ".cpl",
    ".diagcab",
    ".diagcfg",
    ".diagpkg",
    ".dll",
    ".dmg",
    ".ex",
    ".ex_",
    ".exe",
    ".hta",
    ".img",
    ".ins",
    ".iso",
    ".isp",
    ".jar",
    ".jnlp",
    ".js",
    ".jse",
    ".lib",
    ".lnk",
    ".mde",
    ".mjs",
    ".msc",
    ".msi",
    ".msix",
    ".msixbundle",
    ".msp",
    ".mst",
    ".nsh",
    ".pif",
    ".ps1",
    ".scr",
    ".sct",
    ".shb",
    ".sys",
    ".vb",
    ".vbe",
    ".vbs",
    ".vhd",
    ".vxd",
    ".wsc",
    ".wsf",
    ".wsh",
    ".xll",
}


def split_csv(value: str | None) -> list[str]:
    if not value:
        return []
    return [part.strip() for part in value.split(",") if part.strip()]


def is_excluded(path: Path, root: Path, exclude_dirs: set[str], exclude_exts: set[str]) -> bool:
    rel_parts = path.relative_to(root).parts
    if any(part in exclude_dirs for part in rel_parts):
        return True
    return path.suffix.lower() in exclude_exts


def default_includes(root: Path) -> list[Path]:
    names = [
        "src",
        "app",
        "lib",
        "include",
        "docs",
        "doc",
        "launcher",
        "tests",
        "test",
        "examples",
        "example",
        "README.md",
        "README.txt",
        "LICENSE",
        "LICENSE.txt",
        "CHANGELOG.md",
        "requirements.txt",
        "pyproject.toml",
        "setup.py",
        "setup.cfg",
        "Pipfile",
        "poetry.lock",
        "package.json",
        "package-lock.json",
        "pnpm-lock.yaml",
        "yarn.lock",
        "tsconfig.json",
        "vite.config.js",
        "vite.config.ts",
        "next.config.js",
        "Cargo.toml",
        "Cargo.lock",
        "go.mod",
        "go.sum",
        "pom.xml",
        "build.gradle",
        "settings.gradle",
        "CMakeLists.txt",
        "Makefile",
        ".gitignore",
        "config.yaml",
        "config.yml",
        "config.json",
        "main.py",
        "build.bat",
        "run_gui.bat",
        "setup.bat",
    ]
    return [root / name for name in names if (root / name).exists()]


def collect_files(root: Path, includes: list[str], include_all: bool, exclude_dirs: set[str], exclude_exts: set[str], force_include: list[Path] | None = None) -> list[Path]:
    include_paths = [root] if include_all else ([root / item for item in includes] if includes else default_includes(root))
    files: list[Path] = []
    for item in include_paths:
        if item.is_file() and not is_excluded(item, root, exclude_dirs, exclude_exts):
            files.append(item)
        elif item.is_dir():
            for file in item.rglob("*"):
                if file.is_file() and not is_excluded(file, root, exclude_dirs, exclude_exts):
                    files.append(file)
    # --include-file entries bypass exclude rules
    for forced in (force_include or []):
        if forced.is_file():
            files.append(forced)
    return sorted(set(files), key=lambda p: p.relative_to(root).as_posix().lower())


def gmail_entry_name(relative: str) -> str:
    if Path(relative).suffix.lower() in GMAIL_BLOCKED_EXTS:
        return relative + ".txt"
    return relative


def write_text_entry(zf: zipfile.ZipFile, name: str, content: str) -> None:
    zf.writestr(name, content.replace("\n", os.linesep))


def gmail_readme() -> str:
    return """README AFTER EXTRACTING
=======================

This package was renamed to pass Gmail attachment security checks.
Gmail blocks some executable/script file types even when they are inside a zip file.

After extracting this zip, restore renamed files before using the project.
Examples:

  build.bat.txt    -> build.bat
  run_gui.bat.txt  -> run_gui.bat
  setup.bat.txt    -> setup.bat
  src/app.js.txt   -> src/app.js

Automatic restore option:

  python restore_gmail_safe_filenames.py

Manual restore option:

  Rename the .txt-suffixed files listed in the restore script back to their original names.
"""


def restore_script(renames: dict[str, str]) -> str:
    mapping = "{\n" + "".join(f'    "{src}": "{dst}",\n' for src, dst in renames.items()) + "}\n"
    return f"""from pathlib import Path

RENAMES = {mapping}
root = Path(__file__).resolve().parent
changed = []
skipped = []

for source_name, target_name in RENAMES.items():
    source = root / source_name
    target = root / target_name
    if target.exists():
        skipped.append(f"{{target_name}} already exists")
        continue
    if not source.exists():
        skipped.append(f"{{source_name}} not found")
        continue
    source.rename(target)
    changed.append(f"{{source_name}} -> {{target_name}}")

if changed:
    print("Restored Gmail-safe filenames:")
    for item in changed:
        print(f"  {{item}}")
else:
    print("No batch files were restored.")

if skipped:
    print("\\nSkipped:")
    for item in skipped:
        print(f"  {{item}}")
"""


def build_zip(root: Path, output: Path, files: list[Path], gmail_safe: bool) -> None:
    renames: dict[str, str] = {}
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for file in files:
            rel = file.relative_to(root).as_posix()
            entry = gmail_entry_name(rel) if gmail_safe else rel
            if entry != rel:
                renames[entry] = rel
            zf.write(file, entry)
        if gmail_safe:
            write_text_entry(zf, "README_AFTER_EXTRACT.txt", gmail_readme())
            write_text_entry(zf, "restore_gmail_safe_filenames.py", restore_script(renames))


def validate_zip(output: Path, required: list[str], gmail_safe: bool, compile_python: bool) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    with zipfile.ZipFile(output) as zf:
        entries = {info.filename for info in zf.infolist()}
        if not entries:
            errors.append("zip has no entries")
        for item in required:
            if item not in entries:
                errors.append(f"missing required entry: {item}")
        blocked = sorted(
            entry for entry in entries if Path(entry).suffix.lower() in GMAIL_BLOCKED_EXTS
        )
        if gmail_safe and blocked:
            errors.append("Gmail-blocked entries found: " + ", ".join(blocked))

    if compile_python:
        temp_dir = Path(tempfile.mkdtemp(prefix="source_zip_verify_"))
        try:
            with zipfile.ZipFile(output) as zf:
                zf.extractall(temp_dir)
            ok = compileall.compile_dir(temp_dir, quiet=1)
            if not ok:
                errors.append("python compileall failed after extraction")
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)
    return errors, warnings


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=".", help="project root")
    parser.add_argument("--name", default=None, help="output zip base name or path")
    parser.add_argument("--include", default=None, help="comma-separated include paths")
    parser.add_argument("--include-all", action="store_true", help="include the whole root, then apply excludes")
    parser.add_argument("--exclude-dir", action="append", default=[], help="extra directory name to exclude")
    parser.add_argument("--exclude-ext", action="append", default=[], help="extra extension to exclude")
    parser.add_argument("--include-file", action="append", default=[], help="specific file path (relative to root) to always include, bypassing exclude rules")
    parser.add_argument("--required", default=None, help="comma-separated required archive entries")
    parser.add_argument("--gmail-safe", action="store_true")
    parser.add_argument("--no-compile", action="store_true")
    args = parser.parse_args()

    root = Path(args.root).resolve()
    if not root.exists():
        print(f"root does not exist: {root}", file=sys.stderr)
        return 2

    output = Path(args.name) if args.name else root / f"{root.name}_source.zip"
    if output.suffix.lower() != ".zip":
        output = output.with_suffix(".zip")
    if not output.is_absolute():
        output = root / output
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.exists():
        output.unlink()

    exclude_dirs = set(DEFAULT_EXCLUDE_DIRS) | set(args.exclude_dir)
    exclude_exts = set(DEFAULT_EXCLUDE_EXTS) | {ext if ext.startswith(".") else f".{ext}" for ext in args.exclude_ext}
    force_include = [root / f for f in args.include_file]
    missing = [str(f) for f in force_include if not f.exists()]
    if missing:
        for m in missing:
            print(f"Warning: --include-file not found: {m}", file=sys.stderr)
    files = collect_files(root, split_csv(args.include), args.include_all, exclude_dirs, exclude_exts, force_include)
    build_zip(root, output, files, args.gmail_safe)

    required = split_csv(args.required)
    errors, warnings = validate_zip(output, required, args.gmail_safe, not args.no_compile)
    with zipfile.ZipFile(output) as zf:
        entry_count = len(zf.infolist())

    print(f"ZipPath: {output}")
    print(f"EntryCount: {entry_count}")
    print(f"SizeBytes: {output.stat().st_size}")
    for warning in warnings:
        print(f"Warning: {warning}")
    if errors:
        for error in errors:
            print(f"Error: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
