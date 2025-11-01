import datetime

from openpyxl import load_workbook, Workbook

import csv
import os
from pathlib import Path
import os
try:
    from PyQt5 import QtCore
    from config.settings_manager import get_main_settings
except Exception:
    QtCore = None
    get_main_settings = None
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
        # Определяем базовую директорию сохранения для режима phase
        base_dir = None
        try:
            if get_main_settings is not None:
                qsettings = get_main_settings()
                v = qsettings.value('base_save_dir')
                if v:
                    base_dir = str(v)
        except Exception:
            base_dir = None

        if base_dir:
            self.calbs_dir = Path(os.path.join(base_dir, 'phase'))
        else:
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
        """Создает CSV файл с нулевыми значениями если файл не существует
        
        Структура файла:
        - 17 блоков (ЛЗ 0-15 + резерв)
        - Каждый блок: 32 ППМ × 4 столбца = 128 строк
        - Итого: 17 × 128 = 2176 строк
        """
        if not self.csv_file.exists():
            logger.info(f"Создание нового CSV файла: {self.csv_file}")

            data = []
            # 17 блоков × 32 ППМ = 544 строки, каждая с 4 столбцами
            for block in range(17):  # ЛЗ 0-15 + резерв
                for ppm in range(32):  # 32 ППМ в каждом блоке
                    row = [0, 0, 0, 0]
                    data.append(row)

            with open(self.csv_file, 'w', newline='', encoding='utf-8') as f:
                writer = csv.writer(f, delimiter=';')
                writer.writerows(data)

            logger.info(f"CSV файл инициализирован с {len(data)} строками (17 блоков × 32 ППМ)")

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

    def save_phase_results(self, channel: Channel, direction: Direction, phase_results: List[int], 
                           delay_line_discretes: Optional[List[int]] = None):
        """
        Сохраняет результаты фазировки в соответствующий столбец CSV файла
        
        Файл содержит 17 блоков:
        - Блок 0 (ЛЗ=0): базовая калибровка ФВ
        - Блоки 1-15 (ЛЗ=1-15): базовая калибровка + дискреты ЛЗ
        - Блок 16: резерв (нули)

        Args:
            channel: Канал (передатчик/приемник)
            direction: Поляризация (вертикальная/горизонтальная)
            phase_results: Список дискретов фазовращателей для 32 ППМ (базовая калибровка)
            delay_line_discretes: Список из 16 значений дискретов для ЛЗ 0-15 
                                 (если None - копируем базовую калибровку во все блоки)
        """
        if len(phase_results) != 32:
            logger.error(f"Ожидается 32 значения, получено {len(phase_results)}")
            return

        column_index = self.get_column_index(channel, direction)
        column_name = self.columns[column_index]

        logger.info(f"Сохранение результатов фазировки в столбец '{column_name}' файла {self.csv_file}")
        if delay_line_discretes:
            logger.info(f"Фазировка ЛЗ включена, сохранение 17 блоков с коррекцией ЛЗ")
        else:
            logger.info(f"Фазировка ЛЗ выключена, копирование базовой калибровки во все блоки")

        try:
            # Читаем существующие данные (2176 строк)
            existing_data = []
            try:
                with open(self.csv_file, 'r', newline='', encoding='utf-8') as f:
                    reader = csv.reader(f, delimiter=';')
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
            except FileNotFoundError:
                pass

            # Убеждаемся что есть 17 блоков × 32 ППМ = 544 строки
            while len(existing_data) < 544:
                existing_data.append([0, 0, 0, 0])

            # Блок 0 (ЛЗ=0): ВСЕГДА обновляем базовую калибровку
            for ppm_index in range(32):
                row_index = ppm_index
                existing_data[row_index][column_index] = phase_results[ppm_index]
            
            # Блоки 1-16: обновляем ТОЛЬКО если есть данные ЛЗ
            if delay_line_discretes and len(delay_line_discretes) == 16:
                for block in range(1, 17):
                    for ppm_index in range(32):
                        row_index = block * 32 + ppm_index
                        
                        if block <= 15:
                            # Блоки 1-15 (ЛЗ=1-15): базовая калибровка + дискреты ЛЗ
                            # block 1 -> ЛЗ=1 -> delay_line_discretes[1]
                            value = phase_results[ppm_index] + delay_line_discretes[block]
                            # Ограничиваем диапазон 0-63
                            value = max(0, min(63, value))
                            existing_data[row_index][column_index] = value
                        else:
                            # Блок 16: резерв - нули
                            existing_data[row_index][column_index] = 0

            # Записываем обратно в файл
            with open(self.csv_file, 'w', newline='', encoding='utf-8') as f:
                writer = csv.writer(f, delimiter=';')
                writer.writerows(existing_data)

            logger.info(f"Результаты фазировки успешно сохранены в столбец '{column_name}' (17 блоков)")

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

def get_or_create_excel_for_check(base_dir, dir_name, file_name, mode, chanel, direction, spacing=True):
    """
    Проверяет существование Excel файла.
    Если файл существует - открывает и возвращает его.
    Если файл не существует - создает новый и возвращает его.

    Args:
        file_path (str): Путь к Excel файлу

    Returns:
        openpyxl.Workbook: Объект рабочей книги Excel
    """
    try:

        eff_dir = os.path.join(base_dir, dir_name)

        if not os.path.exists(eff_dir):
            os.makedirs(eff_dir)

        file_path = os.path.join(eff_dir, file_name)

        if os.path.exists(file_path):
            workbook = load_workbook(file_path)

        else:
            workbook = Workbook()
            workbook.save(file_path)

        if mode == 'check':
            sheet_name = ''
            if chanel == Channel.Receiver and direction == Direction.Horizontal:
                sheet_name = 'ПРМГ'
            elif chanel == Channel.Receiver and direction == Direction.Vertical:
                sheet_name = 'ПРМВ'
            elif chanel == Channel.Transmitter and direction == Direction.Horizontal:
                sheet_name = 'ПРДГ'
            elif chanel == Channel.Transmitter and direction == Direction.Vertical:
                sheet_name = 'ПРДВ'
            if sheet_name in workbook.sheetnames:
                worksheet = workbook[sheet_name]
            else:
                worksheet = workbook.create_sheet(sheet_name)

            if spacing:
                worksheet.insert_rows(idx=1, amount=42)
            worksheet.cell(1, 1).value = 'DateTime'
            worksheet.cell(1, 2).value = datetime.datetime.now().strftime('%d.%m.%Y %H:%M')
            row = ["Номер ППМ",
                   "Статус",
                   "Амплитуда_abs",
                   "Амплитуда_delta",
                   "Фаза",
                   "Дельта ФВ",
                   "Факт. значение 5.625",
                   "Факт. значение 11.25",
                   "Факт. значение 22.5",
                   "Факт. значение 45",
                   "Факт. значение 90",
                   "Факт. значение 180"]
            for i, value in enumerate(row):
                worksheet.cell(row=2, column=i + 1).value = value

            return worksheet, workbook, file_path
        elif mode == 'stend':
            sheet_name = ''
            if chanel == Channel.Receiver and direction == Direction.Horizontal:
                sheet_name = 'ПРМГ'
            elif chanel == Channel.Receiver and direction == Direction.Vertical:
                sheet_name = 'ПРМВ'
            elif chanel == Channel.Transmitter and direction == Direction.Horizontal:
                sheet_name = 'ПРДГ'
            elif chanel == Channel.Transmitter and direction == Direction.Vertical:
                sheet_name = 'ПРДВ'
            if sheet_name in workbook.sheetnames:
                worksheet = workbook[sheet_name]
            else:
                worksheet = workbook.create_sheet(sheet_name)

            if spacing:
                worksheet.insert_rows(idx=1, amount=42)
            worksheet.cell(1, 1).value = 'DateTime'
            worksheet.cell(1, 2).value = datetime.datetime.now().strftime('%d.%m.%Y %H:%M')
            row = ["Номер ППМ",
                   "0 Амп.",
                   "0 Фаза",
                   "5.625 Амп.",
                   "5.625 Фаза",
                   "11.25 Амп.",
                   "11.25 Фаза",
                   "22.5 Амп.",
                   "22.5 Фаза",
                   "45 Амп.",
                   "45 Фаза",
                   "90 Амп.",
                   "90 Фаза",
                   "180 Амп.",
                   "180 Фаза"]
            for i, value in enumerate(row):
                worksheet.cell(row=2, column=i + 1).value = value

            return worksheet, workbook, file_path

        worksheet = workbook.active
        return worksheet, workbook, file_path


    except Exception as e:
        print(f"Ошибка при работе с файлом {file_path}: {e}")
        return None
