import sys
from pathlib import Path
from loguru import logger

def setup_logging(log_file: str = "logs/app.log"):
    """
    Настройка логирования
    
    Args:
        log_file (str): Путь к файлу логов относительно корня проекта
    """
    log_path = Path(log_file)
    log_path.parent.mkdir(parents=True, exist_ok=True)

    logger.remove()

    logger.add(
        sys.stderr,
        format="{time:YYYY-MM-DD HH:mm:ss.SSS}\t{level}\t{message}",
        level="DEBUG"
    )

    logger.add(
        log_file,
        format="{time:YYYY-MM-DD HH:mm:ss.SSS}\t{level}\t{message}",
        level="DEBUG",
        retention="7 days",
        compression="zip"
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
    if device == 'PNA':
        data_str = str(data)
    elif isinstance(data, (bytes, bytearray)):
        data_str = ' '.join(f'{b:02X}' for b in data)
    else:
        data_str = str(data)
    return f"{device} {direction} {data_str}"