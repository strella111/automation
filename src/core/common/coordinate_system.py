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
                    "name": "Аппаратная",
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
    
    def add_system(self, name: str, x_offset: float, y_offset: float) -> bool:
        """Добавляет новую систему координат"""
        # Проверяем, что такое имя еще не используется
        if any(system.name == name for system in self.systems):
            logger.error(f"Система координат с именем '{name}' уже существует")
            return False
        
        new_system = CoordinateSystem(name=name, x_offset=x_offset, y_offset=y_offset)
        self.systems.append(new_system)
        
        # Сохраняем в файл
        if self.save_systems():
            logger.info(f"Добавлена новая система координат: {name} (x={x_offset}, y={y_offset})")
            return True
        else:
            # Если сохранение не удалось, удаляем из списка
            self.systems.remove(new_system)
            return False
    
    def remove_system(self, name: str) -> bool:
        """Удаляет систему координат по имени"""
        # Нельзя удалить последнюю систему координат
        if len(self.systems) <= 1:
            logger.error("Нельзя удалить последнюю систему координат")
            return False
        
        # Ищем систему для удаления
        system_to_remove = None
        for system in self.systems:
            if system.name == name:
                system_to_remove = system
                break
        
        if system_to_remove is None:
            logger.error(f"Система координат с именем '{name}' не найдена")
            return False
        
        # Удаляем систему
        self.systems.remove(system_to_remove)
        
        # Сохраняем изменения
        if self.save_systems():
            logger.info(f"Система координат '{name}' успешно удалена")
            return True
        else:
            # Если сохранение не удалось, возвращаем систему обратно
            self.systems.append(system_to_remove)
            return False

    def save_systems(self) -> bool:
        """Сохраняет все системы координат в конфигурационный файл"""
        try:
            systems_data = {
                "coordinate_systems": [
                    {
                        "name": system.name,
                        "x_offset": system.x_offset,
                        "y_offset": system.y_offset
                    }
                    for system in self.systems
                ]
            }
            
            config_path = Path(self.config_path)
            config_path.parent.mkdir(parents=True, exist_ok=True)
            
            with open(config_path, 'w', encoding='utf-8') as f:
                json.dump(systems_data, f, indent=4, ensure_ascii=False)
            
            logger.info(f"Сохранено {len(self.systems)} систем координат в {self.config_path}")
            return True
        except Exception as e:
            logger.error(f"Ошибка при сохранении систем координат: {e}")
            return False 