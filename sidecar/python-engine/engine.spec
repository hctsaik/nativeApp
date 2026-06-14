# -*- mode: python ; coding: utf-8 -*-

import os as _os
from pathlib import Path as _Path

from PyInstaller.utils.hooks import collect_submodules, copy_metadata

# streamlit reads its own version via importlib.metadata at import time
# (streamlit/version.py), so its .dist-info MUST be bundled or every Streamlit
# tool subprocess crashes in the frozen exe with
# "No package metadata was found for streamlit". recursive=True also covers
# streamlit's deps that do the same. (This was the real reason frozen tools had
# never actually launched end-to-end.)
_metadata_datas = copy_metadata('streamlit', recursive=True)

# Auto-collect every submodule of the platform core AND every plugin's domain,
# so a newly-added plugin (or new submodules in an existing one) never silently
# falls out of the bundle ("dev-green / package-dead"). Previously only the
# Labeling plugin was collected, which broke the "add a plugin without touching
# core/packaging" promise (R1 gap). The explicit list below is a safety net.
#
# NOTE (lean platform): this spec deliberately does NOT bundle plugin-specific
# heavy deps (torch for labeling, plotly/duckdb for AI4BI). The platform stays
# pure; each plugin lives in its own repo (AI4BI as a git submodule, Labeling as
# an external folder mounted at plugins/labeling) and owns its deps, which are
# installed into per-tool isolated venvs at runtime (see core/tool_deps.py, #7).
_auto_hidden = collect_submodules('core')
try:
    _spec_dir = _Path(SPECPATH)  # injected by PyInstaller in spec files
except NameError:  # pragma: no cover - defensive
    _spec_dir = _Path(_os.getcwd())
for _pdir in sorted((_spec_dir / 'plugins').glob('*')):
    if (_pdir / 'domain' / '__init__.py').exists():
        _auto_hidden += collect_submodules(f'plugins.{_pdir.name}.domain')


a = Analysis(
    ['engine.py'],
    pathex=[],
    binaries=[],
    datas=[
        ('tools',        'tools'),
        ('scripts',      'scripts'),
        ('plugins',      'plugins'),        # Labeling plugin home (annotation domain at plugins/labeling/domain)
        ('core',         'core'),
        ('config',       'config'),         # declarative seed + policy samples (seed.yaml / permissions / external_systems / sandbox)
        ('sheets',       'sheets'),
    ] + _metadata_datas,
    hiddenimports=[
        # management modules (static-seed, not auto-detected by PyInstaller)
        'management_insights',
        'management_oracle_store',
        'management_package_importer',
        'management_schema',
        'management_store',
        'management_use_cases',
        # annotation domain (imported by scripts/*.py data files at runtime)
        'plugins.labeling.domain',
        'plugins.labeling.domain.adapters',
        'plugins.labeling.domain.adapters.coco',
        'plugins.labeling.domain.adapters.common',
        'plugins.labeling.domain.adapters.isat',
        'plugins.labeling.domain.adapters.labeling_runtime',
        'plugins.labeling.domain.adapters.labelme',
        'plugins.labeling.domain.adapters.xanylabeling',
        'plugins.labeling.domain.adapters.xanylabeling_runtime',
        'plugins.labeling.domain.adapters.yolo_detection',
        'plugins.labeling.domain.adapters.yolo_segmentation',
        'plugins.labeling.domain.core',
        'plugins.labeling.domain.core.errors',
        'plugins.labeling.domain.core.models',
        'plugins.labeling.domain.core.states',
        'plugins.labeling.domain.core.validation',
        'plugins.labeling.domain.domains',
        'plugins.labeling.domain.domains.animal',
        'plugins.labeling.domain.domains.animal.schema_presets',
        'plugins.labeling.domain.formats',
        'plugins.labeling.domain.formats.builtins',
        'plugins.labeling.domain.formats.contracts',
        'plugins.labeling.domain.formats.registry',
        'plugins.labeling.domain.integrations',
        'plugins.labeling.domain.integrations.connectors',
        'plugins.labeling.domain.integrations.connectors.configurable_rest_connector',
        'plugins.labeling.domain.integrations.connectors.fake_connector',
        'plugins.labeling.domain.integrations.connectors.file_connector',
        'plugins.labeling.domain.integrations.connectors.rest_connector',
        'plugins.labeling.domain.integrations.contracts',
        'plugins.labeling.domain.integrations.profiles',
        'plugins.labeling.domain.integrations.registry',
        'plugins.labeling.domain.label_ops',
        'plugins.labeling.domain.services',
        'plugins.labeling.domain.storage',
        'plugins.labeling.domain.storage.artifacts',
        'plugins.labeling.domain.storage.ports',
        'plugins.labeling.domain.storage.sqlite_store',
        'plugins.labeling.domain.storage.workspace',
        'plugins.labeling.domain.tools',
        'plugins.labeling.domain.tools.builtins',
        'plugins.labeling.domain.tools.contracts',
        'plugins.labeling.domain.tools.registry',
        # platform core (canonical home for external-system integration contracts)
        'core',
        'core.forms',
        'core.output',
        'core.rbac',
        'core.sandbox',
        'core.guidance',
        'core.external_systems',
        'core.integrations',
        'core.integrations.connector',
        'core.integrations.tenant',
    ] + _auto_hidden,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
# tools.sqlite is a per-device derived cache rebuilt at first boot from the
# declarative sources (plugin.yaml + sheet YAML + config/seed.yaml). Never ship
# one inside the exe — a dev build machine may have left a stale config/*.sqlite.
a.datas = [d for d in a.datas if not d[0].lower().endswith('.sqlite')]

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='engine',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
