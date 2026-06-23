# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['src\\run.py'],
    pathex=[],
    binaries=[],
    datas=[],
    hiddenimports=['comtypes', 'comtypes.client', 'comtypes.gen', 'uiautomation', 'mss', 'mss.windows', 'pyautogui', 'pyautogui._pyautogui_win', 'pymsgbox', 'pyscreeze', 'PIL', 'PIL.Image'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['tkinter', 'unittest', 'email'],
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
    name='agent-eye',
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
