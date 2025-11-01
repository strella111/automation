# -*- mode: python ; coding: utf-8 -*-
"""
Спецификация для PyInstaller
Компилирует приложение в единый исполняемый файл
"""

import os
from PyInstaller.utils.hooks import collect_data_files, collect_submodules

block_cipher = None

# Пути
src_path = os.path.join(os.getcwd(), 'src')

# Собираем все данные из пакетов
datas = []
datas += collect_data_files('pyqtgraph')

# Добавляем конфигурационные файлы
datas += [(os.path.join(src_path, 'config', 'coordinate_systems.json'), 'config')]

# Добавляем иконку (PNG для окна приложения)
import os
if os.path.exists('icon/Logo.png'):
    datas += [('icon/Logo.png', 'icon')]
if os.path.exists('icon/Logo.ico'):
    datas += [('icon/Logo.ico', 'icon')]

# Собираем скрытые импорты
hiddenimports = []
hiddenimports += collect_submodules('pyqtgraph')
hiddenimports += collect_submodules('openpyxl')
hiddenimports += collect_submodules('pyvisa')
hiddenimports += collect_submodules('pyvisa_py')
hiddenimports += collect_submodules('serial')
hiddenimports += [
    'numpy',
    'PyQt5.QtCore',
    'PyQt5.QtGui',
    'PyQt5.QtWidgets',
    'loguru',
    'openpyxl.cell._writer',
]

a = Analysis(
    [os.path.join(src_path, 'main.py')],
    pathex=[src_path],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'matplotlib',
        'PIL',
        'tkinter',
        '_tkinter',
        'pandas',
        'scipy',
        'pytest',
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='AutomationTool',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,  # Без консоли для GUI приложения
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='icon/Logo.ico' if os.path.exists('icon/Logo.ico') else None,  # Иконка EXE (требует ICO!)
)

