from PyQt5 import QtWidgets, QtCore, QtGui
from .phase_ma_widget import PhaseMaWidget
from .check_ma_widget import CheckMaWidget
import serial.tools.list_ports
from loguru import logger

class SettingsDialog(QtWidgets.QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle('Настройки устройств')
        self.setModal(True)
        layout = QtWidgets.QVBoxLayout(self)

        # --- Настройки PNA ---
        pna_group = QtWidgets.QGroupBox('Настройки PNA')
        pna_layout = QtWidgets.QFormLayout(pna_group)
        self.pna_ip_edit = QtWidgets.QLineEdit()
        self.pna_port_edit = QtWidgets.QLineEdit()
        self.pna_mode_combo = QtWidgets.QComboBox()
        self.pna_mode_combo.addItems(['Реальный', 'Тестовый'])
        pna_layout.addRow('IP:', self.pna_ip_edit)
        pna_layout.addRow('Порт:', self.pna_port_edit)
        pna_layout.addRow('Режим:', self.pna_mode_combo)
        layout.addWidget(pna_group)

        # --- Настройки PSN ---
        psn_group = QtWidgets.QGroupBox('Настройки PSN')
        psn_layout = QtWidgets.QFormLayout(psn_group)
        self.psn_ip_edit = QtWidgets.QLineEdit()
        self.psn_port_edit = QtWidgets.QLineEdit()
        self.psn_mode_combo = QtWidgets.QComboBox()
        self.psn_mode_combo.addItems(['Реальный', 'Тестовый'])
        psn_layout.addRow('IP:', self.psn_ip_edit)
        psn_layout.addRow('Порт:', self.psn_port_edit)
        psn_layout.addRow('Режим:', self.psn_mode_combo)

        self.psn_speed_x = QtWidgets.QSpinBox(); self.psn_speed_x.setRange(-9999, 9999) 
        self.psn_speed_y = QtWidgets.QSpinBox(); self.psn_speed_y.setRange(-9999, 9999)
        self.psn_acc_x = QtWidgets.QSpinBox(); self.psn_acc_x.setRange(-9999, 9999)
        self.psn_acc_y = QtWidgets.QSpinBox(); self.psn_acc_y.setRange(-9999, 9999)
        psn_layout.addRow('Скорость X:', self.psn_speed_x)
        psn_layout.addRow('Скорость Y:', self.psn_speed_y)
        psn_layout.addRow('Ускорение X:', self.psn_acc_x)
        psn_layout.addRow('Ускорение Y:', self.psn_acc_y)
        layout.addWidget(psn_group)

        # --- Настройки MA ---
        ma_group = QtWidgets.QGroupBox('Настройки MA')
        ma_layout = QtWidgets.QFormLayout(ma_group)
        self.ma_com_combo = QtWidgets.QComboBox()
        self.update_com_ports_btn = QtWidgets.QPushButton('Обновить')
        self.update_com_ports_btn.clicked.connect(self.update_com_ports)
        com_port_layout = QtWidgets.QHBoxLayout()
        com_port_layout.addWidget(self.ma_com_combo)
        com_port_layout.addWidget(self.update_com_ports_btn)
        ma_layout.addRow('COM-порт:', com_port_layout)
        self.ma_mode_combo = QtWidgets.QComboBox()
        self.ma_mode_combo.addItems(['Реальный', 'Тестовый'])
        ma_layout.addRow('Режим:', self.ma_mode_combo)
        layout.addWidget(ma_group)


        # --- Кнопки ---
        btns = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel)
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        layout.addWidget(btns)

    def update_com_ports(self):
        """Обновляет список доступных COM портов (только реальные)"""
        current_port = self.ma_com_combo.currentText()
        self.ma_com_combo.clear()
        # Добавляем тестовый режим
        self.ma_com_combo.addItem('Тестовый')
        # Получаем список доступных портов
        filtered_ports = []
        for port in serial.tools.list_ports.comports():
            if any(x in port.device for x in ['usbserial', 'usbmodem', 'ttyUSB', 'ttyACM', 'wchusbserial', 'SLAB_USBtoUART', 'COM']):
                display = f"{port.device} ({port.description})"
                filtered_ports.append(display)
        self.ma_com_combo.addItems(filtered_ports)
        # Восстанавливаем предыдущий выбор, если возможно
        index = self.ma_com_combo.findText(current_port)
        if index >= 0:
            self.ma_com_combo.setCurrentIndex(index)
        else:
            self.ma_com_combo.setCurrentIndex(0)
        # Логировать только если список изменился
        if not hasattr(self, '_last_ports') or filtered_ports != self._last_ports:
            logger.debug(f'COM-порты для выбора: {filtered_ports}')
        self._last_ports = filtered_ports

    def get_settings(self):
        return {
            'pna_ip': self.pna_ip_edit.text(),
            'pna_port': self.pna_port_edit.text(),
            'psn_ip': self.psn_ip_edit.text(),
            'psn_port': self.psn_port_edit.text(),
            'psn_speed_x': self.psn_speed_x.value(),
            'psn_speed_y': self.psn_speed_y.value(),
            'psn_acc_x': self.psn_acc_x.value(),
            'psn_acc_y': self.psn_acc_y.value(),
            'ma_com_port': self.ma_com_combo.currentText(),
            'ma_mode': self.ma_mode_combo.currentIndex(),
            'pna_mode': self.pna_mode_combo.currentIndex(),
            'psn_mode': self.psn_mode_combo.currentIndex()
        }

class MainWindow(QtWidgets.QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle('DEV')
        self.resize(1400, 800)

        self.settings = QtCore.QSettings('PULSAR', 'PhaseMA')

        self.menu_bar = QtWidgets.QMenuBar(self)
        self.setMenuBar(self.menu_bar)
        self.menu_mode = self.menu_bar.addMenu('Режим')
        self.menu_utils = self.menu_bar.addMenu('Утилиты')
        self.menu_params = self.menu_bar.addMenu('Параметры')

        # --- Центральная область (режимы) ---
        self.central_widget = QtWidgets.QStackedWidget()
        self.setCentralWidget(self.central_widget)

        # --- Виджеты режимов ---
        self.phase_ma_widget = PhaseMaWidget()
        self.check_ma_widget = CheckMaWidget()
        self.central_widget.addWidget(self.phase_ma_widget)
        self.central_widget.addWidget(self.check_ma_widget)

        # --- Привязка меню ---
        self.phase_action = self.menu_mode.addAction('Фазировка МА')
        self.phase_action.setCheckable(True)
        self.phase_action.triggered.connect(self.show_phase_ma)
        
        self.check_action = self.menu_mode.addAction('Проверка МА')
        self.check_action.setCheckable(True)
        self.check_action.triggered.connect(self.show_check_ma)
        
        # Группа для взаимоисключающих действий
        mode_group = QtWidgets.QActionGroup(self)
        mode_group.addAction(self.phase_action)
        mode_group.addAction(self.check_action)
        mode_group.setExclusive(True)
        
        self.menu_params.addAction('Настройки устройств', self.open_settings_dialog)

        self.show_phase_ma()  # По умолчанию

        self.load_settings()
        
    def show_phase_ma(self):
        self.central_widget.setCurrentWidget(self.phase_ma_widget)
        self.phase_action.setChecked(True)

    def show_check_ma(self):
        self.central_widget.setCurrentWidget(self.check_ma_widget)
        self.check_action.setChecked(True)

    def open_settings_dialog(self):
        dlg = SettingsDialog(self)

        dlg.pna_ip_edit.setText(self.settings.value('pna_ip', ''))
        dlg.pna_port_edit.setText(self.settings.value('pna_port', ''))
        dlg.pna_mode_combo.setCurrentIndex(self.settings.value('pna_mode', 0))
        dlg.psn_ip_edit.setText(self.settings.value('psn_ip', ''))
        dlg.psn_port_edit.setText(self.settings.value('psn_port', ''))
        dlg.psn_mode_combo.setCurrentIndex(self.settings.value('psn_mode', 0))
        dlg.psn_speed_x.setValue(int(self.settings.value('psn_speed_x', 0)))
        dlg.psn_speed_y.setValue(int(self.settings.value('psn_speed_y', 0)))
        dlg.psn_acc_x.setValue(int(self.settings.value('psn_acc_x', 0)))
        dlg.psn_acc_y.setValue(int(self.settings.value('psn_acc_y', 0)))
        dlg.ma_com_combo.setCurrentText(self.settings.value('ma_com_port', ''))
        dlg.ma_mode_combo.setCurrentIndex(self.settings.value('ma_mode', 0))
        if dlg.exec_() == QtWidgets.QDialog.Accepted:
            settings = dlg.get_settings()
            for k, v in settings.items():
                self.settings.setValue(k, v)
            self.settings.sync()
            # Передаём параметры в оба виджета
            self.phase_ma_widget.set_device_settings(settings)
            self.check_ma_widget.set_device_settings(settings)

    def load_settings(self):
        # При запуске приложения сразу применяем параметры к обоим виджетам
        settings = {k: self.settings.value(k) for k in self.settings.allKeys()}
        self.phase_ma_widget.set_device_settings(settings)
        self.check_ma_widget.set_device_settings(settings)

if __name__ == '__main__':
    import sys
    app = QtWidgets.QApplication(sys.argv)
    win = MainWindow()
    win.show()
    sys.exit(app.exec_())
