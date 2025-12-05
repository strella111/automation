import sys
from pathlib import Path
from loguru import logger

def get_app_root():
    """
    Получает корневую директорию приложения.
    Логи сохраняются в папке установки приложения.
    """
    if getattr(sys, 'frozen', False):
        # Запущено из exe
        return Path(sys.executable).parent
    else:
        # Запущено из исходников
        return Path(__file__).parent.parent.parent

def setup_logging(log_file: str = "logs/app.log", rotation_size: str = "10 MB"):
    """
    Настройка логирования
    
    Args:
        log_file (str): Путь к файлу логов относительно корня проекта
        rotation_size (str): Размер файла для ротации (например, "10 MB", "1 GB")
    """
    # Определяем абсолютный путь к логам
    app_root = get_app_root()
    log_path = app_root / log_file
    log_path.parent.mkdir(parents=True, exist_ok=True)

    logger.remove()

    # Добавляем вывод в консоль только если она доступна (не в скомпилированном GUI)
    if sys.stdout is not None:
        logger.add(
            sys.stdout,
            format="{time:YYYY-MM-DD HH:mm:ss.SSS} | {level} | {name}:{function}:{line} | {message}",
            level="DEBUG"
        )

    # Добавляем вывод в файл
    logger.add(
        str(log_path),
        format="{time:YYYY-MM-DD HH:mm:ss.SSS} | {level} | {name}:{function}:{line} | {message}",
        level="DEBUG",
        rotation=rotation_size,
        retention="7 days", 
        compression="zip", 
        encoding="utf-8"
    )
    
    logger.info(f"Логирование успешно настроено. Файл логов: {log_path}")
    return logger 

def format_device_log(device: str, direction: str, data) -> str:
    """
    Форматирует лог обмена с устройством.
    device: 'MA', 'PSN', 'PNA'
    direction: '>>' (отправка) или '<<' (приём)
    data: str или bytes
    """
    if device == 'PNA':
        data_str = str(data)
    elif isinstance(data, (bytes, bytearray)):
        data_str = ' '.join(f'{b:02X}' for b in data)
    else:
        data_str = str(data)
    return f"{device} {direction} {data_str}"