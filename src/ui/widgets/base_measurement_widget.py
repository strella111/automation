import time

from PyQt5 import QtWidgets, QtCore, QtGui
from PyQt5.QtWidgets import QMessageBox, QStyle
from loguru import logger
import threading
import os

from core.devices.trigger_box import E5818Config
from ui.components.log_handler import QTextEditLogHandler
from core.workers.device_connection_worker import DeviceConnectionWorker
from ui.dialogs.pna_file_dialog import PnaFileDialog


class BaseMeasurementWidget(QtWidgets.QWidget):
    """Базовый класс для всех виджетов измерений"""
    
    # Общие сигналы
    device_connection_started = QtCore.pyqtSignal(str)  # device_name
    device_connection_finished = QtCore.pyqtSignal(str, bool, str)  # device_name, success, message
    error_signal = QtCore.pyqtSignal(str, str)  # title, message
    buttons_enabled_signal = QtCore.pyqtSignal(bool)  # enabled
    
    def __init__(self):
        super().__init__()
        
        self.ma = None
        self.pna = None
        self.psn = None
        self.trigger = None
        self.afar = None
        
        # Потоки для асинхронного подключения к устройствам
        self._ma_connection_thread = None
        self._pna_connection_thread = None
        self._psn_connection_thread = None
        self._trigger_connection_thread = None
        self._afar_connection_thread = None
        
        # Общие переменные для измерений
        self._stop_flag = threading.Event()
        self._pause_flag = threading.Event()
        
        # Настройки устройств
        self.device_settings = {}
        self.pna_settings = {}
        
        # Обработчик логов
        self.log_handler = None
        
        # Инициализация UI и подключений
        self._setup_common_ui()
        self._setup_device_connections()
        self._setup_common_connections()
    
    def _setup_common_ui(self):
        """Общая настройка UI - переопределяется в наследниках"""
        pass
    
    def _setup_device_connections(self):
        """Общая настройка подключений к устройствам"""
        # Подключение сигналов для асинхронного подключения к устройствам
        self.device_connection_started.connect(self._on_device_connection_started)
        self.device_connection_finished.connect(self._on_device_connection_finished)
    
    def _setup_common_connections(self):
        """Общие подключения сигналов"""
        self.error_signal.connect(self.show_error_message)
        self.buttons_enabled_signal.connect(self.set_buttons_enabled)
    
    def build_connect_group(self, button_specs):
        """
        Создает группу кнопок подключения устройств.
        
        Args:
            button_specs: iterable of tuples (attr_name, label)
                          attr_name — префикс для имени поля кнопки, например 'pna' -> self.pna_connect_btn
        Returns:
            QtWidgets.QGroupBox с вертикальным layout.
        """
        group = QtWidgets.QGroupBox('Подключение устройств')
        layout = QtWidgets.QVBoxLayout(group)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(10)
        
        for attr_name, label in button_specs:
            row_widget = QtWidgets.QWidget()
            row_layout = QtWidgets.QHBoxLayout(row_widget)
            row_layout.setContentsMargins(0, 0, 0, 0)
            
            btn = QtWidgets.QPushButton(label)
            btn.setMinimumHeight(40)
            row_layout.addWidget(btn)
            layout.addWidget(row_widget)
            
            setattr(self, f"{attr_name}_connect_btn", btn)
            # Инициализируем красным состоянием «не подключено»
            self.set_button_connection_state(btn, False)
        
        return group
    
    def create_control_buttons(self, include_apply=True, include_start=True, include_stop=True, include_pause=True):
        """
        Создает стандартные кнопки управления измерением.
        Возвращает (apply_btn | None, control_layout)
        """
        apply_btn = None
        if include_apply:
            apply_btn = QtWidgets.QPushButton('Применить параметры')
        
        control_layout = QtWidgets.QHBoxLayout()
        
        if include_pause:
            self.pause_btn = QtWidgets.QPushButton('Пауза')
            control_layout.addWidget(self.pause_btn)
        if include_stop:
            self.stop_btn = QtWidgets.QPushButton('Стоп')
            control_layout.addWidget(self.stop_btn)
        if include_start:
            self.start_btn = QtWidgets.QPushButton('Старт')
            control_layout.addWidget(self.start_btn)
        
        return apply_btn, control_layout

    def build_pna_form(
        self,
        points_options=None,
        default_points=None,
        include_pulse=True,
        include_file=True,
        include_pulse_source=True,
        include_trig_polarity=True,
        start_default=9300,
        stop_default=9800,
        power_default=0,
    ):
        """
        Фабрика вкладки PNA. Создает форму и сохраняет контролы в атрибутах:
        s_param_combo, pna_power, pna_start_freq, pna_stop_freq,
        pna_number_of_points, pulse_mode_combo, pulse_width, pulse_period,
        settings_file_edit, load_file_btn.
        Возвращает (pna_tab, pna_tab_layout).
        """
        if points_options is None:
            points_options = ['3', '11', '21', '33', '51', '101', '201']
        if default_points is None:
            default_points = '11'

        pna_tab = QtWidgets.QWidget()
        pna_tab_layout = QtWidgets.QFormLayout(pna_tab)

        self.s_param_combo = QtWidgets.QComboBox()
        self.s_param_combo.addItems(['S21', 'S12', 'S11', 'S22'])
        pna_tab_layout.addRow('S-параметр:', self.s_param_combo)

        self.pna_power = QtWidgets.QDoubleSpinBox()
        self.pna_power.setRange(-20, 18)
        self.pna_power.setSingleStep(1)
        self.pna_power.setDecimals(0)
        self.pna_power.setValue(power_default)
        pna_tab_layout.addRow('Выходная мощность (дБм):', self.pna_power)

        self.pna_start_freq = QtWidgets.QSpinBox()
        self.pna_start_freq.setRange(1, 50000)
        self.pna_start_freq.setSingleStep(50)
        self.pna_start_freq.setValue(start_default)
        self.pna_start_freq.setSuffix(' МГц')
        pna_tab_layout.addRow('Нач. частота:', self.pna_start_freq)

        self.pna_stop_freq = QtWidgets.QSpinBox()
        self.pna_stop_freq.setRange(1, 50000)
        self.pna_stop_freq.setSingleStep(50)
        self.pna_stop_freq.setValue(stop_default)
        self.pna_stop_freq.setSuffix(' МГц')
        pna_tab_layout.addRow('Кон. частота:', self.pna_stop_freq)

        self.pna_number_of_points = QtWidgets.QComboBox()
        self.pna_number_of_points.addItems(points_options)
        if default_points in points_options:
            self.pna_number_of_points.setCurrentText(default_points)
        pna_tab_layout.addRow('Кол-во точек:', self.pna_number_of_points)

        if include_pulse:
            self.pulse_mode_combo = QtWidgets.QComboBox()
            self.pulse_mode_combo.addItems(['Standard', 'Off'])
            pna_tab_layout.addRow('Импульсный режим', self.pulse_mode_combo)

            self.pulse_width = QtWidgets.QDoubleSpinBox()
            self.pulse_width.setDecimals(3)
            self.pulse_width.setRange(5, 50)
            self.pulse_width.setSingleStep(1)
            self.pulse_width.setValue(20)
            self.pulse_width.setSuffix(' мкс')
            pna_tab_layout.addRow('Ширина импульса', self.pulse_width)

            self.pulse_period = QtWidgets.QDoubleSpinBox()
            self.pulse_period.setDecimals(3)
            self.pulse_period.setRange(20, 20000)
            self.pulse_period.setValue(2000)
            self.pulse_period.setSingleStep(10)
            self.pulse_period.setSuffix(' мкс')
            pna_tab_layout.addRow('Период импульса', self.pulse_period)

        if include_pulse_source:
            self.pulse_source = QtWidgets.QComboBox()
            self.pulse_source.addItems(['External', 'Internal'])
            pna_tab_layout.addRow('Источник импульса', self.pulse_source)

        if include_trig_polarity:
            self.trig_polarity = QtWidgets.QComboBox()
            self.trig_polarity.addItems(['Positive', 'Negative'])
            pna_tab_layout.addRow('Полярность сигнала', self.trig_polarity)

        if include_file:
            settings_layout = QtWidgets.QHBoxLayout()
            settings_layout.setSpacing(4)
            self.settings_file_edit = QtWidgets.QLineEdit()
            self.settings_file_edit.setReadOnly(True)
            self.settings_file_edit.setPlaceholderText('Выберите файл настроек...')
            self.settings_file_edit.setFixedHeight(32)

            self.load_file_btn = QtWidgets.QPushButton()
            self.load_file_btn.setProperty("iconButton", True)
            self.load_file_btn.setFixedSize(32, 28)
            self.load_file_btn.setToolTip('Выбрать файл настроек')

            style = self.style()
            folder_icon = style.standardIcon(QStyle.StandardPixmap.SP_DirOpenIcon)
            self.load_file_btn.setIcon(folder_icon)
            self.load_file_btn.setIconSize(QtCore.QSize(16, 16))
            self.load_file_btn.setFixedHeight(32)

            settings_layout.addWidget(self.settings_file_edit, 1)
            settings_layout.addWidget(self.load_file_btn, 0)

            pna_tab_layout.addRow('Файл настроек:', settings_layout)

        return pna_tab, pna_tab_layout

    def open_file_dialog(self):
        """Открытие диалога выбора файла настроек PNA"""
        try:
            if not self.pna or not hasattr(self.pna, 'connection'):
                QtWidgets.QMessageBox.warning(self, 'Предупреждение', 'Сначала подключитесь к PNA')
                return

            files_path = self.device_settings.get('pna_files_path', 'C:\\Users\\Public\\Documents\\Network Analyzer\\')

            dialog = PnaFileDialog(self.pna, files_path, self)

            if dialog.exec_() == QtWidgets.QDialog.Accepted:
                selected_file = dialog.selected_file
                if selected_file:
                    self.settings_file_edit.setText(selected_file)
                    self.apply_parsed_settings()
                    logger.info(f'Выбран файл настроек PNA: {selected_file}')

        except Exception as e:
            error_msg = f'Ошибка при выборе файла настроек: {e}'
            QtWidgets.QMessageBox.critical(self, 'Ошибка', error_msg)
            logger.error(error_msg)
    
    def set_button_connection_state(self, button: QtWidgets.QPushButton, connected: bool):
        """Устанавливает состояние кнопки подключения"""
        if connected:
            button.setStyleSheet("QPushButton { background-color: #28a745; color: white; }")
        else:
            button.setStyleSheet("QPushButton { background-color: #dc3545; color: white; }")
    
    def set_buttons_enabled(self, enabled: bool):
        """Включает/выключает кнопки управления"""
        # Переопределяется в наследниках для конкретных кнопок
        pass
    
    def show_error_message(self, title: str, message: str):
        """Показывает всплывающее окно с ошибкой"""
        QMessageBox.critical(self, title, message)
        logger.error(f"{title}: {message}")
    
    def show_warning_message(self, title: str, message: str):
        """Показывает всплывающее окно с предупреждением"""
        QMessageBox.warning(self, title, message)
        logger.warning(f"{title}: {message}")
    
    def show_info_message(self, title: str, message: str):
        """Показывает всплывающее окно с информацией"""
        QMessageBox.information(self, title, message)
        logger.info(f"{title}: {message}")
    
    def set_device_settings(self, settings: dict):
        """Сохраняет параметры устройств из настроек"""
        self.device_settings = settings or {}
        logger.info('Настройки устройств обновлены')
        logger.debug(f'Новые настройки: {self.device_settings}')
    
    # Обработчики сигналов подключения к устройствам
    @QtCore.pyqtSlot(str)
    def _on_device_connection_started(self, device_name: str):
        """Обработчик начала подключения к устройству"""
        logger.info(f"Начинается подключение к {device_name}...")
    
    @QtCore.pyqtSlot(str, bool, str)
    def _on_device_connection_finished(self, device_name: str, success: bool, message: str):
        """Обработчик завершения подключения к устройству"""
        if success:
            logger.info(f"{device_name} успешно подключен: {message}")
        else:
            logger.error(f"Ошибка подключения к {device_name}: {message}")
            self.show_error_message(f"Ошибка подключения к {device_name}", message)
    
    # Методы подключения к устройствам (общие)
    def connect_ma(self):
        """Подключает/отключает МА"""
        if self.ma and self.ma.connection:
            try:
                self.ma.disconnect()
                self.ma = None
                self.ma_connect_btn.setText('МА')
                self.set_button_connection_state(self.ma_connect_btn, False)
                logger.info('МА успешно отключен')
                return
            except Exception as e:
                self.show_error_message("Ошибка отключения МА", f"Не удалось отключить МА: {str(e)}")
                return

        # Проверяем, не идет ли уже подключение
        if self._ma_connection_thread and self._ma_connection_thread.isRunning():
            logger.info("Подключение к МА уже выполняется...")
            return

        com_port = self.device_settings.get('ma_com_port', '')
        mode = self.device_settings.get('ma_mode', 0)

        if mode == 0 and (not com_port or com_port == 'Тестовый'):
            self.show_error_message("Ошибка настроек", "COM-порт не выбран. Откройте настройки и выберите COM-порт.")
            return

        logger.info(f'Попытка подключения к МА через {com_port if mode == 0 else "тестовый режим"}, режим: {"реальный" if mode == 0 else "тестовый"}')

        # Создаем поток для подключения
        connection_params = {
            'com_port': com_port,
            'mode': mode
        }
        
        self._ma_connection_thread = DeviceConnectionWorker('MA', connection_params)
        self._ma_connection_thread.connection_finished.connect(self._on_ma_connection_finished)
        self.device_connection_started.emit('MA')
        self._ma_connection_thread.start()
    
    def connect_pna(self):
        """Подключает/отключает PNA"""
        if self.pna and self.pna.connection:
            try:
                self.pna.disconnect()
                self.pna = None
                self.set_button_connection_state(self.pna_connect_btn, False)
                logger.info('PNA успешно отключен')
                return
            except Exception as e:
                self.show_error_message("Ошибка отключения PNA", f"Не удалось отключить PNA: {str(e)}")
                return

        # Проверяем, не идет ли уже подключение
        if self._pna_connection_thread and self._pna_connection_thread.isRunning():
            logger.info("Подключение к PNA уже выполняется...")
            return

        ip = self.device_settings.get('pna_ip', '')
        port = int(self.device_settings.get('pna_port', ''))
        mode = self.device_settings.get('pna_mode', 0)

        # Создаем поток для подключения
        connection_params = {
            'ip': ip,
            'port': port,
            'mode': mode
        }
        
        self._pna_connection_thread = DeviceConnectionWorker('PNA', connection_params)
        self._pna_connection_thread.connection_finished.connect(self._on_pna_connection_finished)
        self.device_connection_started.emit('PNA')
        self._pna_connection_thread.start()
    
    def connect_psn(self):
        """Подключает/отключает PSN"""
        if self.psn and self.psn.connection:
            try:
                self.psn.disconnect()
                self.psn = None
                self.set_button_connection_state(self.psn_connect_btn, False)
                logger.info('PSN успешно отключен')
                return
            except Exception as e:
                self.show_error_message("Ошибка отключения PSN", f"Не удалось отключить PSN: {str(e)}")
                return

        if self._psn_connection_thread and self._psn_connection_thread.isRunning():
            logger.info("Подключение к PSN уже выполняется...")
            return

        ip = self.device_settings.get('psn_ip', '')
        port = self.device_settings.get('psn_port', '')
        mode = self.device_settings.get('psn_mode', 0)

        # Создаем поток для подключения
        connection_params = {
            'ip': ip,
            'port': port,
            'mode': mode
        }
        
        self._psn_connection_thread = DeviceConnectionWorker('PSN', connection_params)
        self._psn_connection_thread.connection_finished.connect(self._on_psn_connection_finished)
        self.device_connection_started.emit('PSN')
        self._psn_connection_thread.start()
    
    def connect_trigger(self):
        """Подключает/отключает устройство синхронизации (TriggerBox E5818)"""
        if self.trigger is not None and getattr(self.trigger, 'connection', None) is not None:
            try:
                self.trigger.close()
                self.trigger = None
                self.set_button_connection_state(self.gen_connect_btn, False)
                logger.info('Устройство синхронизации отключено')
                return
            except Exception as e:
                self.show_error_message("Ошибка отключения устройства синхронизации", f"Не удалось отключить: {str(e)}")
                return

        # Сбор параметров из общих настроек и вкладки
        trigger_ip = self.device_settings.get('trigger_ip', '').strip()
        trigger_port = str(self.device_settings.get('trigger_port', '')).strip()
        trigger_mode = int(self.device_settings.get('trigger_mode', 0))

        if trigger_mode == 0:
            if not trigger_ip or not trigger_port:
                self.show_error_message("Ошибка настроек", "IP/Порт устройства синхронизации не заданы. Откройте параметры и заполните поля.")
                return
            visa_resource = f"TCPIP0::{trigger_ip}::inst0::INSTR"
        else:
            # Тестовый режим — используем заглушечный ресурс
            visa_resource = "TEST"

        # Каналы TTL/EXT из вкладки (комбо)
        ttl_text = getattr(self, 'trig_ttl_channel', type('obj', (object,), {'currentText': lambda: 'TTL1'})()).currentText().upper().replace('TTL', '')
        ext_text = getattr(self, 'trig_ext_channel', type('obj', (object,), {'currentText': lambda: 'EXT1'})()).currentText().upper().replace('EXT', '')
        try:
            ttl_channel = int(ttl_text)
            ext_channel = int(ext_text)
        except Exception:
            ttl_channel, ext_channel = 1, 1

        # Параметры тайминга из вкладки
        start_lead_s = float(getattr(self, 'trig_start_lead', type('obj', (object,), {'value': lambda: 25.0})()).value())
        pulse_period_s = float(getattr(self, 'trig_pulse_period', type('obj', (object,), {'value': lambda: 500.0})()).value())
        min_alarm_guard_s = float(getattr(self, 'trig_min_alarm_guard', type('obj', (object,), {'value': lambda: 0.0})()).value())
        ext_debounce_s = float(getattr(self, 'trig_ext_debounce', type('obj', (object,), {'value': lambda: 0.0})()).value())

        # Таймаут берем из общих настроек устройств
        visa_timeout_ms = int(self.device_settings.get('trigger_visa_timeout_ms', 5000))
        # Интервал очистки логов (для предотвращения таймаутов)
        log_clear_interval = int(self.device_settings.get('trigger_log_clear_interval', 300))

        # Проверяем, не идет ли уже подключение
        if self._trigger_connection_thread and self._trigger_connection_thread.isRunning():
            logger.info("Подключение к устройству синхронизации уже выполняется...")
            return

        # Создаем поток для подключения
        connection_params = {
            'config': E5818Config(
                resource=visa_resource,
                ttl_channel=ttl_channel,
                ext_channel=ext_channel,
                visa_timeout_ms=visa_timeout_ms,
                start_lead_s=start_lead_s,
                pulse_period_s=pulse_period_s,
                min_alarm_guard_s=min_alarm_guard_s,
                ext_debounce_s=ext_debounce_s,
                log_clear_interval=log_clear_interval,
                logger=lambda m: logger.debug(f"E5818 | {m}")
            )
        }
        
        self._trigger_connection_thread = DeviceConnectionWorker('Trigger', connection_params)
        self._trigger_connection_thread.connection_finished.connect(self._on_trigger_connection_finished)
        self.device_connection_started.emit('Trigger')
        self._trigger_connection_thread.start()
    
    def connect_afar(self):
        """Подключает/отключает АФАР"""
        if self.afar and self.afar.connection:
            try:
                self.afar.disconnect()
                self.afar = None
                self.set_button_connection_state(self.afar_connect_btn, False)
                logger.info('АФАР успешно отключен')
                return
            except Exception as e:
                self.show_error_message("Ошибка отключения АФАР", f"Не удалось отключить АФАР: {str(e)}")
                return

        # Проверяем, не идет ли уже подключение
        if self._afar_connection_thread and self._afar_connection_thread.isRunning():
            logger.info("Подключение к АФАР уже выполняется...")
            return

        connection_type = self.device_settings.get('afar_connection_type', 'udp')
        mode = self.device_settings.get('afar_mode', 0)
        write_delay_ms = int(self.device_settings.get('afar_write_delay', 100))  # Задержка в миллисекундах
        
        if connection_type == 'udp':
            ip = self.device_settings.get('afar_ip', '')
            port = int(self.device_settings.get('afar_port', ''))
            
            if mode == 0 and (not ip or not port):
                self.show_error_message("Ошибка настроек", "IP/Порт АФАР не заданы. Откройте настройки и заполните поля.")
                return
                
            connection_params = {
                'connection_type': connection_type,
                'com_port': None,  # Для UDP не нужен COM-порт
                'ip': ip,
                'port': port,
                'mode': mode,
                'write_delay_ms': write_delay_ms
            }
        else:  # com
            com_port = self.device_settings.get('afar_com_port', '')
            
            if mode == 0 and (not com_port or com_port == 'Тестовый'):
                self.show_error_message("Ошибка настроек", "COM-порт АФАР не выбран. Откройте настройки и выберите COM-порт.")
                return
                
            connection_params = {
                'connection_type': connection_type,
                'com_port': com_port,
                'ip': None,  # Для COM не нужен IP
                'port': None,  # Для COM не нужен порт
                'mode': mode,
                'write_delay_ms': write_delay_ms
            }
        
        logger.info(f'Попытка подключения к АФАР через {connection_type}, режим: {"реальный" if mode == 0 else "тестовый"}')
        
        self._afar_connection_thread = DeviceConnectionWorker('AFAR', connection_params)
        self._afar_connection_thread.connection_finished.connect(self._on_afar_connection_finished)
        self.device_connection_started.emit('AFAR')
        self._afar_connection_thread.start()

    @QtCore.pyqtSlot(str, bool, str, object)
    def _on_ma_connection_finished(self, device_name: str, success: bool, message: str, device_instance):
        """Обработчик завершения подключения к МА"""
        if success:
            self.ma = device_instance
            if self.ma.bu_addr:
                self.ma_connect_btn.setText(f'МА №{self.ma.bu_addr}')
            self.set_button_connection_state(self.ma_connect_btn, True)
            logger.info(f'МА успешно подключен: {message}')
        else:
            self.ma = None
            self.set_button_connection_state(self.ma_connect_btn, False)
            self.show_error_message("Ошибка подключения МА", f"Не удалось подключиться к МА: {message}")
        
        # Очищаем ссылку на поток
        self._ma_connection_thread = None

    @QtCore.pyqtSlot(str, bool, str, object)
    def _on_pna_connection_finished(self, device_name: str, success: bool, message: str, device_instance):
        """Обработчик завершения подключения к PNA"""
        if success:
            self.pna = device_instance
            self.set_button_connection_state(self.pna_connect_btn, True)
            logger.info(f'PNA успешно подключен: {message}')
            # Обновляем список файлов настроек PNA, если метод существует
            if hasattr(self, 'update_pna_settings_files'):
                self.update_pna_settings_files()
        else:
            self.pna = None
            self.set_button_connection_state(self.pna_connect_btn, False)
            self.show_error_message("Ошибка подключения PNA", f"Не удалось подключиться к PNA: {message}")
        
        # Очищаем ссылку на поток
        self._pna_connection_thread = None

    @QtCore.pyqtSlot(str, bool, str, object)
    def _on_psn_connection_finished(self, device_name: str, success: bool, message: str, device_instance):
        """Обработчик завершения подключения к PSN"""
        if success:
            self.psn = device_instance
            self.set_button_connection_state(self.psn_connect_btn, True)
            logger.info(f'Планарный сканер успешно подключен: {message}')
        else:
            self.psn = None
            self.set_button_connection_state(self.psn_connect_btn, False)
            self.show_error_message("Ошибка подключения планарного сканера", f"Не удалось подключиться к PSN: {message}")
        
        # Очищаем ссылку на поток
        self._psn_connection_thread = None

    @QtCore.pyqtSlot(str, bool, str, object)
    def _on_trigger_connection_finished(self, device_name: str, success: bool, message: str, device_instance):
        """Обработчик завершения подключения к Trigger"""
        if success:
            self.trigger = device_instance
            self.set_button_connection_state(self.gen_connect_btn, True)
            logger.info(f'Устройство синхронизации успешно подключено: {message}')
        else:
            self.trigger = None
            self.set_button_connection_state(self.gen_connect_btn, False)
            self.show_error_message("Ошибка подключения устройства синхронизации", f"Не удалось подключиться: {message}")
        
        # Очищаем ссылку на поток
        self._trigger_connection_thread = None

    @QtCore.pyqtSlot(str, bool, str, object)
    def _on_afar_connection_finished(self, device_name: str, success: bool, message: str, device_instance):
        """Обработчик завершения подключения к АФАР"""
        if success:
            self.afar = device_instance
            self.set_button_connection_state(self.afar_connect_btn, True)
            logger.info(f'АФАР успешно подключен: {message}')
        else:
            self.afar = None
            self.set_button_connection_state(self.afar_connect_btn, False)
            self.show_error_message("Ошибка подключения АФАР", f"Не удалось подключиться к АФАР: {message}")
        
        # Очищаем ссылку на поток
        self._afar_connection_thread = None
    
    def create_centered_table_item(self, text: str) -> QtWidgets.QTableWidgetItem:
        """Создает элемент таблицы с центрированным текстом"""
        item = QtWidgets.QTableWidgetItem(str(text))
        item.setTextAlignment(QtCore.Qt.AlignCenter)
        item.setFlags(item.flags() & ~QtCore.Qt.ItemIsEditable)
        return item
    
    def create_status_table_item(self, text: str, is_ok: bool) -> QtWidgets.QTableWidgetItem:
        """Создает элемент таблицы со статусом (OK/FAIL)"""
        item = QtWidgets.QTableWidgetItem(str(text))
        item.setTextAlignment(QtCore.Qt.AlignCenter)
        item.setFlags(item.flags() & ~QtCore.Qt.ItemIsEditable)
        
        if is_ok:
            item.setBackground(QtGui.QColor("#d4edda"))
            item.setForeground(QtGui.QColor("#155724"))
        else:
            item.setBackground(QtGui.QColor("#f8d7da"))
            item.setForeground(QtGui.QColor("#721c24"))
        
        return item
    
    def create_neutral_status_item(self, text: str) -> QtWidgets.QTableWidgetItem:
        """Создает нейтральный элемент таблицы"""
        item = QtWidgets.QTableWidgetItem(str(text))
        item.setTextAlignment(QtCore.Qt.AlignCenter)
        item.setFlags(item.flags() & ~QtCore.Qt.ItemIsEditable)
        return item

    def setup_pna_common(self):
        """Общая настройка PNA для всех измерений"""
        if not self.pna or not self.pna_settings:
            return
        try:
            self.pna.fpreset()
            self.pna.preset()

            if self.pna_settings.get('settings_file'):
                settings_file = self.pna_settings.get('settings_file')
                base_path = self.device_settings.get('pna_files_path', '')
                if settings_file and base_path and not os.path.isabs(settings_file):
                    settings_file = os.path.join(base_path, settings_file)
                self.pna.load_settings_file(settings_file)
                time.sleep(1)
            else:
                self.pna.create_measure(self.pna_settings.get('s_param'))
                self.pna.turn_window(state=True)
                self.pna.put_and_visualize_trace()

            self.pna.set_freq_start(self.pna_settings.get('freq_start'))
            self.pna.set_freq_stop(self.pna_settings.get('freq_stop'))
            self.pna.set_points(self.pna_settings.get('freq_points'))


            if 's_param' in self.pna_settings:
                self.pna.set_s_param(self.pna_settings.get('s_param'))
                if self.pna_settings.get('s_param').lower() == 's21':
                    self.pna.set_power(self.pna_settings.get('power'), port=1)
                elif self.pna_settings.get('s_param').lower() == 's12':
                    self.pna.set_power(self.pna_settings.get('power'), port=2)
                else:
                    logger.warning('Не установлена мощность порта PNA. Отсутствует s-параметр.')
            
            # Настройки импульсного режима (если есть)
            if 'pulse_mode' in self.pna_settings:
                if self.pna_settings.get('pulse_mode').lower() in ('STD'.lower(), 'Standard'.lower()):
                    self.pna.set_standard_pulse()
                else:
                    self.pna.set_pulse_mode_off()

                if self.pna_settings.get('pulse_source').lower() == 'external':
                    self.pna.set_pulse_source_external()
                elif self.pna_settings.get('pulse_source').lower() == 'internal':
                    self.pna.set_pulse_source_internal()

                if self.pna_settings.get('polarity_trig').lower() == 'positive':
                    self.pna.set_positive_polarity_trig()
                elif self.pna_settings.get('polarity_trig').lower() == 'negative':
                    self.pna.set_negative_polarity_trig()
                self.pna.set_period(self.pna_settings.get('pulse_period'))
                self.pna.set_pulse_width(self.pna_settings.get('pulse_width'))
            
            # Включение выхода
            self.pna.set_ascii_data()
            self.pna.set_output(True)
            self.pna.period = self.pna.get_period()
            self.pna.count_freqs_point = self.pna.get_amount_of_points()

            # Проверка и установка активного измерения
            meas = self.pna.get_selected_meas()
            if not meas:
                measures = self.pna.get_all_meas()
                if measures:
                    self.pna.set_current_meas(measures[0])
                    
            logger.info('PNA успешно настроен')
            
        except Exception as e:
            logger.error(f"Ошибка при настройке PNA: {e}")
            raise

    def setup_scanner_common(self):
        """Общая настройка сканера для измерений с PSN"""
        if not self.psn or not self.device_settings:
            return
            
        try:
            self.psn.preset()
            self.psn.preset_axis(0)
            self.psn.preset_axis(1)

            x_offset = self.coord_system.x_offset if self.coord_system else 0
            y_offset = self.coord_system.y_offset if self.coord_system else 0
            self.psn.set_offset(x_offset, y_offset)

            speed_x = int(self.device_settings.get('psn_speed_x', 0))
            speed_y = int(self.device_settings.get('psn_speed_y', 0))
            acc_x = int(self.device_settings.get('psn_acc_x', 0))
            acc_y = int(self.device_settings.get('psn_acc_y', 0))
            
            self.psn.set_speed(0, speed_x)
            self.psn.set_speed(1, speed_y)
            self.psn.set_acc(0, acc_x)
            self.psn.set_acc(1, acc_y)
            
            logger.info(f'Параметры PSN успешно применены (смещения: x={x_offset}, y={y_offset})')
            
        except Exception as e:
            logger.error(f'Ошибка применения параметров PSN: {e}')
            raise

    def turn_off_pna(self):
        """Выключение PNA"""
        try:
            if self.pna:
                self.pna.set_output(False)
                logger.info('PNA выключен')
        except Exception as e:
            logger.error(f"Ошибка при выключении PNA: {e}")
    
    def create_console_with_log_level(self, parent_layout, console_height=180):
        """
        Создает консоль с выбором уровня логов и добавляет в указанный layout.
        Возвращает (console_widget, log_handler) для дальнейшего использования.
        
        Args:
            parent_layout: Layout куда добавить консоль
            console_height: Высота консоли в пикселях (по умолчанию 200)
        """
        # Создаем контейнер для консоли и контролов
        console_container = QtWidgets.QWidget()
        console_layout = QtWidgets.QVBoxLayout(console_container)
        console_layout.setContentsMargins(0, 0, 0, 0)
        console_layout.setSpacing(3)
        
        # Панель с выбором уровня логов
        log_control_panel = QtWidgets.QWidget()
        log_control_layout = QtWidgets.QHBoxLayout(log_control_panel)
        log_control_layout.setContentsMargins(0, 0, 0, 0)
        log_control_layout.setSpacing(8)
        
        log_level_label = QtWidgets.QLabel("Уровень логов:")
        log_control_layout.addWidget(log_level_label)
        
        log_level_combo = QtWidgets.QComboBox()
        log_level_combo.addItems(['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'])
        log_level_combo.setCurrentText('DEBUG')
        log_level_combo.setToolTip('Выберите минимальный уровень логов для отображения в консоли')
        log_control_layout.addWidget(log_level_combo)
        
        # Кнопка очистки консоли
        clear_console_btn = QtWidgets.QPushButton('Очистить консоль')
        clear_console_btn.setMaximumWidth(150)
        log_control_layout.addWidget(clear_console_btn)
        
        log_control_layout.addStretch()
        
        console_layout.addWidget(log_control_panel)
        
        # Сама консоль
        console = QtWidgets.QTextEdit()
        console.setReadOnly(True)
        console.setFixedHeight(console_height)
        
        # Улучшенный читаемый шрифт для консоли
        console_font = QtGui.QFont("Consolas")
        console_font.setPointSize(10)
        console_font.setStyleHint(QtGui.QFont.Monospace)
        console.setFont(console_font)
        
        # Стиль консоли - светлый фон, читаемый текст
        console.setStyleSheet("""
            QTextEdit {
                background-color: #FFFFFF;
                color: #2C2C2C;
                border: 1px solid #CCCCCC;
                border-radius: 3px;
                padding: 6px;
                font-family: 'Consolas', 'Courier New', 'Monaco', monospace;
                font-size: 10pt;
                line-height: 1.5;
            }
        """)
        
        console_layout.addWidget(console)
        
        # Добавляем контейнер в родительский layout (без stretch для фиксированной высоты)
        parent_layout.addWidget(console_container)
        
        # Создаем обработчик логов
        log_handler = QTextEditLogHandler(console)
        
        # Подключаем изменение уровня логов
        def on_log_level_changed(level):
            log_handler.set_min_level(level)
            logger.info(f'Уровень логов консоли изменен на: {level}')
        
        log_level_combo.currentTextChanged.connect(on_log_level_changed)
        
        # Подключаем очистку консоли
        clear_console_btn.clicked.connect(console.clear)
        
        return console, log_handler, log_level_combo

    def apply_parsed_settings(self):
        """Применение параметров PNA настроек к интерфейсу"""
        try:
            polarity = self.pna.get_polarity_trig()
            logger.info(f'Trig polarity={polarity}')
            if polarity:
                text = 'Positive' if 'POS' in polarity else 'Negative'
                index = self.trig_polarity.findText(text)
                if index >= 0:
                    self.trig_polarity.setCurrentIndex(index)

            pulse_source = self.pna.get_pulse_source()
            logger.info(f'Pulse source={pulse_source}')
            if pulse_source:
                text = 'Internal' if 'Internal' in pulse_source else 'External'
                index = self.pulse_source.findText(text)
                if index >= 0:
                    self.pulse_source.setCurrentIndex(index)

            s_param = self.pna.get_s_param()
            logger.info(f'S_PARAM={s_param}')
            if s_param:
                index = self.s_param_combo.findText(s_param)
                if index >= 0:
                    self.s_param_combo.setCurrentIndex(index)

            power1 = self.pna.get_power(1)
            power2 = self.pna.get_power(2)

            if s_param.lower() == 's12':
                self.pna_power.setValue(power2)
            else:
                self.pna_power.setValue(power1)

            freq_start = self.pna.get_start_freq()
            if freq_start:
                self.pna_start_freq.setValue(int(freq_start/10**6))

            freq_stop = self.pna.get_stop_freq()
            if freq_stop:
                self.pna_stop_freq.setValue(int(freq_stop/10**6))

            points = self.pna.get_amount_of_points()
            if points:
                index = self.pna_number_of_points.findText(str(int(points)))
                if index >= 0:
                    self.pna_number_of_points.setCurrentIndex(index)

            pulse_mode = self.pna.get_pulse_mode()
            if pulse_mode:
                index = self.pulse_mode_combo.findText(pulse_mode)
                if index >= 0:
                    self.pulse_mode_combo.setCurrentIndex(index)

            pna_pulse_width = self.pna.get_pulse_width()
            if pna_pulse_width:
                self.pulse_width.setValue(float(pna_pulse_width) * 10 ** 6)

            pna_pulse_period = self.pna.get_period()
            if pna_pulse_period:
                self.pulse_period.setValue(float(pna_pulse_period) * 10 ** 6)

        except Exception as e:
            logger.error(f'Ошибка при применении настроек к интерфейсу: {e}')


    def disconnect_all_devices(self):
        """Отключает все подключенные устройства"""
        devices_to_disconnect = []
        
        # Проверяем и отключаем MA
        if self.ma and self.ma.connection:
            try:
                self.ma.disconnect()
                self.ma = None
                if hasattr(self, 'ma_connect_btn'):
                    self.set_button_connection_state(self.ma_connect_btn, False)
                    self.ma_connect_btn.setText('МА')
                devices_to_disconnect.append('МА')
            except Exception as e:
                logger.error(f"Ошибка отключения МА: {e}")
        
        # Проверяем и отключаем PNA
        if self.pna and self.pna.connection:
            try:
                self.pna.disconnect()
                self.pna = None
                if hasattr(self, 'pna_connect_btn'):
                    self.set_button_connection_state(self.pna_connect_btn, False)
                devices_to_disconnect.append('PNA')
            except Exception as e:
                logger.error(f"Ошибка отключения PNA: {e}")
        
        # Проверяем и отключаем PSN
        if self.psn and self.psn.connection:
            try:
                self.psn.disconnect()
                self.psn = None
                if hasattr(self, 'psn_connect_btn'):
                    self.set_button_connection_state(self.psn_connect_btn, False)
                devices_to_disconnect.append('PSN')
            except Exception as e:
                logger.error(f"Ошибка отключения PSN: {e}")
        
        # Проверяем и отключаем Trigger
        if self.trigger is not None and getattr(self.trigger, 'connection', None) is not None:
            try:
                self.trigger.close()
                self.trigger = None
                if hasattr(self, 'gen_connect_btn'):
                    self.set_button_connection_state(self.gen_connect_btn, False)
                devices_to_disconnect.append('Устройство синхронизации')
            except Exception as e:
                logger.error(f"Ошибка отключения устройства синхронизации: {e}")
        
        # Проверяем и отключаем AFAR
        if self.afar and self.afar.connection:
            try:
                self.afar.disconnect()
                self.afar = None
                if hasattr(self, 'afar_connect_btn'):
                    self.set_button_connection_state(self.afar_connect_btn, False)
                devices_to_disconnect.append('АФАР')
            except Exception as e:
                logger.error(f"Ошибка отключения АФАР: {e}")
        
        if devices_to_disconnect:
            logger.info(f"Отключены устройства: {', '.join(devices_to_disconnect)}")
        else:
            logger.debug("Нет подключенных устройств для отключения")

    def update_scanner_offset(self):
        """Обновление смещений сканера (для перемера)"""
        if not self.psn or not self.coord_system:
            return
            
        try:
            x_offset = self.coord_system.x_offset
            y_offset = self.coord_system.y_offset
            self.psn.set_offset(x_offset, y_offset)
            logger.info(f'Смещения PSN обновлены (x={x_offset}, y={y_offset})')
        except Exception as e:
            logger.error(f'Ошибка обновления смещений PSN: {e}')
