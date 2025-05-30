from PyQt5 import QtWidgets, QtCore, QtGui
from PyQt5.QtGui import QTextCursor
from loguru import logger
import sys
import threading
import numpy as np
from core.devices.ma import MA
from core.devices.pna import PNA
from core.devices.psn import PSN
from core.measurements.check.check_ma import CheckMA
from core.common.enums import Channel, Direction
from core.common.coordinate_system import CoordinateSystemManager

class QTextEditLogHandler(QtCore.QObject):
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

class CheckMaWidget(QtWidgets.QWidget):
    def __init__(self):
        super().__init__()
        
        # Инициализация менеджера систем координат
        self.coord_system_manager = CoordinateSystemManager("config/coordinate_systems.json")
        self.coord_system = None
        
        self.btn_style_disconnected = '''
            QPushButton {
                background: #e74c3c;
                color: white;
                border-radius: 7px;
                border: 1px solid #666;
                padding: 5px;
                font-size: 14px;
            }
            QPushButton:hover {
                background: #c0392b;
            }
        '''
        
        self.btn_style_connected = '''
            QPushButton {
                background: #2ecc40;
                color: white;
                border-radius: 7px;
                border: 1px solid #666;
                padding: 5px;
                font-size: 14px;
            }
            QPushButton:hover {
                background: #27ae60;
            }
        '''

        self.layout = QtWidgets.QHBoxLayout(self)

        # --- Левая панель ---
        self.left_panel = QtWidgets.QWidget()
        self.left_panel.setFixedWidth(400)
        self.left_layout = QtWidgets.QVBoxLayout(self.left_panel)
        self.layout.addWidget(self.left_panel)

        # --- Правая панель (широкая) ---
        self.right_panel = QtWidgets.QWidget()
        self.right_layout = QtWidgets.QVBoxLayout(self.right_panel)
        self.layout.addWidget(self.right_panel, stretch=3)

        # --- Блок подключения устройств ---
        self.connect_group = QtWidgets.QGroupBox('Подключение устройств')
        self.connect_layout = QtWidgets.QVBoxLayout(self.connect_group)
        self.connect_layout.setContentsMargins(10, 10, 10, 10)
        self.connect_layout.setSpacing(10)

        # PNA
        pna_widget = QtWidgets.QWidget()
        pna_layout = QtWidgets.QHBoxLayout(pna_widget)
        pna_layout.setContentsMargins(0, 0, 0, 0)
        self.pna_connect_btn = QtWidgets.QPushButton('Анализатор')
        self.pna_connect_btn.setMinimumHeight(40)
        self.pna_connect_btn.setStyleSheet(self.btn_style_disconnected)
        pna_layout.addWidget(self.pna_connect_btn)
        self.connect_layout.addWidget(pna_widget)

        # PSN
        psn_widget = QtWidgets.QWidget()
        psn_layout = QtWidgets.QHBoxLayout(psn_widget)
        psn_layout.setContentsMargins(0, 0, 0, 0)
        self.psn_connect_btn = QtWidgets.QPushButton('Сканер')
        self.psn_connect_btn.setMinimumHeight(40)
        self.psn_connect_btn.setStyleSheet(self.btn_style_disconnected)
        psn_layout.addWidget(self.psn_connect_btn)
        self.connect_layout.addWidget(psn_widget)

        # MA
        ma_widget = QtWidgets.QWidget()
        ma_layout = QtWidgets.QHBoxLayout(ma_widget)
        ma_layout.setContentsMargins(0, 0, 0, 0)
        self.ma_connect_btn = QtWidgets.QPushButton('МА')
        self.ma_connect_btn.setMinimumHeight(40)
        self.ma_connect_btn.setStyleSheet(self.btn_style_disconnected)
        ma_layout.addWidget(self.ma_connect_btn)

        self.connect_layout.addWidget(ma_widget)
        self.left_layout.addWidget(self.connect_group)

        # --- Tabs для параметров устройств и измерения ---
        self.param_tabs = QtWidgets.QTabWidget()
        
        # MA tab
        self.ma_tab = QtWidgets.QWidget()
        self.ma_tab_layout = QtWidgets.QFormLayout(self.ma_tab)
        self.ma_tab_layout.addRow('Номер МА:', QtWidgets.QLineEdit())

        self.ma_addr_combo = QtWidgets.QComboBox()
        self.ma_addr_combo.addItems([str(i) for i in range(1, 41)])
        self.ma_tab_layout.addRow('Адрес БУ:', self.ma_addr_combo)
        
        # Выбор канала
        self.channel_combo = QtWidgets.QComboBox()
        self.channel_combo.addItems(['Приемник', 'Передатчик'])
        self.ma_tab_layout.addRow('Канал:', self.channel_combo)
        
        # Выбор поляризации
        self.direction_combo = QtWidgets.QComboBox()
        self.direction_combo.addItems(['Горизонтальная', 'Вертикальная'])
        self.ma_tab_layout.addRow('Поляризация:', self.direction_combo)
        
        self.param_tabs.addTab(self.ma_tab, 'MA')
        
        # PNA tab
        self.pna_tab = QtWidgets.QWidget()
        self.pna_tab_layout = QtWidgets.QFormLayout(self.pna_tab)
        self.pna_tab_layout.addRow('S-параметр:', QtWidgets.QComboBox())
        self.pna_tab_layout.addRow('Входная мощность:', QtWidgets.QDoubleSpinBox())
        self.pna_tab_layout.addRow('Нач. частота (Гц):', QtWidgets.QSpinBox())
        self.pna_tab_layout.addRow('Кон. частота (Гц):', QtWidgets.QSpinBox())
        self.pna_tab_layout.addRow('Точек:', QtWidgets.QSpinBox())
        self.pna_tab_layout.addRow('Файл настроек:', QtWidgets.QLineEdit())
        self.param_tabs.addTab(self.pna_tab, 'PNA')
        
        # Meas tab
        self.meas_tab = QtWidgets.QWidget()
        self.meas_tab_layout = QtWidgets.QFormLayout(self.meas_tab)
        self.meas_tab_layout.addRow('Номер ППМ:', QtWidgets.QSpinBox())
        self.meas_tab_layout.addRow('Шаг:', QtWidgets.QSpinBox())
        self.meas_tab_layout.addRow('Кол-во точек:', QtWidgets.QSpinBox())
        
        # Добавляем выбор системы координат
        self.coord_system_combo = QtWidgets.QComboBox()
        self.coord_system_combo.addItems(self.coord_system_manager.get_system_names())
        self.meas_tab_layout.addRow('Система координат:', self.coord_system_combo)
        
        self.param_tabs.addTab(self.meas_tab, 'Meas')
        self.left_layout.addWidget(self.param_tabs, 1)

        # --- Кнопки управления ---
        self.apply_btn = QtWidgets.QPushButton('Применить параметры')
        self.left_layout.addWidget(self.apply_btn)
        self.btns_layout = QtWidgets.QHBoxLayout()
        self.pause_btn = QtWidgets.QPushButton('Пауза')
        self.stop_btn = QtWidgets.QPushButton('Стоп')
        self.start_btn = QtWidgets.QPushButton('Старт')
        self.btns_layout.addWidget(self.pause_btn)
        self.btns_layout.addWidget(self.stop_btn)
        self.btns_layout.addWidget(self.start_btn)
        self.left_layout.addLayout(self.btns_layout)
        self.left_layout.addStretch()

        # --- Таблица результатов ---
        self.results_table = QtWidgets.QTableWidget()
        self.results_table.setColumnCount(12)
        self.results_table.setHorizontalHeaderLabels(['ППМ', 
                                                      'Амплитуда', 
                                                      'Фаза', 
                                                      'Статус амплитуды', 
                                                      'Статус фазы', 
                                                      'Дельта ФВ', 
                                                      'ФВ 5,625', 
                                                      'ФВ 11,25', 
                                                      'ФВ 22,5',
                                                      'ФВ 45',
                                                      'ФВ 90',
                                                      'ФВ 180'])
        self.right_layout.addWidget(self.results_table, stretch=2)

        # --- Консоль логов ---
        self.console = QtWidgets.QTextEdit()
        self.console.setReadOnly(True)
        self.console.setStyleSheet('background: #fff; color: #000; font-family: "PT Mono";')
        self.console.setFixedHeight(200)
        self.right_layout.addWidget(self.console, stretch=1)

        # --- Логирование ---
        self.log_handler = QTextEditLogHandler(self.console)
        logger.add(self.log_handler, format="{time:HH:mm:ss} | {level} | {message}")

        # --- Устройства и параметры ---
        self.ma = None
        self.pna = None
        self.psn = None
        self._check_thread = None
        self._stop_flag = threading.Event()
        self._pause_flag = threading.Event()

        # --- Сигналы ---
        self.ma_connect_btn.clicked.connect(self.connect_ma)
        self.pna_connect_btn.clicked.connect(self.connect_pna)
        self.psn_connect_btn.clicked.connect(self.connect_psn)
        self.apply_btn.clicked.connect(self.apply_params)
        self.start_btn.clicked.connect(self.start_check)
        self.stop_btn.clicked.connect(self.stop_check)
        self.pause_btn.clicked.connect(self.pause_check)

        self.set_buttons_enabled(True)
        self.device_settings = {}

    def set_buttons_enabled(self, enabled: bool):
        """Управляет доступностью кнопок"""
        self.ma_connect_btn.setEnabled(enabled)
        self.pna_connect_btn.setEnabled(enabled)
        self.psn_connect_btn.setEnabled(enabled)
        self.apply_btn.setEnabled(enabled)
        self.start_btn.setEnabled(enabled)
        self.stop_btn.setEnabled(not enabled)
        self.pause_btn.setEnabled(not enabled)

    def apply_params(self):
        """Сохраняет параметры из вкладок"""
        # MA
        self.bu_addr = self.ma_addr_combo.currentText()
        self.ma_num = self.ma_tab_layout.itemAt(1).widget().text()
        self.channel = self.channel_combo.currentText()
        self.direction = self.direction_combo.currentText()
        # PNA
        self.s_param = self.pna_tab_layout.itemAt(1).widget().currentText()
        self.power = self.pna_tab_layout.itemAt(3).widget().value()
        self.freq_start = self.pna_tab_layout.itemAt(5).widget().value()
        self.freq_stop = self.pna_tab_layout.itemAt(7).widget().value()
        self.freq_points = self.pna_tab_layout.itemAt(9).widget().value()
        self.settings_file = self.pna_tab_layout.itemAt(11).widget().text()
        # Meas
        self.ppm_num = self.meas_tab_layout.itemAt(1).widget().value()
        self.step = self.meas_tab_layout.itemAt(3).widget().value()
        self.n_points = self.meas_tab_layout.itemAt(5).widget().value()
        # Система координат
        coord_system_name = self.coord_system_combo.currentText()
        self.coord_system = self.coord_system_manager.get_system_by_name(coord_system_name)
        logger.info('Параметры успешно применены')

    def start_check(self):
        """Запускает процесс проверки"""
        if not (self.ma and self.pna and self.psn):
            logger.error('Сначала подключите все устройства!')
            return
        
        self._stop_flag.clear()
        self._pause_flag.clear()
        self.pause_btn.setText('Пауза') # Reset pause button text
        
        self.results_table.clearContents()
        self.results_table.setRowCount(32)  # 32 ППМ
        
        self.set_buttons_enabled(False)
        logger.info("Запуск проверки МА...")
        self._check_thread = threading.Thread(target=self._run_check, daemon=True)
        self._check_thread.start()

    def pause_check(self):
        """Ставит проверку на паузу"""
        if self._pause_flag.is_set():
            self._pause_flag.clear()
            self.pause_btn.setText('Пауза')
            logger.info('Проверка возобновлена')
        else:
            self._pause_flag.set()
            self.pause_btn.setText('Продолжить')
            logger.info('Проверка приостановлена')

    def stop_check(self):
        """Останавливает процесс проверки"""
        logger.info('Остановка проверки...')
        self._stop_flag.set()
        if self._check_thread and self._check_thread.is_alive():
            self._check_thread.join(timeout=2)
            if self._check_thread.is_alive():
                logger.warning("Поток проверки не завершился вовремя.")
        self._pause_flag.clear() # Ensure pause is cleared for next run
        self.pause_btn.setText('Пауза') # Reset pause button text
        self.set_buttons_enabled(True)
        logger.info('Проверка остановлена.')

    def _run_check(self):
        """Выполняет проверку МА"""
        try:
            channel = Channel.Receiver if self.channel_combo.currentText()== 'Приемник' else Channel.Transmitter
            direction = Direction.Horizontal if self.direction_combo.currentText()=='Горизонтальная' else Direction.Vertical
            logger.info(f'Используем канал: {channel.value}, поляризация: {direction.value}')

            if self.psn and self.device_settings:
                try:
                    self.psn.preset()
                    self.psn.preset_axis(0)
                    self.psn.preset_axis(1)

                    if self.coord_system:
                        x_offset = self.coord_system.x_offset
                        y_offset = self.coord_system.y_offset
                    else:
                        x_offset = float(self.device_settings.get('psn_x_offset', 0))
                        y_offset = float(self.device_settings.get('psn_y_offset', 0))
                    
                    self.psn.set_offset(x_offset, y_offset)
                    speed_x = int(self.device_settings.get('psn_speed_x', 0))
                    speed_y = int(self.device_settings.get('psn_speed_y', 0))
                    acc_x = int(self.device_settings.get('psn_acc_x', 0))
                    acc_y = int(self.device_settings.get('psn_acc_y', 0))
                    self.psn.set_speed(0, speed_x)
                    self.psn.set_speed(1, speed_y)
                    self.psn.set_acc(0, acc_x)
                    self.psn.set_acc(1, acc_y)
                    logger.info(f'Параметры PSN успешно применены перед измерением (смещения: x={x_offset}, y={y_offset})')
                except Exception as e:
                    logger.error(f'Ошибка применения параметров PSN перед измерением: {e}')

            # Создаем экземпляр класса проверки, передавая события
            check = CheckMA(ma=self.ma, psn=self.psn, pna=self.pna, 
                          stop_event=self._stop_flag, pause_event=self._pause_flag)
            
            # Запускаем проверку
            results = check.start(channel=channel, direction=direction)
            
            # Обновляем таблицу результатов
            for ppm_num, (result, measurements, fv_data) in results:
                if self._stop_flag.is_set():
                    logger.info('Обновление таблицы остановлено пользователем')
                    break

                while self._pause_flag.is_set() and not self._stop_flag.is_set():
                    QtCore.QThread.msleep(100)

                amp, phase = measurements
                row = ppm_num - 1
                
                # Обновляем номер ППМ
                self.results_table.setItem(row, 0, QtWidgets.QTableWidgetItem(str(ppm_num)))
                
                # Обновляем амплитуду и фазу
                if np.isnan(amp) or np.isnan(phase):
                    self.results_table.setItem(row, 1, QtWidgets.QTableWidgetItem("---"))
                    self.results_table.setItem(row, 2, QtWidgets.QTableWidgetItem("---"))
                else:
                    self.results_table.setItem(row, 1, QtWidgets.QTableWidgetItem(f"{amp:.2f}"))
                    self.results_table.setItem(row, 2, QtWidgets.QTableWidgetItem(f"{phase:.1f}"))
                
                # Обновляем статусы
                status = "OK" if result else "FAIL"
                status_item = QtWidgets.QTableWidgetItem(status)
                if result:
                    status_item.setBackground(QtGui.QColor("#2ecc40"))
                else:
                    status_item.setBackground(QtGui.QColor("#e74c3c"))
                status_item.setForeground(QtGui.QColor("white"))
                self.results_table.setItem(row, 3, status_item)
                
                # Обновляем значения ФВ
                if not result and fv_data:  # Если ППМ не прошел проверку и есть данные ФВ
                    try:
                        # Заполняем значения ФВ в таблицу
                        for i, value in enumerate(fv_data['values']):
                            self.results_table.setItem(row, i + 5, QtWidgets.QTableWidgetItem(f"{value:.1f}"))
                        
                        # Заполняем дельту ФВ
                        if 'delta' in fv_data:
                            self.results_table.setItem(row, 4, QtWidgets.QTableWidgetItem(f"{fv_data['delta']:.1f}"))
                        else:
                            self.results_table.setItem(row, 4, QtWidgets.QTableWidgetItem("---"))
                    except Exception as e:
                        logger.error(f'Ошибка при обновлении значений ФВ для ППМ {ppm_num}: {e}')
                        # В случае ошибки ставим прочерки
                        for i in range(6):
                            self.results_table.setItem(row, i + 5, QtWidgets.QTableWidgetItem("---"))
                        self.results_table.setItem(row, 4, QtWidgets.QTableWidgetItem("---"))
                else:
                    # Если ППМ прошел проверку или нет данных ФВ, ставим прочерки
                    for i in range(6):
                        self.results_table.setItem(row, i + 5, QtWidgets.QTableWidgetItem("---"))
                    self.results_table.setItem(row, 4, QtWidgets.QTableWidgetItem("---"))
                
                # Принудительно обновляем таблицу
                self.results_table.viewport().update()
                QtCore.QCoreApplication.processEvents()
                
                QtCore.QThread.msleep(50) # Маленькая задержка для отзывчивости UI при обновлении таблицы

            if not self._stop_flag.is_set():
                 logger.info('Проверка завершена успешно.')

        except Exception as e:
            logger.error(f'Ошибка проверки: {e}')
        finally:
            if not self.start_btn.isEnabled():
                self.set_buttons_enabled(True)
                self.pause_btn.setText('Пауза')

    def connect_ma(self):
        """Подключает/отключает МА"""
        if self.ma and self.ma.connection:
            try:
                self.ma.disconnect()
                self.ma = None
                self.ma_connect_btn.setStyleSheet(self.btn_style_disconnected)
                logger.info('МА успешно отключен')
                return
            except Exception as e:
                logger.error(f'Ошибка отключения МА: {e}')
                return

        addr = self.ma_addr_combo.currentText()
        com_port = self.device_settings.get('ma_com_port', '')
        mode = self.device_settings.get('ma_mode', 0)

        try:
            self.ma = MA(bu_addr=int(addr), ma_num=1, com_port=com_port, mode=mode)
            self.ma.connect()
            self.ma_connect_btn.setStyleSheet(self.btn_style_connected)
            logger.info(f'МА успешно подключен {'' if mode == 0 else "(тестовый режим)"}')
        except Exception as e:
            self.ma = None
            self.ma_connect_btn.setStyleSheet(self.btn_style_disconnected)
            logger.error(f'Ошибка подключения МА: {e}')

    def connect_pna(self):
        """Подключает/отключает PNA"""
        if self.pna and self.pna.connection:
            try:
                self.pna.disconnect()
                self.pna = None
                self.pna_connect_btn.setStyleSheet(self.btn_style_disconnected)
                logger.info('PNA успешно отключен')
                return
            except Exception as e:
                logger.error(f'Ошибка отключения PNA: {e}')
                return

        ip = self.device_settings.get('pna_ip', '')
        port = int(self.device_settings.get('pna_port', ''))
        mode = self.device_settings.get('pna_mode', 0)

        try:
            self.pna = PNA(ip=ip, port=port, mode=mode)
            self.pna.connect()
            self.pna_connect_btn.setStyleSheet(self.btn_style_connected)
            logger.info(f'PNA успешно подключен {'' if mode == 0 else "(тестовый режим)"}')
        except Exception as e:
            self.pna = None
            self.pna_connect_btn.setStyleSheet(self.btn_style_disconnected)
            logger.error(f'Ошибка подключения PNA: {e}')

    def connect_psn(self):
        """Подключает/отключает PSN"""
        if self.psn and self.psn.connection:
            try:
                self.psn.disconnect()
                self.psn = None
                self.psn_connect_btn.setStyleSheet(self.btn_style_disconnected)
                logger.info('PSN успешно отключен')
                return
            except Exception as e:
                logger.error(f'Ошибка отключения PSN: {e}')
                return

        ip = self.device_settings.get('psn_ip', '')
        port = self.device_settings.get('psn_port', '')
        mode = self.device_settings.get('psn_mode', 0)

        try:
            self.psn = PSN(ip=ip, port=port, mode=mode)
            self.psn.connect()
            self.psn_connect_btn.setStyleSheet(self.btn_style_connected)
            logger.info(f'PSN успешно подключен {'' if mode == 0 else "(тестовый режим)"}')
        except Exception as e:
            self.psn = None
            self.psn_connect_btn.setStyleSheet(self.btn_style_disconnected)
            logger.error(f'Ошибка подключения PSN: {e}')

    def set_device_settings(self, settings: dict):
        """Сохраняет параметры устройств из настроек"""
        self.device_settings = settings or {} 