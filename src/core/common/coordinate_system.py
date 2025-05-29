import json
from pathlib import Path
from typing import List, Dict, Optional
from dataclasses import dataclass
from loguru import logger

@dataclass
class CoordinateSystem:
    name: str
    x_offset: float
    y_offset: float

class CoordinateSystemManager:
    def __init__(self, config_path: str = "config/coordinate_systems.json"):
        self.config_path = config_path
        self.systems: List[CoordinateSystem] = []
        self.load_systems()

    def load_systems(self) -> None:
        """Загружает системы координат из конфигурационного файла"""
        try:
            config_path = Path(self.config_path)
            if not config_path.exists():
                logger.warning(f"Файл конфигурации {self.config_path} не найден. Создаю новый.")
                self._create_default_config()
                return

            with open(config_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                self.systems = [
                    CoordinateSystem(
                        name=system['name'],
                        x_offset=float(system['x_offset']),
                        y_offset=float(system['y_offset'])
                    )
                    for system in data.get('coordinate_systems', [])
                ]
            logger.info(f"Загружено {len(self.systems)} систем координат")
        except Exception as e:
            logger.error(f"Ошибка при загрузке систем координат: {e}")
            self.systems = []

    def _create_default_config(self) -> None:
        """Создает конфигурационный файл с системой координат по умолчанию"""
        default_systems = {
            "coordinate_systems": [
                {
                    "name": "По умолчанию",
                    "x_offset": 0,
                    "y_offset": 0
                }
            ]
        }
        try:
            config_path = Path(self.config_path)
            config_path.parent.mkdir(parents=True, exist_ok=True)
            with open(config_path, 'w', encoding='utf-8') as f:
                json.dump(default_systems, f, indent=4, ensure_ascii=False)
            self.systems = [CoordinateSystem("По умолчанию", 0, 0)]
            logger.info("Создан конфигурационный файл с системой координат по умолчанию")
        except Exception as e:
            logger.error(f"Ошибка при создании конфигурационного файла: {e}")

    def get_system_names(self) -> List[str]:
        """Возвращает список названий систем координат"""
        return [system.name for system in self.systems]

    def get_system_by_name(self, name: str) -> Optional[CoordinateSystem]:
        """Возвращает систему координат по имени"""
        for system in self.systems:
            if system.name == name:
                return system
        return None 