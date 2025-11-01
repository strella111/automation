"""
Модуль для централизованного управления настройками приложения.
Настройки сохраняются в директории проекта в формате INI.
"""
import os
import sys
from PyQt5 import QtCore
from pathlib import Path


def get_project_root():
    """
    Возвращает корневую директорию проекта или приложения.
    Настройки сохраняются в папке установки приложения.
    """
    if getattr(sys, 'frozen', False):
        # Приложение запущено из скомпилированного exe (PyInstaller)
        # sys.executable указывает на путь к exe файлу
        application_path = Path(sys.executable).parent
        return str(application_path)
    else:
        # Приложение запущено из исходников
        # Получаем путь к текущему файлу
        current_file = Path(__file__)
        # Поднимаемся на два уровня вверх (от src/config/ к корню)
        project_root = current_file.parent.parent.parent
        return str(project_root)


def get_settings_dir():
    """Возвращает директорию для хранения настроек"""
    settings_dir = os.path.join(get_project_root(), 'settings')
    # Создаем директорию, если её нет
    os.makedirs(settings_dir, exist_ok=True)
    return settings_dir


def get_settings(settings_name='main'):
    """
    Создает и возвращает объект QSettings для указанного файла настроек.
    
    Args:
        settings_name: Имя файла настроек (без расширения)
        
    Returns:
        QtCore.QSettings: Объект настроек
    """
    settings_path = os.path.join(get_settings_dir(), f'{settings_name}.ini')
    return QtCore.QSettings(settings_path, QtCore.QSettings.IniFormat)


def get_main_settings():
    """Возвращает основные настройки приложения"""
    return get_settings('main')


def get_ui_settings(widget_name):
    """
    Возвращает настройки UI для конкретного виджета.
    
    Args:
        widget_name: Имя виджета (например, 'phase_ma', 'check_ma')
        
    Returns:
        QtCore.QSettings: Объект настроек UI виджета
    """
    return get_settings(f'ui_{widget_name}')

