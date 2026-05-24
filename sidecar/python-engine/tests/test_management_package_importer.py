from __future__ import annotations

import io
import zipfile

from management_package_importer import analyze_module_package


def _zip(files: dict[str, str]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as zf:
        for name, source in files.items():
            zf.writestr(name, source)
    return buffer.getvalue()


def _valid_files() -> dict[str, str]:
    return {
        "module_012/plugin.yaml": "\n".join([
            "id: module_012",
            "name: Uploaded Module",
            "version: 1.2.3",
            "category: module",
            "runner: cv_framework",
        ]),
        "module_012/012_input.py": "def render_input():\n    return {}\n",
        "module_012/012_process.py": "def execute_logic(params):\n    return params\n",
        "module_012/012_output.py": "def render_output(result):\n    return None\n",
        "module_012/README.md": "# Uploaded Module\n",
    }


def test_analyze_module_package_accepts_valid_root_folder_zip() -> None:
    report = analyze_module_package(_zip(_valid_files()), "module_012.zip")

    assert report.ok is True
    assert report.plugin_id == "module_012"
    assert report.version == "1.2.3"
    assert sorted(report.content) == [
        "012_input.py",
        "012_output.py",
        "012_process.py",
        "README.md",
        "plugin.yaml",
    ]


def test_analyze_module_package_blocks_path_traversal() -> None:
    files = _valid_files()
    files["module_012/../evil.py"] = "print('bad')\n"

    report = analyze_module_package(_zip(files), "bad.zip")

    assert report.ok is False
    assert any(issue.code == "ZIP_UNSAFE_PATH" for issue in report.issues)


def test_analyze_module_package_blocks_process_streamlit() -> None:
    files = _valid_files()
    files["module_012/012_process.py"] = "import streamlit as st\ndef execute_logic(params): return params\n"

    report = analyze_module_package(_zip(files), "bad.zip")

    assert report.ok is False
    assert any(issue.code == "PROCESS_IMPORTS_STREAMLIT" for issue in report.issues)


def test_analyze_module_package_requires_semver() -> None:
    files = _valid_files()
    files["module_012/plugin.yaml"] = files["module_012/plugin.yaml"].replace("1.2.3", "draft")

    report = analyze_module_package(_zip(files), "bad.zip")

    assert report.ok is False
    assert any(issue.code == "VERSION_INVALID" for issue in report.issues)
