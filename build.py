#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Скрипт для автоматической сборки приложения

Использование:
    python build.py              # Сборка exe
    python build.py --installer  # Сборка exe + создание инсталлятора
    python build.py --clean      # Очистка временных файлов
"""

import os
import sys
import shutil
import subprocess
import argparse
from pathlib import Path

# Цвета для вывода в консоль
class Colors:
    HEADER = '\033[95m'
    OKBLUE = '\033[94m'
    OKCYAN = '\033[96m'
    OKGREEN = '\033[92m'
    WARNING = '\033[93m'
    FAIL = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'

def print_step(message):
    """Вывод заголовка этапа"""
    print(f"\n{Colors.HEADER}{Colors.BOLD}{'='*60}")
    print(f"  {message}")
    print(f"{'='*60}{Colors.ENDC}\n")

def print_success(message):
    """Вывод успешного сообщения"""
    print(f"{Colors.OKGREEN}✓ {message}{Colors.ENDC}")

def print_error(message):
    """Вывод сообщения об ошибке"""
    print(f"{Colors.FAIL}✗ {message}{Colors.ENDC}")

def print_warning(message):
    """Вывод предупреждения"""
    print(f"{Colors.WARNING}⚠ {message}{Colors.ENDC}")

def clean_build_files():
    """Очистка временных файлов сборки"""
    print_step("Очистка временных файлов")
    
    dirs_to_remove = ['build', 'dist', '__pycache__']
    files_to_remove = ['*.pyc', '*.pyo', '*.spec~']
    
    for dir_name in dirs_to_remove:
        if os.path.exists(dir_name):
            print(f"Удаление {dir_name}/...")
            shutil.rmtree(dir_name)
            print_success(f"Удалено: {dir_name}/")
    
    # Удаление .pyc файлов рекурсивно
    for root, dirs, files in os.walk('.'):
        for file in files:
            if file.endswith(('.pyc', '.pyo')):
                try:
                    os.remove(os.path.join(root, file))
                except Exception as e:
                    print_warning(f"Не удалось удалить {file}: {e}")
    
    print_success("Очистка завершена")

def check_requirements():
    """Проверка установленных зависимостей"""
    print_step("Проверка зависимостей")
    
    try:
        import PyInstaller
        print_success(f"PyInstaller установлен (версия {PyInstaller.__version__})")
    except ImportError:
        print_error("PyInstaller не установлен!")
        print("Установите: pip install pyinstaller")
        return False
    
    if not os.path.exists('requirements.txt'):
        print_warning("Файл requirements.txt не найден")
    else:
        print_success("Файл requirements.txt найден")
    
    if not os.path.exists('build.spec'):
        print_error("Файл build.spec не найден!")
        return False
    else:
        print_success("Файл build.spec найден")
    
    return True

def build_exe():
    """Сборка исполняемого файла"""
    print_step("Сборка исполняемого файла")
    
    cmd = ['pyinstaller', '--clean', '--noconfirm', 'build.spec']
    
    print(f"Выполнение команды: {' '.join(cmd)}")
    
    try:
        result = subprocess.run(cmd, check=True, capture_output=False, text=True)
        print_success("Сборка EXE завершена успешно!")
        return True
    except subprocess.CalledProcessError as e:
        print_error(f"Ошибка при сборке: {e}")
        return False

def create_distribution_folder():
    """Создание финальной папки с приложением"""
    print_step("Создание финальной структуры приложения")
    
    dist_folder = Path('dist/AutomationTool')
    
    # Создаем необходимые папки
    folders = ['settings', 'logs', 'data', 'config']
    for folder in folders:
        folder_path = dist_folder / folder
        folder_path.mkdir(parents=True, exist_ok=True)
        print_success(f"Создана папка: {folder}/")
    
    # Перемещаем EXE файл в папку AutomationTool (если он в dist/)
    exe_in_dist = Path('dist/AutomationTool.exe')
    exe_in_folder = dist_folder / 'AutomationTool.exe'
    if exe_in_dist.exists() and not exe_in_folder.exists():
        shutil.move(str(exe_in_dist), str(exe_in_folder))
        print_success("AutomationTool.exe перемещен в dist/AutomationTool/")
    elif exe_in_folder.exists():
        print_success("AutomationTool.exe уже в dist/AutomationTool/")
    else:
        print_warning("AutomationTool.exe не найден!")
    
    # Копируем конфигурационные файлы
    config_src = Path('src/config/coordinate_systems.json')
    if config_src.exists():
        shutil.copy(config_src, dist_folder / 'config' / 'coordinate_systems.json')
        print_success("Скопирован coordinate_systems.json")
    
    # Создаем README в settings
    readme_src = Path('settings/README.md')
    if readme_src.exists():
        shutil.copy(readme_src, dist_folder / 'settings' / 'README.md')
        print_success("Скопирован README.md в settings")
    
    # Создаем README для приложения
    app_readme = dist_folder / 'README.txt'
    with open(app_readme, 'w', encoding='utf-8') as f:
        f.write("""Automation Tool - Система автоматизации измерений

РАСПОЛОЖЕНИЕ ДАННЫХ
===================
Все данные (настройки, логи) хранятся в папке установки приложения.
По умолчанию: %LOCALAPPDATA%\\Automation Tool\\

СТРУКТУРА ПАПОК:
- settings/   - Настройки приложения (параметры устройств, UI настройки)
- logs/       - Логи работы приложения (ротируются автоматически)
- data/       - Данные измерений и калибровок
- config/     - Конфигурационные файлы (системы координат)

ЗАПУСК:
Запустите AutomationTool.exe

ПОРТАТИВНЫЙ РЕЖИМ:
Для переноса на другой ПК просто скопируйте всю папку с приложением.
Все настройки и данные сохранятся!

ВАЖНО:
При установке в Program Files могут потребоваться права администратора.
Рекомендуется использовать путь установки по умолчанию.

Разработчик: PULSAR
Дата сборки: """ + Path.cwd().name + "\n")
    
    print_success("Создан README.txt")
    
    # Очищаем лишние папки созданные PyInstaller в dist/
    # (settings, logs, config которые создались автоматически)
    extra_folders = [Path('dist/settings'), Path('dist/logs'), Path('dist/config')]
    for folder in extra_folders:
        if folder.exists():
            try:
                shutil.rmtree(folder)
                print(f"Удалена лишняя папка: {folder.name}/")
            except Exception as e:
                print_warning(f"Не удалось удалить {folder.name}/: {e}")
    
    print_success("Структура приложения создана")

def build_installer():
    """Создание инсталлятора с помощью Inno Setup"""
    print_step("Создание инсталлятора")
    
    # Проверяем наличие Inno Setup
    inno_paths = [
        r"C:\Program Files (x86)\Inno Setup 6\ISCC.exe",
        r"C:\Program Files\Inno Setup 6\ISCC.exe",
        r"C:\Program Files (x86)\Inno Setup 5\ISCC.exe",
        r"C:\Program Files\Inno Setup 5\ISCC.exe",
    ]
    
    iscc_path = None
    for path in inno_paths:
        if os.path.exists(path):
            iscc_path = path
            break
    
    if not iscc_path:
        print_warning("Inno Setup не найден!")
        print("Скачайте с: https://jrsoftware.org/isdl.php")
        print("После установки запустите: python build.py --installer")
        return False
    
    if not os.path.exists('setup.iss'):
        print_error("Файл setup.iss не найден!")
        return False
    
    # Проверяем наличие EXE файла
    exe_path = Path('dist/AutomationTool/AutomationTool.exe')
    if not exe_path.exists():
        print_error("AutomationTool.exe не найден в dist/AutomationTool/!")
        print("Сначала выполните сборку: python build.py")
        return False
    
    print(f"Используется Inno Setup: {iscc_path}")
    print_success(f"EXE файл найден: dist\\AutomationTool\\AutomationTool.exe")
    
    try:
        cmd = [iscc_path, 'setup.iss']
        subprocess.run(cmd, check=True)
        print_success("Инсталлятор создан успешно!")
        return True
    except subprocess.CalledProcessError as e:
        print_error(f"Ошибка при создании инсталлятора: {e}")
        return False

def main():
    parser = argparse.ArgumentParser(description='Сборка приложения Automation Tool')
    parser.add_argument('--clean', action='store_true', help='Только очистка временных файлов')
    parser.add_argument('--installer', action='store_true', help='Создать инсталлятор (требуется Inno Setup)')
    parser.add_argument('--no-clean', action='store_true', help='Не очищать временные файлы перед сборкой')
    
    args = parser.parse_args()
    
    print(f"{Colors.OKCYAN}{Colors.BOLD}")
    print("╔═══════════════════════════════════════════════════════════╗")
    print("║      Automation Tool - Система сборки приложения         ║")
    print("╚═══════════════════════════════════════════════════════════╝")
    print(f"{Colors.ENDC}")
    
    # Только очистка
    if args.clean:
        clean_build_files()
        return
    
    # Проверка зависимостей
    if not check_requirements():
        print_error("Проверка зависимостей не пройдена!")
        sys.exit(1)
    
    # Очистка перед сборкой
    if not args.no_clean:
        clean_build_files()
    
    # Сборка EXE
    if not build_exe():
        print_error("Сборка EXE не удалась!")
        sys.exit(1)
    
    # Создание структуры приложения
    create_distribution_folder()
    
    # Создание инсталлятора
    if args.installer:
        if build_installer():
            print_step("Готово!")
            print_success("Инсталлятор находится в папке: Output/")
        else:
            print_warning("Инсталлятор не создан, но EXE готов в папке: dist/AutomationTool/")
    else:
        print_step("Готово!")
        print_success("Приложение готово в папке: dist/AutomationTool/")
        print("\nДля создания инсталлятора запустите:")
        print("  python build.py --installer")
    
    print(f"\n{Colors.OKGREEN}{Colors.BOLD}Сборка завершена успешно!{Colors.ENDC}\n")

if __name__ == '__main__':
    main()

