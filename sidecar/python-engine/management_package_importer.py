from __future__ import annotations

import ast
import hashlib
import io
import re
import zipfile
from dataclasses import dataclass, field
from pathlib import PurePosixPath
from typing import Any

import yaml


MAX_PACKAGE_BYTES = 10 * 1024 * 1024
MAX_FILE_COUNT = 64
MAX_FILE_BYTES = 512 * 1024
MAX_COMPRESSION_RATIO = 100
ALLOWED_SUFFIXES = {".py", ".yaml", ".yml", ".md", ".txt", ".html"}
BLOCKED_SUFFIXES = {".exe", ".dll", ".pyd", ".bat", ".cmd", ".ps1", ".sh", ".so", ".dylib"}
MODULE_ID_RE = re.compile(r"^module_[0-9]{3}$")
SEMVER_RE = re.compile(r"^[0-9]+\.[0-9]+\.[0-9]+(?:[-+][0-9A-Za-z.-]+)?$")


@dataclass(frozen=True)
class PackageIssue:
    code: str
    severity: str
    message: str
    file: str = ""
    how_to_fix: str = ""


@dataclass
class ModulePackageReport:
    ok: bool
    package_name: str
    package_hash: str
    plugin_id: str = ""
    name: str = ""
    version: str = ""
    runner: str = ""
    file_count: int = 0
    total_size: int = 0
    is_update: bool = False
    files: list[str] = field(default_factory=list)
    added: list[str] = field(default_factory=list)
    changed: list[str] = field(default_factory=list)
    removed: list[str] = field(default_factory=list)
    issues: list[PackageIssue] = field(default_factory=list)
    content: dict[str, str] = field(default_factory=dict, repr=False)

    def public_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "package_name": self.package_name,
            "package_hash": self.package_hash,
            "plugin_id": self.plugin_id,
            "name": self.name,
            "version": self.version,
            "runner": self.runner,
            "file_count": self.file_count,
            "total_size": self.total_size,
            "is_update": self.is_update,
            "files": self.files,
            "added": self.added,
            "changed": self.changed,
            "removed": self.removed,
            "issues": [issue.__dict__ for issue in self.issues],
        }


class ModulePackageError(RuntimeError):
    def __init__(self, report: ModulePackageReport) -> None:
        super().__init__("Module package validation failed")
        self.report = report


def analyze_module_package(
    package_bytes: bytes,
    package_name: str = "module.zip",
    *,
    existing_content: dict[str, str] | None = None,
    existing_tool: dict[str, Any] | None = None,
) -> ModulePackageReport:
    package_hash = hashlib.sha256(package_bytes).hexdigest()
    issues: list[PackageIssue] = []
    content: dict[str, str] = {}
    total_size = 0

    if len(package_bytes) > MAX_PACKAGE_BYTES:
        issues.append(PackageIssue(
            "ZIP_TOO_LARGE",
            "error",
            f"Package is larger than {MAX_PACKAGE_BYTES // (1024 * 1024)} MB.",
            how_to_fix="Upload a smaller module package.",
        ))

    try:
        zf = zipfile.ZipFile(io.BytesIO(package_bytes))
    except zipfile.BadZipFile:
        report = ModulePackageReport(False, package_name, package_hash)
        report.issues.append(PackageIssue("ZIP_INVALID", "error", "Uploaded file is not a valid zip."))
        return report

    with zf:
        infos = [info for info in zf.infolist() if not info.is_dir()]
        if len(infos) > MAX_FILE_COUNT:
            issues.append(PackageIssue(
                "ZIP_TOO_MANY_FILES",
                "error",
                f"Package contains {len(infos)} files; the limit is {MAX_FILE_COUNT}.",
                how_to_fix="Remove generated files and keep only module source files.",
            ))

        normalized_names: set[str] = set()
        root = _common_root([info.filename for info in infos])

        for info in infos:
            raw_name = info.filename.replace("\\", "/")
            safe_name = _safe_member_name(raw_name, root)
            if safe_name is None:
                issues.append(PackageIssue(
                    "ZIP_UNSAFE_PATH",
                    "error",
                    "Package contains an unsafe path.",
                    file=raw_name,
                    how_to_fix="Remove absolute paths, drive letters, and '..' path segments.",
                ))
                continue

            lower_name = safe_name.lower()
            if lower_name in normalized_names:
                issues.append(PackageIssue(
                    "ZIP_CASE_COLLISION",
                    "error",
                    "Package contains duplicate file names that differ only by case.",
                    file=safe_name,
                    how_to_fix="Keep one canonical file name.",
                ))
                continue
            normalized_names.add(lower_name)

            suffix = PurePosixPath(safe_name).suffix.lower()
            if suffix in BLOCKED_SUFFIXES or suffix not in ALLOWED_SUFFIXES:
                issues.append(PackageIssue(
                    "ZIP_FILE_TYPE_BLOCKED",
                    "error",
                    "This file type is not allowed in module packages.",
                    file=safe_name,
                    how_to_fix="Keep only Python source, plugin.yaml, and documentation files.",
                ))
                continue

            total_size += int(info.file_size)
            if info.file_size > MAX_FILE_BYTES:
                issues.append(PackageIssue(
                    "ZIP_FILE_TOO_LARGE",
                    "error",
                    f"File is larger than {MAX_FILE_BYTES // 1024} KB.",
                    file=safe_name,
                    how_to_fix="Move large models or datasets to a managed asset store.",
                ))
                continue
            if info.compress_size and info.file_size / max(info.compress_size, 1) > MAX_COMPRESSION_RATIO:
                issues.append(PackageIssue(
                    "ZIP_SUSPICIOUS_COMPRESSION",
                    "error",
                    "File compression ratio is suspiciously high.",
                    file=safe_name,
                    how_to_fix="Rebuild the package without highly compressed generated files.",
                ))
                continue

            if suffix in {".py", ".yaml", ".yml", ".md", ".txt", ".html"}:
                try:
                    content[safe_name] = zf.read(info).decode("utf-8")
                except UnicodeDecodeError:
                    issues.append(PackageIssue(
                        "ZIP_TEXT_DECODE_FAILED",
                        "error",
                        "File is not valid UTF-8 text.",
                        file=safe_name,
                        how_to_fix="Save module source files as UTF-8.",
                    ))

    manifest_text = content.get("plugin.yaml") or content.get("plugin.yml")
    manifest: dict[str, Any] = {}
    if not manifest_text:
        issues.append(PackageIssue(
            "PLUGIN_MANIFEST_MISSING",
            "error",
            "Package must contain plugin.yaml.",
            how_to_fix="Add plugin.yaml at the package root.",
        ))
    else:
        try:
            data = yaml.safe_load(manifest_text) or {}
            if isinstance(data, dict):
                manifest = data
            else:
                issues.append(PackageIssue("PLUGIN_MANIFEST_INVALID", "error", "plugin.yaml must be a YAML object."))
        except Exception as exc:
            issues.append(PackageIssue("PLUGIN_MANIFEST_INVALID", "error", f"plugin.yaml could not be parsed: {exc}"))

    plugin_id = str(manifest.get("id", "")).strip()
    version = str(manifest.get("version", "")).strip()
    name = str(manifest.get("name", plugin_id)).strip()
    runner = str(manifest.get("runner", "")).strip() or "cv_framework"

    if not MODULE_ID_RE.match(plugin_id):
        issues.append(PackageIssue(
            "PLUGIN_ID_INVALID",
            "error",
            "Module id must match module_NNN.",
            file="plugin.yaml",
            how_to_fix="Use an id such as module_012.",
        ))
    if not SEMVER_RE.match(version):
        issues.append(PackageIssue(
            "VERSION_INVALID",
            "error",
            "Module version must be semantic versioning, such as 1.2.3.",
            file="plugin.yaml",
            how_to_fix="Update plugin.yaml version.",
        ))
    if runner != "cv_framework":
        issues.append(PackageIssue(
            "RUNNER_UNSUPPORTED",
            "error",
            "Zip import currently supports runner: cv_framework only.",
            file="plugin.yaml",
            how_to_fix="Set runner: cv_framework or import this module through a custom reviewed path.",
        ))

    if MODULE_ID_RE.match(plugin_id):
        short_id = plugin_id.removeprefix("module_")
        required = ["plugin.yaml", f"{short_id}_input.py", f"{short_id}_process.py", f"{short_id}_output.py"]
        for filename in required:
            if filename not in content:
                issues.append(PackageIssue(
                    "MODULE_REQUIRED_FILE_MISSING",
                    "error",
                    f"Required file is missing: {filename}.",
                    file=filename,
                    how_to_fix="Add the required layer file with a name matching the module id.",
                ))
        for filename, source in content.items():
            if filename.endswith(".py"):
                issues.extend(_scan_python_source(filename, source, process_file=f"{short_id}_process.py"))

    existing_map = existing_content or {}
    current_names = set(content)
    existing_names = set(existing_map)
    added = sorted(current_names - existing_names)
    removed = sorted(existing_names - current_names)
    changed = sorted(name for name in current_names & existing_names if content[name] != existing_map[name])

    report = ModulePackageReport(
        ok=not any(issue.severity == "error" for issue in issues),
        package_name=package_name,
        package_hash=package_hash,
        plugin_id=plugin_id,
        name=name,
        version=version,
        runner=runner,
        file_count=len(content),
        total_size=total_size,
        is_update=existing_tool is not None,
        files=sorted(content),
        added=added,
        changed=changed,
        removed=removed,
        issues=issues,
        content=content,
    )
    return report


def _common_root(names: list[str]) -> str:
    parts = []
    for name in names:
        cleaned = name.replace("\\", "/").strip("/")
        if "/" in cleaned:
            parts.append(cleaned.split("/", 1)[0])
        else:
            return ""
    return parts[0] if parts and all(part == parts[0] for part in parts) else ""


def _safe_member_name(raw_name: str, root: str) -> str | None:
    if raw_name.startswith("/") or raw_name.startswith("\\"):
        return None
    if re.match(r"^[A-Za-z]:", raw_name) or raw_name.startswith("//"):
        return None
    path = PurePosixPath(raw_name)
    if any(part in {"", ".", ".."} for part in path.parts):
        return None
    if root and path.parts and path.parts[0] == root:
        path = PurePosixPath(*path.parts[1:])
    if len(path.parts) != 1:
        return None
    return path.as_posix()


def _scan_python_source(filename: str, source: str, *, process_file: str) -> list[PackageIssue]:
    issues: list[PackageIssue] = []
    try:
        tree = ast.parse(source, filename=filename)
    except SyntaxError as exc:
        return [PackageIssue(
            "PYTHON_SYNTAX_ERROR",
            "error",
            f"Python syntax error: {exc.msg}.",
            file=filename,
            how_to_fix="Fix the syntax error before importing.",
        )]

    blocked_imports = {"subprocess", "socket"}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                root = alias.name.split(".", 1)[0]
                if root in blocked_imports:
                    issues.append(PackageIssue(
                        "PYTHON_IMPORT_BLOCKED",
                        "error",
                        f"Importing {root} is not allowed in uploaded modules.",
                        file=filename,
                        how_to_fix="Move this behavior to a reviewed platform service.",
                    ))
                if filename == process_file and root == "streamlit":
                    issues.append(PackageIssue(
                        "PROCESS_IMPORTS_STREAMLIT",
                        "error",
                        "Process layer must not import Streamlit.",
                        file=filename,
                        how_to_fix="Move UI code to the input or output layer.",
                    ))
        elif isinstance(node, ast.ImportFrom):
            root = (node.module or "").split(".", 1)[0]
            if root in blocked_imports:
                issues.append(PackageIssue(
                    "PYTHON_IMPORT_BLOCKED",
                    "error",
                    f"Importing {root} is not allowed in uploaded modules.",
                    file=filename,
                    how_to_fix="Move this behavior to a reviewed platform service.",
                ))
            if filename == process_file and root == "streamlit":
                issues.append(PackageIssue(
                    "PROCESS_IMPORTS_STREAMLIT",
                    "error",
                    "Process layer must not import Streamlit.",
                    file=filename,
                    how_to_fix="Move UI code to the input or output layer.",
                ))
        elif isinstance(node, ast.Call):
            call_name = _call_name(node.func)
            if call_name in {"eval", "exec", "compile", "__import__", "os.system"}:
                issues.append(PackageIssue(
                    "PYTHON_CALL_BLOCKED",
                    "error",
                    f"Calling {call_name} is not allowed in uploaded modules.",
                    file=filename,
                    how_to_fix="Remove dynamic code execution and shell calls.",
                ))
    return issues


def _call_name(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name):
        return f"{node.value.id}.{node.attr}"
    return ""
