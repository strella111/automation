import sys
from pathlib import Path
from loguru import logger

def setup_logging(log_file: str = "logs/app.log"):
    """
    Настройка логирования с использованием loguru.
    
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
        format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>",
        level="INFO"
    )
    
    # Добавляем обработчик для записи в файл
    logger.add(
        log_file,
        format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} - {message}",
        level="DEBUG",
        rotation="1 day",    # Ротация логов каждый день
        retention="7 days",  # Хранить логи 7 дней
        compression="zip"    # Сжимать старые логи
    )
    
    logger.info("Логирование успешно настроено")
    return logger 