from PyQt5 import QtWidgets, QtCore, QtGui
from PyQt5.QtGui import QTextCursor
from PyQt5.QtWidgets import QMessageBox
from loguru import logger
import threading
from core.devices.trigger_box import E5818Config

from core.workers.device_connection_worker import DeviceConnectionWorker


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


class BaseMeasurementWidget(QtWidgets.QWidget):
    """Базовый класс для всех виджетов измерений"""
    
    # Общие сигналы
    device_connection_started = QtCore.pyqtSignal(str)  # device_name
    device_connection_finished = QtCore.pyqtSignal(str, bool, str)  # device_name, success, message
    error_signal = QtCore.pyqtSignal(str, str)  # title, message
    buttons_enabled_signal = QtCore.pyqtSignal(bool)  # enabled
    
    def __init__(self):
        super().__init__()
        
        # Общие переменные для устройств
        self.ma = None
        self.pna = None
        self.psn = None
        self.trigger = None
        
        # Потоки для асинхронного подключения к устройствам
        self._ma_connection_thread = None
        self._pna_connection_thread = None
        self._psn_connection_thread = None
        self._trigger_connection_thread = None
        
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

        # Проверяем, не идет ли уже подключение
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
        visa_timeout_ms = int(self.device_settings.get('trigger_visa_timeout_ms', 2000))

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
                logger=lambda m: logger.debug(f"E5818 | {m}")
            )
        }
        
        self._trigger_connection_thread = DeviceConnectionWorker('Trigger', connection_params)
        self._trigger_connection_thread.connection_finished.connect(self._on_trigger_connection_finished)
        self.device_connection_started.emit('Trigger')
        self._trigger_connection_thread.start()
    
    # Обработчики завершения подключения к конкретным устройствам
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
