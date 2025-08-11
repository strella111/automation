"""
Утилиты для работы с CSV файлами калибровки фазировки.
"""
import csv
import os
from pathlib import Path
from typing import List, Optional
from loguru import logger
from core.common.enums import Channel, Direction


class CalibrationCSV:
    """Класс для работы с CSV файлами калибровки фазировки"""
    
    def __init__(self, bu_address: int):
        """
        Инициализация для работы с CSV файлом калибровки
        
        Args:
            bu_address: Адрес БУ для формирования имени файла
        """
        self.bu_address = bu_address
        self.calbs_dir = Path("calbs")
        self.csv_file = self.calbs_dir / f"{bu_address}.csv"

        self.calbs_dir.mkdir(exist_ok=True)


        self.columns = [
            "Передатчик_Горизонтальная",
            "Передатчик_Вертикальная",
            "Приемник_Горизонтальная",
            "Приемник_Вертикальная"
        ]

        self._initialize_csv_if_needed()
    
    def _initialize_csv_if_needed(self):
        """Создает CSV файл с нулевыми значениями если файл не существует"""
        if not self.csv_file.exists():
            logger.info(f"Создание нового CSV файла: {self.csv_file}")
            

            data = []
            for ppm in range(1, 34):
                row = [0, 0, 0, 0]
                data.append(row)

            # Записываем в файл без заголовков
            with open(self.csv_file, 'w', newline='', encoding='utf-8') as f:
                writer = csv.writer(f, delimiter=';')
                writer.writerows(data)
            
            logger.info(f"CSV файл инициализирован с {len(data)} строками")

    def get_column_index(self, channel: Channel, direction: Direction) -> int:
        """
        Возвращает индекс столбца для заданной комбинации канал/поляризация

        Args:
            channel: Канал (передатчик/приемник)
            direction: Поляризация (вертикальная/горизонтальная)

        Returns:
            int: Индекс столбца (0-3)
        """
        channel_name = "Передатчик" if channel == Channel.Transmitter else "Приемник"
        direction_name = "Вертикальная" if direction == Direction.Vertical else "Горизонтальная"
        column_name = f"{channel_name}_{direction_name}"

        try:
            return self.columns.index(column_name)
        except ValueError:
            logger.error(f"Неизвестная комбинация канал/поляризация: {column_name}")
            return 0
    
    def save_phase_results(self, channel: Channel, direction: Direction, phase_results: List[int]):
        """
        Сохраняет результаты фазировки в соответствующий столбец CSV файла
        
        Args:
            channel: Канал (передатчик/приемник)
            direction: Поляризация (вертикальная/горизонтальная)
            phase_results: Список дискретов фазовращателей для 32 ППМ
        """
        if len(phase_results) != 32:
            logger.error(f"Ожидается 32 значения, получено {len(phase_results)}")
            return
        
        column_index = self.get_column_index(channel, direction)
        column_name = self.columns[column_index]
        
        logger.info(f"Сохранение результатов фазировки в столбец '{column_name}' файла {self.csv_file}")
        
        try:
            existing_data = []
            with open(self.csv_file, 'r', newline='', encoding='utf-8') as f:
                reader = csv.reader(f)
                for row in reader:
                    int_row = []
                    for i in range(4):
                        if i < len(row):
                            try:
                                int_row.append(int(row[i]))
                            except ValueError:
                                int_row.append(0)
                        else:
                            int_row.append(0)
                    existing_data.append(int_row)
            
            # Дополняем данными до 32 строк если нужно
            while len(existing_data) < 32:
                existing_data.append([0, 0, 0, 0])
            
            # Обновляем нужный столбец
            for ppm_index, phase_value in enumerate(phase_results):
                if ppm_index < len(existing_data):
                    existing_data[ppm_index][column_index] = phase_value

            with open(self.csv_file, 'w', newline='', encoding='utf-8') as f:
                writer = csv.writer(f, delimiter=';')
                writer.writerows(existing_data)
            
            logger.info(f"Результаты фазировки успешно сохранены в столбец '{column_name}'")
            
        except Exception as e:
            logger.error(f"Ошибка при сохранении результатов фазировки: {e}")
    
    def load_phase_results(self, channel: Channel, direction: Direction) -> Optional[List[int]]:
        """
        Загружает результаты фазировки из соответствующего столбца CSV файла
        
        Args:
            channel: Канал (передатчик/приемник)
            direction: Поляризация (вертикальная/горизонтальная)
            
        Returns:
            List[int]: Список дискретов фазовращателей для 32 ППМ или None при ошибке
        """
        column_index = self.get_column_index(channel, direction)
        column_name = self.columns[column_index]
        
        try:
            with open(self.csv_file, 'r', newline='', encoding='utf-8') as f:
                reader = csv.reader(f)
                
                phase_results = []
                for row_index, row in enumerate(reader):
                    if row_index >= 32:  # Только первые 32 ППМ
                        break
                    
                    if column_index < len(row):
                        try:
                            phase_results.append(int(row[column_index]))
                        except ValueError:
                            phase_results.append(0)
                    else:
                        phase_results.append(0)
                
                # Дополняем до 32 значений если нужно
                while len(phase_results) < 32:
                    phase_results.append(0)
                
                logger.info(f"Загружены результаты фазировки из столбца '{column_name}': {len(phase_results)} значений")
                return phase_results
                
        except Exception as e:
            logger.error(f"Ошибка при загрузке результатов фазировки: {e}")
            return None
    
    def get_file_path(self) -> Path:
        """Возвращает путь к CSV файлу"""
        return self.csv_file