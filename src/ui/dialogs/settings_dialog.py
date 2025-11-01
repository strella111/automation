from PyQt5 import QtWidgets
import serial.tools.list_ports
from loguru import logger


class SettingsDialog(QtWidgets.QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle('Параметры')
        self.setModal(True)
        layout = QtWidgets.QVBoxLayout(self)

        tabs = QtWidgets.QTabWidget()
        layout.addWidget(tabs)

        # --- Вкладка: Устройства ---
        devices_tab = QtWidgets.QWidget()
        devices_layout = QtWidgets.QVBoxLayout(devices_tab)

        # --- Настройки PNA ---
        pna_group = QtWidgets.QGroupBox('Настройки PNA')
        pna_layout = QtWidgets.QFormLayout(pna_group)
        self.pna_ip_edit = QtWidgets.QLineEdit()
        self.pna_port_edit = QtWidgets.QLineEdit()
        self.pna_mode_combo = QtWidgets.QComboBox()
        self.pna_mode_combo.addItems(['Реальный', 'Тестовый'])
        self.pna_files_path = QtWidgets.QLineEdit()
        self.pna_files_path.setPlaceholderText('C\\Users\\Public\\Documents\\Network Analyzer\\')
        pna_layout.addRow('IP:', self.pna_ip_edit)
        pna_layout.addRow('Порт:', self.pna_port_edit)
        pna_layout.addRow('Режим:', self.pna_mode_combo)
        pna_layout.addRow('Путь к файлам:', self.pna_files_path)
        devices_layout.addWidget(pna_group)

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
        devices_layout.addWidget(psn_group)

        # --- Настройки TriggerBox ---
        trigger_group = QtWidgets.QGroupBox('Настройки TriggerBox')
        trigger_layout = QtWidgets.QFormLayout(trigger_group)
        self.trigger_ip_edit = QtWidgets.QLineEdit()
        self.trigger_port_edit = QtWidgets.QLineEdit()
        self.trigger_mode_combo = QtWidgets.QComboBox()
        self.trigger_mode_combo.addItems(['Реальный', 'Тестовый'])
        trigger_layout.addRow('IP:', self.trigger_ip_edit)
        trigger_layout.addRow('Порт:', self.trigger_port_edit)
        trigger_layout.addRow('Режим:', self.trigger_mode_combo)
        devices_layout.addWidget(trigger_group)

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
        devices_layout.addWidget(ma_group)

        # --- Настройки АФАР ---
        afar_group = QtWidgets.QGroupBox('Настройки АФАР')
        afar_layout = QtWidgets.QFormLayout(afar_group)
        
        # Тип подключения
        self.afar_connection_type = QtWidgets.QComboBox()
        self.afar_connection_type.addItems(['UDP', 'COM'])
        afar_layout.addRow('Тип подключения:', self.afar_connection_type)
        
        # UDP настройки
        self.afar_ip_edit = QtWidgets.QLineEdit()
        self.afar_port_edit = QtWidgets.QLineEdit()
        afar_layout.addRow('IP:', self.afar_ip_edit)
        afar_layout.addRow('Порт:', self.afar_port_edit)
        
        # COM настройки
        self.afar_com_combo = QtWidgets.QComboBox()
        self.update_afar_com_ports_btn = QtWidgets.QPushButton('Обновить')
        self.update_afar_com_ports_btn.clicked.connect(self.update_afar_com_ports)
        afar_com_port_layout = QtWidgets.QHBoxLayout()
        afar_com_port_layout.addWidget(self.afar_com_combo)
        afar_com_port_layout.addWidget(self.update_afar_com_ports_btn)
        afar_layout.addRow('COM-порт:', afar_com_port_layout)
        
        # Режим
        self.afar_mode_combo = QtWidgets.QComboBox()
        self.afar_mode_combo.addItems(['Реальный', 'Тестовый'])
        afar_layout.addRow('Режим:', self.afar_mode_combo)
        
        devices_layout.addWidget(afar_group)
        tabs.addTab(devices_tab, 'Устройства')

        # --- Вкладка: Другое (сохранение) ---
        other_tab = QtWidgets.QWidget()
        other_layout = QtWidgets.QFormLayout(other_tab)
        self.base_save_dir_edit = QtWidgets.QLineEdit()
        self.base_save_dir_edit.setReadOnly(True)
        self.base_save_dir_btn = QtWidgets.QPushButton('Выбрать папку...')
        def pick_base_dir():
            path = QtWidgets.QFileDialog.getExistingDirectory(self, 'Выбор общей папки сохранения')
            if path:
                self.base_save_dir_edit.setText(path)
        self.base_save_dir_btn.clicked.connect(pick_base_dir)
        h = QtWidgets.QHBoxLayout()
        h.addWidget(self.base_save_dir_edit, 1)
        h.addWidget(self.base_save_dir_btn, 0)
        container = QtWidgets.QWidget(); container.setLayout(h)
        other_layout.addRow('Общая папка хранения данных:', container)
        info_lbl = QtWidgets.QLabel('Внутри будут созданы подпапки: check, stend, phase')
        info_lbl.setStyleSheet('color: gray')
        other_layout.addRow('', info_lbl)
        tabs.addTab(other_tab, 'Другое')

        # Обновляем список COM портов сразу при создании диалога
        self.update_com_ports()
        self.update_afar_com_ports()

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

    def update_afar_com_ports(self):
        """Обновляет список доступных COM портов для АФАР"""
        current_port = self.afar_com_combo.currentText()
        self.afar_com_combo.clear()
        # Добавляем тестовый режим
        self.afar_com_combo.addItem('Тестовый')
        # Получаем список доступных портов
        filtered_ports = []
        for port in serial.tools.list_ports.comports():
            if any(x in port.device for x in ['usbserial', 'usbmodem', 'ttyUSB', 'ttyACM', 'wchusbserial', 'SLAB_USBtoUART', 'COM']):
                # Показываем только имя порта без описания
                filtered_ports.append(port.device)
        self.afar_com_combo.addItems(filtered_ports)
        # Восстанавливаем предыдущий выбор, если возможно
        index = self.afar_com_combo.findText(current_port)
        if index >= 0:
            self.afar_com_combo.setCurrentIndex(index)
        else:
            self.afar_com_combo.setCurrentIndex(0)

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
            'trigger_ip': self.trigger_ip_edit.text(),
            'trigger_port': self.trigger_port_edit.text(),
            'trigger_mode': self.trigger_mode_combo.currentIndex(),
            'ma_com_port': self.ma_com_combo.currentText(),
            'ma_mode': self.ma_mode_combo.currentIndex(),
            'afar_connection_type': self.afar_connection_type.currentText().lower(),
            'afar_ip': self.afar_ip_edit.text(),
            'afar_port': self.afar_port_edit.text(),
            'afar_com_port': self.afar_com_combo.currentText(),
            'afar_mode': self.afar_mode_combo.currentIndex(),
            'pna_mode': self.pna_mode_combo.currentIndex(),
            'psn_mode': self.psn_mode_combo.currentIndex(),
            'pna_files_path': self.pna_files_path.text(),
            'base_save_dir': self.base_save_dir_edit.text(),
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
        self.trigger_ip_edit.setText(settings.get('trigger_ip', ''))
        self.trigger_port_edit.setText(settings.get('trigger_port', ''))
        self.trigger_mode_combo.setCurrentIndex(int(settings.get('trigger_mode', 0)))
        self.ma_com_combo.setCurrentText(settings.get('ma_com_port', ''))
        self.ma_mode_combo.setCurrentIndex(int(settings.get('ma_mode', 0)))
        
        # Настройки АФАР
        afar_connection_type = settings.get('afar_connection_type', 'udp')
        if afar_connection_type == 'udp':
            self.afar_connection_type.setCurrentIndex(0)
        else:
            self.afar_connection_type.setCurrentIndex(1)
        self.afar_ip_edit.setText(settings.get('afar_ip', ''))
        self.afar_port_edit.setText(settings.get('afar_port', ''))
        self.afar_com_combo.setCurrentText(settings.get('afar_com_port', ''))
        self.afar_mode_combo.setCurrentIndex(int(settings.get('afar_mode', 0)))
        
        self.pna_files_path.setText(settings.get('pna_files_path', 'C:\\Users\\Public\\Documents\\Network Analyzer\\'))
        self.base_save_dir_edit.setText(settings.get('base_save_dir', ''))
