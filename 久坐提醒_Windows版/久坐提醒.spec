# -*- mode: python ; coding: utf-8 -*-
# =====================================================================
# PyInstaller 打包规格（单文件 exe，无需目标机器安装 Python）
# 用法：
#   pyinstaller 久坐提醒.spec --noconfirm --clean
# 产物： dist/久坐提醒.exe
# =====================================================================
import os

block_cipher = None

a = Analysis(
    ['sit_reminder_windows.pyw'],
    pathex=[],
    binaries=[],
    datas=[],
    hiddenimports=[
        'tkinter',
        'tkinter.simpledialog',
        'tkinter.messagebox',
        'tkinter.filedialog',
        'tkinter.scrolledtext',
        'tkinter.ttk',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='久坐提醒',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,                 # 窗口程序，不弹黑框
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=os.path.join('.', 'app_icon.ico'),
    version='file_version_info.txt',
)
# 注意：此处不使用 COLLECT，因此为 --onefile 单文件模式。
