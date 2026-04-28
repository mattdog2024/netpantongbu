# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec for GitHub Actions CI build
from PyInstaller.utils.hooks import collect_submodules

block_cipher = None

a = Analysis(
    ['main.py'],
    pathex=['.'],
    binaries=[],
    datas=[
        ('assets/icon.ico', 'assets'),
    ],
    hiddenimports=[
        'PyQt5', 'PyQt5.QtCore', 'PyQt5.QtGui', 'PyQt5.QtWidgets',
        'PyQt5.QtNetwork', 'PyQt5.QtWebEngineWidgets',
        'PyQt5.QtWebEngineCore', 'PyQt5.QtWebChannel',
        'requests', 'urllib3', 'certifi', 'charset_normalizer',
        'idna', 'pickle', 'json', 'threading', 'datetime', 'schedule',
        'gui', 'gui.main_window', 'gui.file_browser', 'gui.task_panel',
        'gui.schedule_panel', 'gui.login_widget',
        'core', 'core.baidu_api', 'core.download_manager', 'core.login_server',
    ],
    hookspath=[],
    runtime_hooks=[],
    excludes=['matplotlib', 'numpy', 'pandas', 'scipy', 'tkinter', 'PIL'],
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz, a.scripts, a.binaries, a.zipfiles, a.datas, [],
    name='BaiduPanScheduler',
    debug=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    icon='assets/icon.ico',
)
