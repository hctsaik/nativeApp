# -*- mode: python ; coding: utf-8 -*-

from PyInstaller.utils.hooks import collect_submodules

# Auto-collect every submodule of the platform core and the Labeling plugin
# domain, so newly-added submodules never silently fall out of the bundle
# ("dev-green / package-dead"). The explicit list below is kept as a safety net.
_auto_hidden = collect_submodules('core') + collect_submodules('plugins.labeling.domain')


a = Analysis(
    ['engine.py'],
    pathex=[],
    binaries=[],
    datas=[
        ('tools',        'tools'),
        ('scripts',      'scripts'),
        ('plugins',      'plugins'),        # Labeling plugin home (annotation domain at plugins/labeling/domain)
        ('core',         'core'),
        ('sheets',       'sheets'),
    ],
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
        'plugins.labeling.domain.integrations.connectors.fake_connector',
        'plugins.labeling.domain.integrations.connectors.file_connector',
        'plugins.labeling.domain.integrations.connectors.rest_connector',
        'plugins.labeling.domain.integrations.contracts',
        'plugins.labeling.domain.integrations.profiles',
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
