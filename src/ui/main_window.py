from PyQt5 import QtWidgets, QtCore, QtGui
from .widgets.phase_ma_widget import PhaseMaWidget
from .widgets.check_ma_widget import CheckMaWidget
from .widgets.check_stend_ma_widget import StendCheckMaWidget
from .widgets.manual_control_widget import ManualControlWindow
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
            'trigger_ip': self.trigger_ip_edit.text(),
            'trigger_port': self.trigger_port_edit.text(),
            'trigger_mode': self.trigger_mode_combo.currentIndex(),
            'ma_com_port': self.ma_com_combo.currentText(),
            'ma_mode': self.ma_mode_combo.currentIndex(),
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
        self.pna_files_path.setText(settings.get('pna_files_path', 'C:\\Users\\Public\\Documents\\Network Analyzer\\'))
        self.base_save_dir_edit.setText(settings.get('base_save_dir', ''))

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
        self.check_stend_ma_widget = StendCheckMaWidget()
        self.central_widget.addWidget(self.phase_ma_widget)
        self.central_widget.addWidget(self.check_ma_widget)
        self.central_widget.addWidget(self.check_stend_ma_widget)

        # --- Привязка меню ---
        self.phase_action = self.menu_mode.addAction('Фазировка МА в БЭК')
        self.phase_action.setCheckable(True)
        self.phase_action.triggered.connect(self.show_phase_ma)

        self.check_bek_action = self.menu_mode.addAction('Проверка МА в БЭК')
        self.check_bek_action.setCheckable(True)
        self.check_bek_action.triggered.connect(self.show_check_ma)

        self.check_stend_action = self.menu_mode.addAction('Проверка МА на стенде')
        self.check_stend_action.setCheckable(True)
        self.check_stend_action.triggered.connect(self.show_check_stend_ma)

        # Группа для взаимоисключающих действий
        mode_group = QtWidgets.QActionGroup(self)
        mode_group.addAction(self.phase_action)
        mode_group.addAction(self.check_bek_action)
        mode_group.addAction(self.check_stend_action)
        mode_group.setExclusive(True)
        
        self.menu_params.addAction('Настройки устройств', self.open_settings_dialog)
        # --- Утилиты ---
        self.action_manual_control = self.menu_utils.addAction('Ручное управление')
        self.action_manual_control.triggered.connect(self.open_manual_control)

        # Восстанавливаем состояние интерфейса
        self.restore_ui_state()
        
        # Загружаем настройки устройств
        self.load_settings()

        # Ссылка на окно ручного управления, чтобы не собирался GC
        self._manual_control_window = None

    def restore_ui_state(self):
        """Восстанавливает состояние интерфейса"""
        # Восстанавливаем размер и позицию окна
        self.restoreGeometry(self.settings.value('window_geometry', b''))
        self.restoreState(self.settings.value('window_state', b''))
        
        # Восстанавливаем выбранную вкладку
        last_mode = self.settings.value('last_mode', 'check')  # По умолчанию - проверка в БЭК
        if last_mode == 'phase':
            self.show_phase_ma()
        elif last_mode == 'check_stend':
            self.show_check_stend_ma()
        else:
            self.show_check_ma()

    def closeEvent(self, event):
        """Сохраняет состояние при закрытии окна"""
        self.settings.setValue('window_geometry', self.saveGeometry())
        self.settings.setValue('window_state', self.saveState())
        
        # Сохраняем текущую вкладку
        if self.central_widget.currentWidget() == self.phase_ma_widget:
            self.settings.setValue('last_mode', 'phase')
        elif self.central_widget.currentWidget() == self.check_stend_ma_widget:
            self.settings.setValue('last_mode', 'check_stend')
        else:
            self.settings.setValue('last_mode', 'check')
            
        self.settings.sync()
        super().closeEvent(event)
        
    def show_phase_ma(self):
        self.central_widget.setCurrentWidget(self.phase_ma_widget)
        self.phase_action.setChecked(True)

    def show_check_ma(self):
        self.central_widget.setCurrentWidget(self.check_ma_widget)
        self.check_bek_action.setChecked(True)

    def show_check_stend_ma(self):
        self.central_widget.setCurrentWidget(self.check_stend_ma_widget)
        self.check_stend_action.setChecked(True)

    def open_settings_dialog(self):
        dlg = SettingsDialog(self)

        # Загружаем текущие настройки в диалог
        dlg.pna_ip_edit.setText(self.settings.value('pna_ip', ''))
        dlg.pna_port_edit.setText(self.settings.value('pna_port', ''))
        dlg.pna_mode_combo.setCurrentIndex(int(self.settings.value('pna_mode', 0)))
        dlg.pna_files_path.setText(self.settings.value('pna_files_path', 'C:\\Users\\Public\\Documents\\Network Analyzer\\'))
        dlg.base_save_dir_edit.setText(self.settings.value('base_save_dir', ''))
        
        dlg.psn_ip_edit.setText(self.settings.value('psn_ip', ''))
        dlg.psn_port_edit.setText(self.settings.value('psn_port', ''))
        dlg.psn_mode_combo.setCurrentIndex(int(self.settings.value('psn_mode', 0)))
        dlg.psn_speed_x.setValue(int(self.settings.value('psn_speed_x', 10)))
        dlg.psn_speed_y.setValue(int(self.settings.value('psn_speed_y', 10)))
        dlg.psn_acc_x.setValue(int(self.settings.value('psn_acc_x', 5)))
        dlg.psn_acc_y.setValue(int(self.settings.value('psn_acc_y', 5)))
        
        dlg.trigger_ip_edit.setText(self.settings.value('trigger_ip', ''))
        dlg.trigger_port_edit.setText(self.settings.value('trigger_port', ''))
        dlg.trigger_mode_combo.setCurrentIndex(int(self.settings.value('trigger_mode', 0)))
        
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
        else:
            # При отмене — не сохраняем, но всё равно пробросим актуальные настройки (на случай, если были активные)
            settings = self._collect_current_settings()
            settings['base_save_dir'] = self.settings.value('base_save_dir', '')
            self.phase_ma_widget.set_device_settings(settings)
            self.check_ma_widget.set_device_settings(settings)
            self.check_stend_ma_widget.set_device_settings(settings)

    def _collect_current_settings(self):
        """Собирает текущие настройки из QSettings в dict, как в load_settings."""
        settings = {}
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
        settings['trigger_ip'] = self.settings.value('trigger_ip', '')
        settings['trigger_port'] = self.settings.value('trigger_port', '')
        settings['trigger_mode'] = int(self.settings.value('trigger_mode', 0))
        settings['ma_com_port'] = self.settings.value('ma_com_port', '')
        settings['ma_mode'] = int(self.settings.value('ma_mode', 0))
        return settings

    def open_manual_control(self):
        """Открывает окно ручного управления (утилиты)."""
        try:
            if self._manual_control_window is None or not self._manual_control_window.isVisible():
                self._manual_control_window = ManualControlWindow(self)
                # Передаём текущие настройки
                self._manual_control_window.set_device_settings(self._collect_current_settings())
            self._manual_control_window.show()
            self._manual_control_window.raise_()
            self._manual_control_window.activateWindow()
        except Exception as e:
            logger.error(f'Не удалось открыть окно ручного управления: {e}')

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
        
        settings['trigger_ip'] = self.settings.value('trigger_ip', '')
        settings['trigger_port'] = self.settings.value('trigger_port', '')
        settings['trigger_mode'] = int(self.settings.value('trigger_mode', 0))
        
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
