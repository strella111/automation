"""
Компонент для отображения логов в QTextEdit
"""
from PyQt5 import QtWidgets, QtCore
from PyQt5.QtGui import QTextCursor


class QTextEditLogHandler(QtCore.QObject):
    """Обработчик логов для QTextEdit с поддержкой фильтрации по уровню"""
    log_signal = QtCore.pyqtSignal(str, str)  # (message, level)

    def __init__(self, text_edit: QtWidgets.QTextEdit):
        super().__init__()
        self.text_edit = text_edit
        self.log_signal.connect(self.append_text)
        self.min_level = "DEBUG"  # Минимальный уровень логов для отображения
        
        # Иерархия уровней логов (от меньшего к большему)
        self.level_hierarchy = {
            "TRACE": 0,
            "DEBUG": 1,
            "INFO": 2,
            "SUCCESS": 3,
            "WARNING": 4,
            "ERROR": 5,
            "CRITICAL": 6
        }

    def write(self, message):
        """Метод для записи лога (вызывается loguru)"""
        # Извлекаем уровень из сообщения loguru
        level = self._extract_level(message)
        
        # Для INFO убираем информацию о модуле/функции/строке
        if level == "INFO":
            message = self._simplify_info_message(message)
        
        self.log_signal.emit(message, level)

    def _extract_level(self, message: str) -> str:
        """Извлекает уровень лога из сообщения"""
        # Формат loguru: "time | LEVEL | ..."
        try:
            parts = message.split("|")
            if len(parts) >= 2:
                level = parts[1].strip()
                return level
        except Exception:
            pass
        return "INFO"  # По умолчанию
    
    def _simplify_info_message(self, message: str) -> str:
        """Упрощает сообщение INFO, убирая модуль:функцию:строку"""
        # Формат: "time | INFO | module:function:line | message"
        # Результат: "time | INFO | message"
        try:
            parts = message.split("|", 3)  # Разделяем максимум на 4 части
            if len(parts) >= 4:
                # parts[0] = time, parts[1] = level, parts[2] = module:function:line, parts[3] = message
                time_part = parts[0].strip()
                level_part = parts[1].strip()
                message_part = parts[3].strip()
                return f"{time_part} | {level_part} | {message_part}\n"
        except Exception:
            pass
        return message

    def set_min_level(self, level: str):
        """Устанавливает минимальный уровень логов для отображения"""
        if level in self.level_hierarchy:
            self.min_level = level

    def should_display(self, level: str) -> bool:
        """Проверяет, должен ли лог отображаться"""
        msg_level_value = self.level_hierarchy.get(level, 0)
        min_level_value = self.level_hierarchy.get(self.min_level, 0)
        return msg_level_value >= min_level_value

    def flush(self):
        pass

    def append_text(self, message: str, level: str):
        """Добавляет текст в консоль, если уровень подходит"""
        if self.should_display(level):
            self.text_edit.moveCursor(QTextCursor.End)
            self.text_edit.insertPlainText(message)
            self.text_edit.moveCursor(QTextCursor.End)
