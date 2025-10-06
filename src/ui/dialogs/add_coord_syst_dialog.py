from PyQt5 import QtWidgets


class AddCoordinateSystemDialog(QtWidgets.QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle('Добавить систему координат')
        self.setModal(True)
        self.setFixedSize(350, 200)
        
        layout = QtWidgets.QVBoxLayout(self)
        layout.setSpacing(15)
        layout.setContentsMargins(20, 20, 20, 20)
        
        # Поля ввода
        form_layout = QtWidgets.QFormLayout()
        form_layout.setSpacing(10)
        
        self.name_edit = QtWidgets.QLineEdit()
        self.name_edit.setPlaceholderText('Введите название системы координат')
        form_layout.addRow('Название:', self.name_edit)
        
        self.x_offset_spinbox = QtWidgets.QDoubleSpinBox()
        self.x_offset_spinbox.setRange(-9999.0, 9999.0)
        self.x_offset_spinbox.setDecimals(2)
        self.x_offset_spinbox.setSuffix(' см')
        self.x_offset_spinbox.setValue(0.0)
        form_layout.addRow('Смещение X:', self.x_offset_spinbox)
        
        self.y_offset_spinbox = QtWidgets.QDoubleSpinBox()
        self.y_offset_spinbox.setRange(-9999.0, 9999.0)
        self.y_offset_spinbox.setDecimals(2)
        self.y_offset_spinbox.setSuffix(' см')
        self.y_offset_spinbox.setValue(0.0)
        form_layout.addRow('Смещение Y:', self.y_offset_spinbox)
        
        layout.addLayout(form_layout)
        
        # Кнопки
        buttons = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        
        # Валидация при изменении текста
        self.name_edit.textChanged.connect(self.validate_input)
        self.validate_input()
        
    def validate_input(self):
        """Проверяет корректность введенных данных"""
        name = self.name_edit.text().strip()
        ok_button = self.findChild(QtWidgets.QDialogButtonBox).button(QtWidgets.QDialogButtonBox.Ok)
        ok_button.setEnabled(len(name) > 0)
        
    def get_values(self):
        """Возвращает введенные значения"""
        return (
            self.name_edit.text().strip(),
            self.x_offset_spinbox.value(),
            self.y_offset_spinbox.value()
        )
