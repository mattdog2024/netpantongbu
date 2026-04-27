# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec for GitHub Actions CI build
from PyInstaller.utils.hooks import collect_all, collect_submodules

block_cipher = None
datas_all = []
binaries_all = []
hiddenimports_all = []

for pkg in ['PyQt5.QtWebEngineWidgets', 'PyQt5.QtWebEngineCore']:
    try:
        d, b, h = collect_all(pkg)
        datas_all += d
        binaries_all += b
        hiddenimports_all += h
    except Exception:
        pass

a = Analysis(
    ['main.py'],
    pathex=['.'],
    binaries=binaries_all,
    datas=datas_all,
    hiddenimports=[
        'PyQt5', 'PyQt5.QtCore', 'PyQt5.QtGui', 'PyQt5.QtWidgets',
        'PyQt5.QtNetwork', 'PyQt5.QtWebEngineWidgets',
        'PyQt5.QtWebEngineCore', 'PyQt5.QtWebChannel',
        'requests', 'urllib3', 'certifi', 'charset_normalizer',
        'idna', 'pickle', 'json', 'threading', 'datetime', 'schedule',
    ] + hiddenimports_all + collect_submodules('PyQt5'),
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
    icon=None,
)
