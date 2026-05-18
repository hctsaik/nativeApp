from __future__ import annotations

from pathlib import Path

import pytest

from engine import ToolDefinition, _split_scripts


def _make_tool(script_path: Path) -> ToolDefinition:
    return ToolDefinition(
        tool_id="test-tool",
        name="Test",
        script_path=script_path,
        version="0.1.0",
    )


class TestSplitScripts:
    def test_falls_back_to_main_when_no_split_files(self, tmp_path: Path) -> None:
        script = tmp_path / "my_tool.py"
        script.touch()
        tool = _make_tool(script)
        input_s, output_s = _split_scripts(tool)
        assert input_s == script
        assert output_s == script

    def test_uses_split_files_when_both_exist(self, tmp_path: Path) -> None:
        (tmp_path / "my_tool.py").touch()
        inp = tmp_path / "my_tool_input.py"
        out = tmp_path / "my_tool_output.py"
        inp.touch()
        out.touch()
        tool = _make_tool(tmp_path / "my_tool.py")
        input_s, output_s = _split_scripts(tool)
        assert input_s == inp
        assert output_s == out

    def test_falls_back_when_only_input_exists(self, tmp_path: Path) -> None:
        script = tmp_path / "my_tool.py"
        script.touch()
        (tmp_path / "my_tool_input.py").touch()
        # output counterpart is missing → should fall back
        tool = _make_tool(script)
        input_s, output_s = _split_scripts(tool)
        assert input_s == script
        assert output_s == script

    def test_falls_back_when_only_output_exists(self, tmp_path: Path) -> None:
        script = tmp_path / "my_tool.py"
        script.touch()
        (tmp_path / "my_tool_output.py").touch()
        tool = _make_tool(script)
        input_s, output_s = _split_scripts(tool)
        assert input_s == script
        assert output_s == script

    def test_opencv_tool_uses_split_files(self) -> None:
        """Integration check: real opencv_tool split files exist on disk."""
        from engine import TOOLS_DIR
        tool = _make_tool(TOOLS_DIR / "opencv_tool.py")
        input_s, output_s = _split_scripts(tool)
        assert input_s.name == "opencv_tool_input.py"
        assert output_s.name == "opencv_tool_output.py"

    def test_animal_tagger_uses_split_files(self) -> None:
        """Integration check: real animal_tagger split files exist on disk."""
        from engine import TOOLS_DIR
        tool = _make_tool(TOOLS_DIR / "animal_tagger.py")
        input_s, output_s = _split_scripts(tool)
        assert input_s.name == "animal_tagger_input.py"
        assert output_s.name == "animal_tagger_output.py"
