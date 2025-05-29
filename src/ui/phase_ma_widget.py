from PyQt5 import QtWidgets, QtCore
from PyQt5.QtGui import QTextCursor
from loguru import logger
import sys
import threading
import numpy as np
import pyqtgraph as pg
import serial.tools.list_ports
from core.devices.ma import MA
from core.devices.pna import PNA
from core.devices.psn import PSN
from utils.logger import setup_logging
from core.measurements.phase.phase_ma import PhaseMaMeas
from core.common.enums import Channel, Direction
from core.common.coordinate_system import CoordinateSystemManager
from pyqtgraph.Qt import QtGui
import pyqtgraph.opengl as gl
from pyqtgraph.colormap import ColorMap

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

class PhaseMaWidget(QtWidgets.QWidget):
    # Сигнал для обновления UI из потока измерений
    update_gui_signal = QtCore.pyqtSignal(int, int, float, float)
    
    def __init__(self):
        super().__init__()
        
        # Подключение сигнала к слоту
        self.update_gui_signal.connect(self.on_measurement_update)

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
        self.pna_connect_btn.setStyleSheet(self.btn_style_disconnected) # Initial style
        pna_layout.addWidget(self.pna_connect_btn)
        self.connect_layout.addWidget(pna_widget)

        # PSN
        psn_widget = QtWidgets.QWidget()
        psn_layout = QtWidgets.QHBoxLayout(psn_widget)
        psn_layout.setContentsMargins(0, 0, 0, 0)
        self.psn_connect_btn = QtWidgets.QPushButton('Сканер')
        self.psn_connect_btn.setMinimumHeight(40)
        self.psn_connect_btn.setStyleSheet(self.btn_style_disconnected) # Initial style
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
        self.ma_num_edit = QtWidgets.QLineEdit()
        self.ma_tab_layout.addRow('Номер МА:', self.ma_num_edit)

        self.ma_addr_combo = QtWidgets.QComboBox()
        self.ma_addr_combo.addItems([str(i) for i in range(1, 41)])
        self.ma_tab_layout.addRow('Адрес БУ:', self.ma_addr_combo)
        
        self.channel_combo = QtWidgets.QComboBox()
        self.channel_combo.addItems(['Receiver', 'Transmitter'])
        self.ma_tab_layout.addRow('Канал:', self.channel_combo)
        
        self.direction_combo = QtWidgets.QComboBox()
        self.direction_combo.addItems(['Horizontal', 'Vertical'])
        self.ma_tab_layout.addRow('Поляризация:', self.direction_combo)
        
        self.param_tabs.addTab(self.ma_tab, 'MA')
        
        # PNA tab (simplified for brevity, assuming it exists as per context)
        self.pna_tab = QtWidgets.QWidget()
        self.pna_tab_layout = QtWidgets.QFormLayout(self.pna_tab)
        self.pna_tab_layout.addRow('S-параметр:', QtWidgets.QComboBox())
        self.pna_tab_layout.addRow('Входная мощность:', QtWidgets.QDoubleSpinBox())
        self.pna_tab_layout.addRow('Нач. частота (Гц):', QtWidgets.QSpinBox())
        self.pna_tab_layout.addRow('Кон. частота (Гц):', QtWidgets.QSpinBox())
        self.pna_tab_layout.addRow('Точек:', QtWidgets.QSpinBox())
        self.settings_file_combo = QtWidgets.QComboBox()
        self.pna_tab_layout.addRow('Файл настроек:', self.settings_file_combo)
        self.param_tabs.addTab(self.pna_tab, 'PNA')
        
        # Meas tab
        self.meas_tab = QtWidgets.QWidget()
        self.meas_tab_layout = QtWidgets.QFormLayout(self.meas_tab)
        self.meas_tab_layout.addRow('Номер ППМ:', QtWidgets.QSpinBox())
        self.meas_tab_layout.addRow('Шаг:', QtWidgets.QSpinBox())
        self.meas_tab_layout.addRow('Кол-во точек:', QtWidgets.QSpinBox())
        
        # Добавляем выбор системы координат
        self.coord_system_manager = CoordinateSystemManager()
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

        # --- Графики 2D амплитуды и фазы ---
        self.plot_tabs = QtWidgets.QTabWidget()
        
        # Амплитуда
        self.amp_plot = pg.PlotWidget(title="Амплитуда (2D)")
        self.amp_plot.setBackground('w')
        self.amp_plot.showGrid(x=True, y=True, alpha=0.3)  # Добавляем сетку
        self.amp_img_item = pg.ImageItem()
        self.amp_plot.addItem(self.amp_img_item)
        
        # Фаза
        self.phase_plot = pg.PlotWidget(title="Фаза (2D)")
        self.phase_plot.setBackground('w')
        self.phase_plot.showGrid(x=True, y=True, alpha=0.3)  # Добавляем сетку
        self.phase_img_item = pg.ImageItem()
        self.phase_plot.addItem(self.phase_img_item)
        
        self.plot_tabs.addTab(self.amp_plot, "Амплитуда")
        self.plot_tabs.addTab(self.phase_plot, "Фаза")
        self.right_layout.addWidget(self.plot_tabs, stretch=5)

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
        self._meas_thread = None
        self._stop_flag = threading.Event()
        self._pause_flag = threading.Event()
        
        self.amp_field = np.full((4,8), np.nan)
        self.phase_field = np.full((4,8), np.nan)
        self.x_cords = [-42, -14, 14, 42]
        self.y_cords = [7.7, 5.5, 3.3, 1.1, -1.1, -3.3, -5.5, -7.7]

        # --- Сигналы ---
        self.ma_connect_btn.clicked.connect(self.connect_ma)
        self.pna_connect_btn.clicked.connect(self.connect_pna)
        self.psn_connect_btn.clicked.connect(self.connect_psn)
        self.apply_btn.clicked.connect(self.apply_params)
        self.start_btn.clicked.connect(self.start_phase_meas)
        self.stop_btn.clicked.connect(self.stop_phase_meas)
        self.pause_btn.clicked.connect(self.pause_phase_meas)

        self.set_buttons_enabled(True)
        self.device_settings = {}


    def update_pna_settings_files(self):
        """Обновляет список файлов настроек PNA в ComboBox"""
        if not self.pna or not self.pna.connection:
            return
        try:
            # Получаем список файлов из PNA
            files = self.pna.get_files_in_dir(folder='C:\\Users\\Public\\Documents\\Network Analyzer\\')
            # Фильтруем только .csa файлы
            csa_files = [f for f in files if f.lower().endswith('.csa')]
            # Обновляем ComboBox
            self.settings_file_combo.clear()
            self.settings_file_combo.addItems(csa_files)
            logger.info(f'Список файлов настроек PNA обновлен: {len(csa_files)} файлов')
        except Exception as e:
            logger.error(f'Ошибка при получении списка файлов настроек PNA: {e}')

    def set_buttons_enabled(self, enabled: bool):
        # Управляет доступностью всех кнопок кроме стоп
        self.ma_connect_btn.setEnabled(enabled)
        self.pna_connect_btn.setEnabled(enabled)
        self.psn_connect_btn.setEnabled(enabled)
        self.apply_btn.setEnabled(enabled)
        self.start_btn.setEnabled(enabled)
        self.stop_btn.setEnabled(not enabled)

    def apply_params(self):
        # Сохраняем параметры из вкладок в self
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
        self.settings_file = self.settings_file_combo.currentText()
        # Meas
        self.ppm_num = self.meas_tab_layout.itemAt(1).widget().value()
        self.step = self.meas_tab_layout.itemAt(3).widget().value()
        self.n_points = self.meas_tab_layout.itemAt(5).widget().value()
        # Система координат
        coord_system_name = self.coord_system_combo.currentText()
        self.coord_system = self.coord_system_manager.get_system_by_name(coord_system_name)
        logger.info('Параметры успешно применены')

    def start_phase_meas(self):
        if not (self.ma and self.pna and self.psn):
            logger.error('Сначала подключите все устройства!')
            return
        self.set_buttons_enabled(False)
        self._stop_flag.clear()
        self.amp_field = np.full((4,8), np.nan)
        self.phase_field = np.full((4,8), np.nan)
        self.amp_plot.clear()
        self.phase_plot.clear()
        self._meas_thread = threading.Thread(target=self._run_phase_ma_real, daemon=True)
        self._meas_thread.start()

    def pause_phase_meas(self):
        """Обработчик нажатия кнопки паузы"""
        if self._pause_flag.is_set():
            logger.info('Возобновление фазировки...')
            self._pause_flag.clear()
            self.pause_btn.setText('Пауза')
        else:
            logger.info('Пауза фазировки...')
            self._pause_flag.set()
            self.pause_btn.setText('Продолжить')

    def _run_phase_ma_real(self):
        try:
            # Применяем параметры PSN перед измерением
            if self.psn and self.device_settings:
                try:
                    self.psn.preset()
                    self.psn.preset_axis(0)
                    self.psn.preset_axis(1)
                    
                    # Используем смещения из выбранной системы координат
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
            
            try:
                channel = Channel[self.channel]
                direction = Direction[self.direction]
                logger.info(f'Используем канал: {channel.value}, поляризация: {direction.value}')
            except KeyError as e:
                logger.error(f'Ошибка при установке канала/поляризации: {e}')
                channel = Channel.Receiver
                direction = Direction.Horizontal
                logger.info('Используем значения по умолчанию: Receiver/Horizontal')
            
            def point_callback(i, j, x, y, amp, phase):
                self.amp_field[i, j] = amp
                self.phase_field[i, j] = phase
                # Используем сигнал вместо invokeMethod
                self.update_gui_signal.emit(i, j, amp, phase)
            
            phase_meas = PhaseMaMeas(
                ma=self.ma,
                psn=self.psn,
                pna=self.pna,
                channel=channel,
                direction=direction,
                point_callback=point_callback,
                stop_flag=self._stop_flag
            )
            logger.info('Запуск фазировки...')
            phase_meas.start()
            logger.info('Фазировка завершена')
        except Exception as e:
            logger.error(f'Ошибка фазировки: {e}')
        finally:
            self.set_buttons_enabled(True)

    @QtCore.pyqtSlot(int, int, float, float)
    def on_measurement_update(self, i, j, amp, phase):
        """Слот для обновления графика при получении новых данных"""
        self.amp_field[i, j] = amp
        self.phase_field[i, j] = phase
        self.update_heatmaps()
        
    @QtCore.pyqtSlot()
    def update_heatmaps(self):
        self.amp_plot.clear()
        self.phase_plot.clear()
        
        # RGB-палитра для амплитуды: синий -> зеленый -> красный
        amp_cmap = ColorMap(pos=[0, 0.5, 1], color=[(0, 0, 255), (0, 255, 0), (255, 0, 0)])
        amp_img = pg.ImageItem(self.amp_field.T)
        amp_img.setColorMap(amp_cmap)
        
        # RGB-палитра для фазы: -180 (красный) -> 0 (синий) -> 180 (зеленый)
        # Нормализуем значения фазы от -180 до 180 в диапазон от 0 до 1
        normalized_phase = np.copy(self.phase_field)
        normalized_phase = (normalized_phase + 180) / 360

        phase_cmap = ColorMap(pos=[0, 0.5, 1], color=[(255, 0, 0), (0, 0, 255), (0, 255, 0)])
        phase_img = pg.ImageItem(normalized_phase.T)
        phase_img.setColorMap(phase_cmap)
        
        self.amp_plot.addItem(amp_img)
        self.phase_plot.addItem(phase_img)
        self.amp_plot.setLimits(xMin=-50, xMax=50, yMin=-10, yMax=10)
        self.phase_plot.setLimits(xMin=-50, xMax=50, yMin=-10, yMax=10)
        self.amp_plot.setAspectLocked()
        self.phase_plot.setAspectLocked()

    def stop_phase_meas(self):
        logger.info('Остановка фазировки...')
        self._stop_flag.set()
        if self._meas_thread and self._meas_thread.is_alive():
            self._meas_thread.join(timeout=2)
        self.set_buttons_enabled(True)


    def connect_ma(self):
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
            self.update_pna_settings_files()
        except Exception as e:
            self.pna = None
            self.pna_connect_btn.setStyleSheet(self.btn_style_disconnected)
            logger.error(f'Ошибка подключения PNA: {e}')

    def connect_psn(self):
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
        """Сохраняет параметры устройств (PSN/PNA) из настроек для последующего применения."""
        self.device_settings = settings or {}
        # Применяем параметры к PSN, если он подключён
        if self.psn:
            try:
                self.psn.preset()
                self.psn.preset_axis(0)
                self.psn.preset_axis(1)
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
                logger.info('Параметры PSN успешно применены')
            except Exception as e:
                logger.error(f'Ошибка применения параметров PSN: {e}')
        # Можно добавить логику для обновления интерфейса, если потребуется 