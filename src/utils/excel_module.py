import datetime

from openpyxl import load_workbook, Workbook
import os
from core.common.enums import Channel, Direction


def get_or_create_excel(dir_name, file_name, mode, chanel, direction, spacing=True):
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
        if not os.path.exists(dir_name):
            os.makedirs(dir_name)

        file_path = os.path.join(dir_name, file_name)

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

        worksheet = workbook.active
        return worksheet, workbook, file_path

    except Exception as e:
        print(f"Ошибка при работе с файлом {file_path}: {e}")
        return None