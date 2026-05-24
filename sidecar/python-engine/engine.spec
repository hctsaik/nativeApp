# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['engine.py'],
    pathex=[],
    binaries=[],
    datas=[('tools', 'tools'), ('scripts', 'scripts')],
    hiddenimports=[
        'management_insights',
        'management_oracle_store',
        'management_package_importer',
        'management_schema',
        'management_store',
        'management_use_cases',
    ],
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
