# Phase 3 — ToolRegistry Spec

## Objective

Replace the `if/elif` dispatch in `labeling_runtime.py` with a pluggable
`ToolRegistry`. Fix the known `_launch_labelme` backslash bug. Consolidate the
two WDAC bypass implementations into one. Add a unified `launch_tool` alias for
module_012. Preserve all existing module_006/012 compatibility fields.

## Requires

Phase 1 complete. (ToolRegistry is independent of FormatRegistry, but Phase 1
confirms the registry pattern works before applying it to tools.)

## Files to Create

```
annotation/tools/__init__.py
annotation/tools/contracts.py
annotation/tools/registry.py
annotation/tools/builtins.py
```

## Files to Modify

```
annotation/adapters/labeling_runtime.py         — dispatch via ToolRegistry
annotation/adapters/xanylabeling_runtime.py     — consolidate WDAC bypass
annotation/services.py                          — prepare_labeling_project uses registry
sidecar/python-engine/scripts/module_012/012_output.py  — fix backslash bug; add launch_tool alias
sidecar/python-engine/scripts/module_006/       — use ToolRegistry; preserve legacy fields
```

## Contracts (`contracts.py`)

```python
@dataclass
class RuntimeStatus:
    available: bool
    executable: str
    version: str | None     # None for labelme/isat (no version detection currently)
    message: str

@dataclass
class ToolDescriptor:
    tool_id: str            # "x-anylabeling" | "labelme" | "isat"
    display_name: str
    default_output_format: str      # format_id for the tool's native file format
    supports_project_mode: bool     # True: xany, labelme; False: isat
    supports_file_mode: bool        # True for all three
    aliases: list[str]

class LabelingToolAdapter(Protocol):
    def detect(self, executable_override: str | None = None) -> RuntimeStatus: ...
    def launch_project(self, project_dir: Path, options: dict) -> None: ...
    def launch_file(self, file_path: str, options: dict) -> str | None:
        """Returns error message string, or None on success."""
    def get_executable(self, executable_override: str | None = None) -> str: ...
```

## Registry (`registry.py`)

```python
class ToolRegistry:
    def register(self, descriptor: ToolDescriptor, adapter: LabelingToolAdapter) -> None: ...
    def get(self, tool_id: str) -> tuple[ToolDescriptor, LabelingToolAdapter]:
        """Normalises aliases. Raises ValueError on unknown tool."""
    def list_supported(self) -> list[dict]: ...
    def normalize(self, tool_id: str) -> str: ...

def get_tool_registry() -> ToolRegistry: ...
```

## Builtins (`builtins.py`)

| tool_id | aliases | supports_project_mode | default_output_format |
|---|---|---|---|
| `x-anylabeling` | `xanylabeling`, `x_anylabeling` | True | `x-anylabeling` |
| `labelme` | `label-me` | True | `labelme` |
| `isat` | `isat-sam` | False | `isat` |

## WDAC Bypass Consolidation

Canonical implementation (in `x-anylabeling` adapter's `get_executable`):

```python
# 1. Find venv python.exe alongside xanylabeling scripts
# 2. Build command: [python_exe, "-c",
#    f"import sys; sys.path.insert(0, '{site_packages}'); from anylabeling.app import main; main()"]
# 3. Fallback: [xanylabeling_exe] directly
```

Rationale: the `sys.path.insert` form works even when the `.exe` trampoline is blocked
by WDAC, because it bypasses the trampoline entirely. The `-m anylabeling.app` form
(old `xanylabeling_runtime._command_prefix()`) requires `anylabeling` to be importable
from sys.path without explicit injection, which fails in some WDAC policies.

Old `_command_prefix()` in `xanylabeling_runtime.py` kept as fallback; new form tried
first.

## Bug Fix: `_launch_labelme()` Line 432

Current (broken):
```python
python_exe = exe_path.parent \ "python.exe"  # backslash = line continuation syntax error
```
Fixed:
```python
python_exe = exe_path.parent / "python.exe"
```

## Output Path Mode Distinction

ToolRegistry must distinguish two modes:

| Mode | Called by | Output dir |
|---|---|---|
| **Project mode** | `labeling_runtime.launch_labeling_project()`, module_006 | `project_dir/labels/` |
| **File mode** | `012_output._launch_*` | `Path(file_path).parent` |

`ToolDescriptor.supports_project_mode = False` for ISAT (ISAT does not accept file/dir
args; cwd is set to image directory as a hint only).

## module_006 Compatibility

`xany_dir` override path: `adapter.get_executable(executable_override=xany_dir)`
`legacy_mode` field: passed through `options={"legacy_mode": True}` to `launch_project`

## module_012 Unified Launch Alias

Add alongside existing three `_launch_*` functions:

```python
def _launch_tool(tool_id: str, file_path: str, exe_override: str | None = None) -> str | None:
    """Unified dispatch. Returns error string or None."""
    _, adapter = get_tool_registry().get(tool_id)
    return adapter.launch_file(file_path, {"executable_override": exe_override})
```

Existing `_launch_xany`, `_launch_labelme`, `_launch_isat` remain functional.
`_launch_tool` is an alias, not a replacement (module_009 still uses individual calls).

## Tests to Add

```
tests/annotation/test_tool_registry.py
    - test_register_and_get_by_id
    - test_get_by_alias_normalizes
    - test_unknown_tool_raises_value_error
    - test_isat_supports_project_mode_false
    - test_all_builtins_registered

tests/annotation/test_tool_launch.py
    - test_labelme_path_join_no_backslash   # regression for line 432 bug
    - test_wdac_bypass_uses_sys_path_insert
    - test_launch_file_vs_project_output_paths
```

## Acceptance Criteria

- [ ] `detect_labeling_tool("x-anylabeling")` returns equivalent result to pre-Phase-3
- [ ] `prepare_labeling_project("isat", ...)` dispatches via ToolRegistry
- [ ] `_launch_labelme()` backslash bug fixed (line 432 uses `/`)
- [ ] WDAC bypass: consolidated `sys.path.insert` form used first
- [ ] `_launch_tool(tool_id, file_path)` callable and dispatches correctly
- [ ] module_006 `xany_dir` override still works
- [ ] `npm run test:python` fully green
