from PyQt5 import QtWidgets, QtCore, QtGui
from .phase_ma_widget import PhaseMaWidget
from .check_ma_widget import CheckMaWidget
from .check_stend_ma_widget import CheckStendMaWidget
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
        self.pna_files_path = QtWidgets.QLineEdit()
        self.pna_files_path.setPlaceholderText('C:\\Users\\Public\\Documents\\Network Analyzer\\')
        pna_layout.addRow('IP:', self.pna_ip_edit)
        pna_layout.addRow('Порт:', self.pna_port_edit)
        pna_layout.addRow('Режим:', self.pna_mode_combo)
        pna_layout.addRow('Путь к файлам:', self.pna_files_path)
        layout.addWidget(pna_group)

        # --- Настройки Генератора АКИП ---
        akip_group = QtWidgets.QGroupBox('Настройки генератора АКИП')
        akip_layout = QtWidgets.QFormLayout(akip_group)

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

        # Обновляем список COM портов сразу при создании диалога
        self.update_com_ports()

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
                # Показываем только имя порта без описания
                filtered_ports.append(port.device)
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
            'psn_mode': self.psn_mode_combo.currentIndex(),
            'pna_files_path': self.pna_files_path.text(),
        }

    def set_settings(self, settings):
        """Установка настроек в диалог"""
        if not settings:
            return
            
        self.pna_ip_edit.setText(settings.get('pna_ip', ''))
        self.pna_port_edit.setText(settings.get('pna_port', ''))
        self.pna_mode_combo.setCurrentIndex(int(settings.get('pna_mode', 0)))
        self.psn_ip_edit.setText(settings.get('psn_ip', ''))
        self.psn_port_edit.setText(settings.get('psn_port', ''))
        self.psn_mode_combo.setCurrentIndex(int(settings.get('psn_mode', 0)))
        self.psn_speed_x.setValue(int(settings.get('psn_speed_x', 10)))
        self.psn_speed_y.setValue(int(settings.get('psn_speed_y', 10)))
        self.psn_acc_x.setValue(int(settings.get('psn_acc_x', 5)))
        self.psn_acc_y.setValue(int(settings.get('psn_acc_y', 5)))
        self.ma_com_combo.setCurrentText(settings.get('ma_com_port', ''))
        self.ma_mode_combo.setCurrentIndex(int(settings.get('ma_mode', 0)))
        self.pna_files_path.setText(settings.get('pna_files_path', 'C:\\Users\\Public\\Documents\\Network Analyzer\\'))

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
        self.check_stend_ma_widget = CheckStendMaWidget()
        self.central_widget.addWidget(self.phase_ma_widget)
        self.central_widget.addWidget(self.check_ma_widget)
        self.central_widget.addWidget(self.check_stend_ma_widget)

        # --- Привязка меню ---
        self.phase_action = self.menu_mode.addAction('Фазировка МА в БЭК')
        self.phase_action.setCheckable(True)
        self.phase_action.triggered.connect(self.show_phase_ma)
        
        self.check_action = self.menu_mode.addAction('Проверка МА в БЭК')
        self.check_action.setCheckable(True)
        self.check_action.triggered.connect(self.show_check_ma)

        self.check_action = self.menu_mode.addAction('Проверка МА на стенде')
        self.check_action.setCheckable(True)
        self.check_action.triggered.connect(self.show_check_stend_ma)
        
        # Группа для взаимоисключающих действий
        mode_group = QtWidgets.QActionGroup(self)
        mode_group.addAction(self.phase_action)
        mode_group.addAction(self.check_action)
        mode_group.setExclusive(True)
        
        self.menu_params.addAction('Настройки устройств', self.open_settings_dialog)

        # Восстанавливаем состояние интерфейса
        self.restore_ui_state()
        
        # Загружаем настройки устройств
        self.load_settings()

    def restore_ui_state(self):
        """Восстанавливает состояние интерфейса"""
        # Восстанавливаем размер и позицию окна
        self.restoreGeometry(self.settings.value('window_geometry', b''))
        self.restoreState(self.settings.value('window_state', b''))
        
        # Восстанавливаем выбранную вкладку
        last_mode = self.settings.value('last_mode', 'check')  # По умолчанию - проверка
        if last_mode == 'phase':
            self.show_phase_ma()
        else:
            self.show_check_ma()

    def closeEvent(self, event):
        """Сохраняет состояние при закрытии окна"""
        self.settings.setValue('window_geometry', self.saveGeometry())
        self.settings.setValue('window_state', self.saveState())
        
        # Сохраняем текущую вкладку
        if self.central_widget.currentWidget() == self.phase_ma_widget:
            self.settings.setValue('last_mode', 'phase')
        else:
            self.settings.setValue('last_mode', 'check')
            
        self.settings.sync()
        super().closeEvent(event)
        
    def show_phase_ma(self):
        self.central_widget.setCurrentWidget(self.phase_ma_widget)
        self.phase_action.setChecked(True)

    def show_check_ma(self):
        self.central_widget.setCurrentWidget(self.check_ma_widget)
        self.check_action.setChecked(True)

    def show_check_stend_ma(self):
        self.central_widget.setCurrentWidget(self.check_stend_ma_widget)
        self.check_action.setChecked(True)

    def open_settings_dialog(self):
        dlg = SettingsDialog(self)

        # Загружаем текущие настройки в диалог
        dlg.pna_ip_edit.setText(self.settings.value('pna_ip', ''))
        dlg.pna_port_edit.setText(self.settings.value('pna_port', ''))
        dlg.pna_mode_combo.setCurrentIndex(int(self.settings.value('pna_mode', 0)))
        dlg.pna_files_path.setText(self.settings.value('pna_files_path', 'C:\\Users\\Public\\Documents\\Network Analyzer\\'))
        
        dlg.psn_ip_edit.setText(self.settings.value('psn_ip', ''))
        dlg.psn_port_edit.setText(self.settings.value('psn_port', ''))
        dlg.psn_mode_combo.setCurrentIndex(int(self.settings.value('psn_mode', 0)))
        dlg.psn_speed_x.setValue(int(self.settings.value('psn_speed_x', 10)))
        dlg.psn_speed_y.setValue(int(self.settings.value('psn_speed_y', 10)))
        dlg.psn_acc_x.setValue(int(self.settings.value('psn_acc_x', 5)))
        dlg.psn_acc_y.setValue(int(self.settings.value('psn_acc_y', 5)))
        
        dlg.ma_com_combo.setCurrentText(self.settings.value('ma_com_port', ''))
        dlg.ma_mode_combo.setCurrentIndex(int(self.settings.value('ma_mode', 0)))
        
        if dlg.exec_() == QtWidgets.QDialog.Accepted:
            settings = dlg.get_settings()
            # Сохраняем все настройки
            for k, v in settings.items():
                self.settings.setValue(k, v)
            self.settings.sync()
            
            logger.info('Настройки сохранены')
            logger.debug(f'Сохраненные настройки: {settings}')
            
            # Передаём параметры в оба виджета
            self.phase_ma_widget.set_device_settings(settings)
            self.check_ma_widget.set_device_settings(settings)
            self.check_stend_ma_widget.set_device_settings(settings)

    def load_settings(self):
        # При запуске приложения сразу применяем параметры к обоим виджетам
        settings = {}
        # Загружаем все сохраненные настройки с значениями по умолчанию
        settings['pna_ip'] = self.settings.value('pna_ip', '')
        settings['pna_port'] = self.settings.value('pna_port', '')
        settings['pna_mode'] = int(self.settings.value('pna_mode', 0))
        settings['pna_files_path'] = self.settings.value('pna_files_path', 'C:\\Users\\Public\\Documents\\Network Analyzer\\')
        
        settings['psn_ip'] = self.settings.value('psn_ip', '')
        settings['psn_port'] = self.settings.value('psn_port', '')
        settings['psn_mode'] = int(self.settings.value('psn_mode', 0))
        settings['psn_speed_x'] = int(self.settings.value('psn_speed_x', 10))
        settings['psn_speed_y'] = int(self.settings.value('psn_speed_y', 10))
        settings['psn_acc_x'] = int(self.settings.value('psn_acc_x', 5))
        settings['psn_acc_y'] = int(self.settings.value('psn_acc_y', 5))
        
        settings['ma_com_port'] = self.settings.value('ma_com_port', '')
        settings['ma_mode'] = int(self.settings.value('ma_mode', 0))
        
        logger.info('Настройки загружены из реестра')
        logger.debug(f'Загруженные настройки: {settings}')
        
        self.phase_ma_widget.set_device_settings(settings)
        self.check_ma_widget.set_device_settings(settings)
        self.check_stend_ma_widget.set_device_settings(settings)

if __name__ == '__main__':
    import sys
    app = QtWidgets.QApplication(sys.argv)
    win = MainWindow()
    win.show()
    sys.exit(app.exec_())
