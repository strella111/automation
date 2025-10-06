"""
Компонент для отображения логов в QTextEdit
"""
from PyQt5 import QtWidgets, QtCore
from PyQt5.QtGui import QTextCursor


class QTextEditLogHandler(QtCore.QObject):
    """Обработчик логов для QTextEdit"""
    log_signal = QtCore.pyqtSignal(str)

    def __init__(self, text_edit: QtWidgets.QTextEdit):
        super().__init__()
        self.text_edit = text_edit
        self.log_signal.connect(self.append_text)

    def write(self, message):
        self.log_signal.emit(message)

    def flush(self):
        pass

    def append_text(self, message):
        self.text_edit.moveCursor(QTextCursor.End)
        self.text_edit.insertPlainText(message)
        self.text_edit.moveCursor(QTextCursor.End)
