# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_all

datas = [('D:\\vscode\\Kuro\\core', 'core'), ('D:\\vscode\\Kuro\\tools', 'tools'), ('D:\\vscode\\Kuro\\integrations', 'integrations'), ('D:\\vscode\\Kuro\\assets', 'assets')]
binaries = []
hiddenimports = ['ctypes', 'cryptography', 'edge_tts', 'pygame', 'speech_recognition', 'rich', 'rich._unicode_data']

tmp_ret_rich = collect_all('rich')
datas += tmp_ret_rich[0]
binaries += tmp_ret_rich[1]
hiddenimports += tmp_ret_rich[2]

tmp_ret_pt = collect_all('prompt_toolkit')
datas += tmp_ret_pt[0]
binaries += tmp_ret_pt[1]
hiddenimports += tmp_ret_pt[2]

a = Analysis(
    ['D:\\vscode\\Kuro\\main.py'],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
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
    [],
    exclude_binaries=True,
    name='KURO',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=['D:\\vscode\\Kuro\\assets\\kuro_icon.ico'],
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='KURO',
)
