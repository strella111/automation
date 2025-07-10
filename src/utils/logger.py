import sys
from pathlib import Path
from loguru import logger

def setup_logging(log_file: str = "logs/app.log"):
    """
    Настройка логирования
    
    Args:
        log_file (str): Путь к файлу логов относительно корня проекта
    """
    # Создаем директорию для логов, если она не существует
    log_path = Path(log_file)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    
    # Удаляем стандартный обработчик
    logger.remove()
    
    # Добавляем обработчик для вывода в консоль
    logger.add(
        sys.stderr,
        format="{time:YYYY-MM-DD HH:mm:ss}\t{level}\t{message}",
        level="DEBUG"
    )
    
    # Добавляем обработчик для записи в файл
    logger.add(
        log_file,
        format="{time:YYYY-MM-DD HH:mm:ss}\t{level}\t{message}",
        level="DEBUG",
        rotation="1 day",    # Ротация логов каждый день
        retention="7 days",  # Хранить логи 7 дней
        compression="zip"    # Сжимать старые логи
    )
    
    logger.info("Логирование успешно настроено")
    return logger 

def format_device_log(device: str, direction: str, data) -> str:
    """
    Форматирует лог обмена с устройством.
    device: 'MA', 'PSN', 'PNA'
    direction: '>>' (отправка) или '<<' (приём)
    data: str или bytes
    """
    if isinstance(data, (bytes, bytearray)):
        data_str = ' '.join(f'{b:02X}' for b in data)
    else:
        data_str = str(data)
    return f"{device} {direction} {data_str}"