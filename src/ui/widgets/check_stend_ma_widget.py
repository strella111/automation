from PyQt5 import QtWidgets, QtCore, QtGui
import os
from PyQt5.QtGui import QTextCursor
from PyQt5.QtWidgets import QMessageBox, QStyle
from PyQt5.QtCore import QSize
from loguru import logger
import threading
import numpy as np
from core.devices.ma import MA
from core.devices.pna import PNA
from core.devices.trigger_box import E5818Config, E5818
from core.measurements.check_stend.check_stend import CheckMAStend
from core.common.enums import Channel, Direction

from ui.dialogs.pna_file_dialog import PnaFileDialog
from core.workers.device_connection_worker import DeviceConnectionWorker
from ui.widgets.base_measurement_widget import BaseMeasurementWidget, QTextEditLogHandler



class StendCheckMaWidget(BaseMeasurementWidget):
    update_data_signal = QtCore.pyqtSignal(dict)   # словарь {fv_angle: [A1,P1,...,A32,P32] с относительными фазами}
    update_realtime_signal = QtCore.pyqtSignal(float, int, float, float)  # angle, ppm_index(1..32), amp_abs, phase_rel
    update_lz_signal = QtCore.pyqtSignal(dict)  # {lz: (mean_amp_delta, mean_delay_delta)}
    check_finished_signal = QtCore.pyqtSignal()  # когда проверка завершена

    def __init__(self):
        super().__init__()

        self.layout = QtWidgets.QHBoxLayout(self)

        self.left_panel = QtWidgets.QWidget()
        self.left_panel.setFixedWidth(400)
        self.left_layout = QtWidgets.QVBoxLayout(self.left_panel)
        self.layout.addWidget(self.left_panel)

        self.right_panel = QtWidgets.QWidget()
        self.right_layout = QtWidgets.QVBoxLayout(self.right_panel)
        self.layout.addWidget(self.right_panel, stretch=3)

        self.connect_group = QtWidgets.QGroupBox('Подключение устройств')
        self.connect_layout = QtWidgets.QVBoxLayout(self.connect_group)
        self.connect_layout.setContentsMargins(10, 10, 10, 10)
        self.connect_layout.setSpacing(10)

        pna_widget = QtWidgets.QWidget()
        pna_layout = QtWidgets.QHBoxLayout(pna_widget)
        pna_layout.setContentsMargins(0, 0, 0, 0)
        self.pna_connect_btn = QtWidgets.QPushButton('Анализатор')
        self.pna_connect_btn.setMinimumHeight(40)
        self.set_button_connection_state(self.pna_connect_btn, False)
        pna_layout.addWidget(self.pna_connect_btn)
        self.connect_layout.addWidget(pna_widget)

        gen_widget = QtWidgets.QWidget()
        gen_layout = QtWidgets.QHBoxLayout(gen_widget)
        gen_layout.setContentsMargins(0, 0, 0, 0)
        self.gen_connect_btn = QtWidgets.QPushButton('Устройство синхронизации')
        self.gen_connect_btn.setMinimumHeight(40)
        self.set_button_connection_state(self.gen_connect_btn, False)
        gen_layout.addWidget(self.gen_connect_btn)
        self.connect_layout.addWidget(gen_widget)

        ma_widget = QtWidgets.QWidget()
        ma_layout = QtWidgets.QHBoxLayout(ma_widget)
        ma_layout.setContentsMargins(0, 0, 0, 0)
        self.ma_connect_btn = QtWidgets.QPushButton('МА')
        self.ma_connect_btn.setMinimumHeight(40)
        self.set_button_connection_state(self.ma_connect_btn, False)
        ma_layout.addWidget(self.ma_connect_btn)
        self.connect_layout.addWidget(ma_widget)

        self.left_layout.addWidget(self.connect_group)

        self.param_tabs = QtWidgets.QTabWidget()

        self.ma_tab = QtWidgets.QWidget()
        self.ma_tab_layout = QtWidgets.QFormLayout(self.ma_tab)

        self.channel_combo = QtWidgets.QComboBox()
        self.channel_combo.addItems(['Приемник', 'Передатчик'])
        self.ma_tab_layout.addRow('Канал:', self.channel_combo)

        self.direction_combo = QtWidgets.QComboBox()
        self.direction_combo.addItems(['Горизонтальная', 'Вертикальная'])
        self.ma_tab_layout.addRow('Поляризация:', self.direction_combo)

        self.ma_command_delay = QtWidgets.QDoubleSpinBox()
        self.ma_command_delay.setRange(0.01, 10)
        self.ma_command_delay.setSingleStep(0.01)
        self.ma_command_delay.setValue(0.1)
        self.ma_tab_layout.addRow('Задержка между командами', self.ma_command_delay)

        self.param_tabs.addTab(self.ma_tab, 'Модуль антенный')

        self.pna_tab = QtWidgets.QWidget()
        self.pna_tab_layout = QtWidgets.QFormLayout(self.pna_tab)

        self.s_param_combo = QtWidgets.QComboBox()
        self.s_param_combo.addItems(['S21', 'S12', 'S11', 'S22'])
        self.pna_tab_layout.addRow('S-параметр:', self.s_param_combo)

        self.pna_power = QtWidgets.QDoubleSpinBox()
        self.pna_power.setRange(-20, 18)
        self.pna_power.setSingleStep(1)
        self.pna_power.setDecimals(0)
        self.pna_power.setValue(0)
        self.pna_tab_layout.addRow('Входная мощность (дБм):', self.pna_power)

        self.pna_start_freq = QtWidgets.QSpinBox()
        self.pna_start_freq.setRange(1, 50000)
        self.pna_start_freq.setSingleStep(50)
        self.pna_start_freq.setValue(9300)
        self.pna_start_freq.setSuffix(' МГц')
        self.pna_tab_layout.addRow('Нач. частота:', self.pna_start_freq)

        self.pna_stop_freq = QtWidgets.QSpinBox()
        self.pna_stop_freq.setRange(1, 50000)
        self.pna_stop_freq.setSingleStep(50)
        self.pna_stop_freq.setValue(9800)
        self.pna_stop_freq.setSuffix(' МГц')
        self.pna_tab_layout.addRow('Кон. частота:', self.pna_stop_freq)

        self.pna_number_of_points = QtWidgets.QComboBox()
        self.pna_number_of_points.addItems(['3', '11', '101', '201'])
        self.pna_number_of_points.setCurrentText('11')
        self.pna_tab_layout.addRow('Кол-во точек:', self.pna_number_of_points)


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
        self.load_file_btn.setIconSize(QSize(16, 16))
        self.load_file_btn.setFixedHeight(32)
        self.load_file_btn.clicked.connect(self.open_file_dialog)

        settings_layout.addWidget(self.settings_file_edit, 1)
        settings_layout.addWidget(self.load_file_btn, 0)

        self.pna_tab_layout.addRow('Файл настроек:', settings_layout)
        self.param_tabs.addTab(self.pna_tab, 'Анализатор')

        # --- Вкладка устройства синхронизации (E5818) ---
        self.trig_tab = QtWidgets.QWidget()
        self.trig_tab_layout = QtWidgets.QFormLayout(self.trig_tab)


        self.trig_ttl_channel = QtWidgets.QComboBox()
        self.trig_ttl_channel.addItems(['TTL1', 'TTL2'])
        self.trig_tab_layout.addRow('Канал TTL:', self.trig_ttl_channel)

        self.trig_ext_channel = QtWidgets.QComboBox()
        self.trig_ext_channel.addItems(['EXT1', 'EXT2'])
        self.trig_tab_layout.addRow('Канал EXT:', self.trig_ext_channel)

        self.trig_start_lead = QtWidgets.QDoubleSpinBox()
        self.trig_start_lead.setRange(0.01, 100.000)
        self.trig_start_lead.setDecimals(2)
        self.trig_start_lead.setSingleStep(0.01)
        self.trig_start_lead.setSuffix(' мс')
        self.trig_start_lead.setValue(25.00)
        self.trig_tab_layout.addRow('Задержка старта (lead):', self.trig_start_lead)

        self.trig_pulse_period = QtWidgets.QDoubleSpinBox()
        self.trig_pulse_period.setDecimals(3)
        self.trig_pulse_period.setRange(0, 10000)
        self.trig_pulse_period.setSingleStep(10)
        self.trig_pulse_period.setSuffix(' мкс')
        self.trig_pulse_period.setValue(500.000)
        self.trig_tab_layout.addRow('Период импульса:', self.trig_pulse_period)

        self.trig_post_trigger_delay = QtWidgets.QDoubleSpinBox()
        self.trig_post_trigger_delay.setDecimals(3)
        self.trig_post_trigger_delay.setRange(0.001, 100.000)
        self.trig_post_trigger_delay.setSingleStep(0.1)
        self.trig_post_trigger_delay.setSuffix(' мс')
        self.trig_post_trigger_delay.setValue(1.000)
        self.trig_tab_layout.addRow('Задержка после обратного триггера:', self.trig_post_trigger_delay)

        self.trig_min_alarm_guard = QtWidgets.QDoubleSpinBox()
        self.trig_min_alarm_guard.setRange(0.0, 10e6)
        self.trig_min_alarm_guard.setDecimals(3)
        self.trig_min_alarm_guard.setSingleStep(1)
        self.trig_min_alarm_guard.setSuffix(' мкс')
        self.trig_min_alarm_guard.setValue(100)
        self.trig_tab_layout.addRow('Min ALARM guard:', self.trig_min_alarm_guard)

        self.trig_ext_debounce = QtWidgets.QDoubleSpinBox()
        self.trig_ext_debounce.setRange(0.0, 1000)
        self.trig_ext_debounce.setDecimals(1)
        self.trig_ext_debounce.setSingleStep(1)
        self.trig_ext_debounce.setSuffix(' мс')
        self.trig_ext_debounce.setValue(2.0)
        self.trig_tab_layout.addRow('EXT дебаунс:', self.trig_ext_debounce)

        self.param_tabs.addTab(self.trig_tab, 'Синхронизация')

        self.meas_tab = QtWidgets.QWidget()
        self.meas_tab_layout = QtWidgets.QVBoxLayout(self.meas_tab)
        self.meas_tab_layout.setSpacing(15)
        self.meas_tab_layout.setContentsMargins(15, 15, 15, 15)

        criteria_group = QtWidgets.QGroupBox('Критерии проверки')
        criteria_layout = QtWidgets.QGridLayout(criteria_group)
        criteria_layout.setContentsMargins(15, 15, 15, 15)
        criteria_layout.setSpacing(10)

        criteria_layout.addWidget(QtWidgets.QLabel(""), 0, 0)  # Пустая ячейка
        rx_label = QtWidgets.QLabel("Приемник")
        rx_label.setAlignment(QtCore.Qt.AlignCenter)
        criteria_layout.addWidget(rx_label, 0, 1)

        tx_label = QtWidgets.QLabel("Передатчик")
        tx_label.setAlignment(QtCore.Qt.AlignCenter)
        criteria_layout.addWidget(tx_label, 0, 2)

        criteria_layout.addWidget(QtWidgets.QLabel("Мин. Амплитуда:"), 1, 0)


        # Порог по абсолютной амплитуде (минимально допустимая), отдельно для RX/TX
        self.abs_amp_min_rx = QtWidgets.QDoubleSpinBox()
        self.abs_amp_min_rx.setRange(-200.0, 200.0)
        self.abs_amp_min_rx.setDecimals(2)
        self.abs_amp_min_rx.setSingleStep(0.1)
        self.abs_amp_min_rx.setValue(-5.00)
        self.abs_amp_min_rx.setSuffix(' дБ')
        criteria_layout.addWidget(self.abs_amp_min_rx, 1, 1)

        self.abs_amp_min_tx = QtWidgets.QDoubleSpinBox()
        self.abs_amp_min_tx.setRange(-200.0, 200.0)
        self.abs_amp_min_tx.setDecimals(2)
        self.abs_amp_min_tx.setSingleStep(0.1)
        self.abs_amp_min_tx.setValue(-5.00)
        self.abs_amp_min_tx.setSuffix(' дБ')
        criteria_layout.addWidget(self.abs_amp_min_tx, 1, 2)



        self.meas_tab_layout.addWidget(criteria_group)

        # Допуски линий задержки (по каждой ЛЗ отдельно)
        lz_group = QtWidgets.QGroupBox('Допуски линий задержки')
        lz_grid = QtWidgets.QGridLayout(lz_group)
        lz_grid.setContentsMargins(15, 15, 15, 15)
        lz_grid.setSpacing(8)

        lz_grid.addWidget(QtWidgets.QLabel(''), 0, 0)
        lz_grid.addWidget(QtWidgets.QLabel('ΔАмп (± дБ)'), 0, 1)
        lz_grid.addWidget(QtWidgets.QLabel('ΔЗадержка от (пс)'), 0, 2)
        lz_grid.addWidget(QtWidgets.QLabel('ΔЗадержка до (пс)'), 0, 3)

        self.lz_amp_tolerances_db = {}
        self.lz_delay_tolerances = {}
        lz_rows = [(1, 80.0, 120.0), (2, 150.0, 220.0), (4, 360.0, 440.0), (8, 650.0, 800.0)]
        for r, (disc, dmin, dmax) in enumerate(lz_rows, start=1):
            lz_grid.addWidget(QtWidgets.QLabel(f'ЛЗ{disc}'), r, 0)

            amp_sb = QtWidgets.QDoubleSpinBox();  amp_sb.setRange(0.0, 20.0);  amp_sb.setDecimals(2)
            amp_sb.setSingleStep(0.1);  amp_sb.setValue(1.0);  amp_sb.setSuffix(' дБ')
            self.lz_amp_tolerances_db[disc] = amp_sb
            lz_grid.addWidget(amp_sb, r, 1)

            min_sb = QtWidgets.QDoubleSpinBox();  min_sb.setRange(-10000.0, 10000.0);  min_sb.setDecimals(1)
            min_sb.setSingleStep(1.0);  min_sb.setValue(dmin);  min_sb.setSuffix(' пс')
            max_sb = QtWidgets.QDoubleSpinBox();  max_sb.setRange(-10000.0, 10000.0);  max_sb.setDecimals(1)
            max_sb.setSingleStep(1.0);  max_sb.setValue(dmax);  max_sb.setSuffix(' пс')
            self.lz_delay_tolerances[disc] = {'min': min_sb, 'max': max_sb}
            lz_grid.addWidget(min_sb, r, 2)
            lz_grid.addWidget(max_sb, r, 3)

        self.meas_tab_layout.addWidget(lz_group)

        ps_group = QtWidgets.QGroupBox('Допуски фазовращателей')
        ps_main_layout = QtWidgets.QVBoxLayout(ps_group)
        ps_main_layout.setContentsMargins(15, 15, 15, 15)

        scroll_area = QtWidgets.QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setMaximumHeight(200)
        scroll_area.setVerticalScrollBarPolicy(QtCore.Qt.ScrollBarAsNeeded)
        scroll_area.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)

        scroll_widget = QtWidgets.QWidget()
        scroll_layout = QtWidgets.QGridLayout(scroll_widget)
        scroll_layout.setSpacing(8)

        scroll_layout.addWidget(QtWidgets.QLabel(""), 0, 0)
        from_label = QtWidgets.QLabel("от:")
        from_label.setAlignment(QtCore.Qt.AlignCenter)
        scroll_layout.addWidget(from_label, 0, 1)

        to_label = QtWidgets.QLabel("до:")
        to_label.setAlignment(QtCore.Qt.AlignCenter)
        scroll_layout.addWidget(to_label, 0, 2)

        self.phase_shifter_tolerances = {}
        phase_angles = [5.625, 11.25, 22.5, 45, 90, 180]

        for row, angle in enumerate(phase_angles, 1):
            ps_label = QtWidgets.QLabel(f"ФВ {angle}°:")
            ps_label.setMinimumWidth(80)
            scroll_layout.addWidget(ps_label, row, 0)

            min_spinbox = QtWidgets.QDoubleSpinBox()
            min_spinbox.setRange(-50.0, 50.0)
            min_spinbox.setSingleStep(0.1)
            min_spinbox.setDecimals(1)
            min_spinbox.setValue(-2.0)
            min_spinbox.setSuffix('°')
            min_spinbox.setMinimumWidth(70)
            min_spinbox.setStyleSheet("QDoubleSpinBox { background-color: white; }")
            scroll_layout.addWidget(min_spinbox, row, 1)

            max_spinbox = QtWidgets.QDoubleSpinBox()
            max_spinbox.setRange(-50.0, 50.0)
            max_spinbox.setSingleStep(0.1)
            max_spinbox.setDecimals(1)
            max_spinbox.setValue(2.0)
            max_spinbox.setSuffix('°')
            max_spinbox.setMinimumWidth(70)
            max_spinbox.setStyleSheet("QDoubleSpinBox { background-color: white; }")
            scroll_layout.addWidget(max_spinbox, row, 2)

            self.phase_shifter_tolerances[angle] = {
                'min': min_spinbox,
                'max': max_spinbox
            }

        scroll_area.setWidget(scroll_widget)
        ps_main_layout.addWidget(scroll_area)

        self.meas_tab_layout.addWidget(ps_group)


        self.meas_tab_layout.addStretch()

        self.param_tabs.addTab(self.meas_tab, 'Настройки измерения')
        self.left_layout.addWidget(self.param_tabs, 1)

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

        self.results_table = QtWidgets.QTableWidget()
        self.results_table.setColumnCount(15)
        self.results_table.setHorizontalHeaderLabels([
            'ППМ', '0° Амп.', '0° Фаза', '5.625° Амп.', '5.625° Фаза', '11.25° Амп.', '11.25° Фаза',
            '22.5° Амп.', '22.5° Фаза', '45° Амп.', '45° Фаза', '90° Амп.', '90° Фаза', '180° Амп.', '180° Фаза'])
        self.results_table.setRowCount(32)

        header = self.results_table.horizontalHeader()
        header.setSectionResizeMode(0, QtWidgets.QHeaderView.Fixed)
        header.resizeSection(0, 50)

        for i in range(1, 15):
            header.setSectionResizeMode(i, QtWidgets.QHeaderView.Stretch)

        self.results_table.verticalHeader().setSectionResizeMode(QtWidgets.QHeaderView.Fixed)
        self.results_table.verticalHeader().setDefaultSectionSize(25)
        self.results_table.verticalHeader().setVisible(False)

        self.results_table.setAlternatingRowColors(True)
        self.results_table.setShowGrid(True)

        for row in range(32):
            item = QtWidgets.QTableWidgetItem(f"{row + 1}")
            item.setTextAlignment(QtCore.Qt.AlignCenter)
            self.results_table.setItem(row, 0, item)
            for col in range(1, 15):
                item = QtWidgets.QTableWidgetItem("")
                item.setTextAlignment(QtCore.Qt.AlignCenter)
                self.results_table.setItem(row, col, item)


        self.delay_table = QtWidgets.QTableWidget()
        self.delay_table.setColumnCount(5)
        self.delay_table.setHorizontalHeaderLabels([
            'Дискрет ЛЗ', 'ΔАмп (дБ)', 'ΔЗадержка (пс)', 'Статус ампл.', 'Статус задержки'])
        self.delay_table.setRowCount(4)

        delay_header = self.delay_table.horizontalHeader()
        delay_header.setSectionResizeMode(0, QtWidgets.QHeaderView.Fixed)
        delay_header.resizeSection(0, 80)

        for i in range(1, 5):
            delay_header.setSectionResizeMode(i, QtWidgets.QHeaderView.Stretch)

        self.delay_table.verticalHeader().setSectionResizeMode(QtWidgets.QHeaderView.Fixed)
        self.delay_table.verticalHeader().setDefaultSectionSize(25)
        self.delay_table.verticalHeader().setVisible(False)

        self.delay_table.setAlternatingRowColors(True)
        self.delay_table.setShowGrid(True)

        delay_discretes = [1, 2, 4, 8]

        for row, discrete in enumerate(delay_discretes):
            item = QtWidgets.QTableWidgetItem(f"ЛЗ{discrete}")
            item.setTextAlignment(QtCore.Qt.AlignCenter)
            self.delay_table.setItem(row, 0, item)
            for col in range(1, 5):
                item = QtWidgets.QTableWidgetItem("")
                item.setTextAlignment(QtCore.Qt.AlignCenter)
                self.delay_table.setItem(row, col, item)

        self.view_tabs = QtWidgets.QTabWidget()
        self.view_tabs.addTab(self.results_table, "Таблица ППМ")
        self.view_tabs.addTab(self.delay_table, "Линии задержки")
        self.right_layout.addWidget(self.view_tabs, stretch=2)

        self.console = QtWidgets.QTextEdit()
        self.console.setReadOnly(True)
        self.console.setFixedHeight(200)
        self.right_layout.addWidget(self.console, stretch=1)

        self.log_handler = QTextEditLogHandler(self.console)
        logger.add(self.log_handler, format="{time:HH:mm:ss} | {level} | {message}")

        self._check_thread = None

        self.ma_connect_btn.clicked.connect(self.connect_ma)
        self.pna_connect_btn.clicked.connect(self.connect_pna)
        self.gen_connect_btn.clicked.connect(self.connect_trigger)
        self.apply_btn.clicked.connect(self.apply_params)
        self.start_btn.clicked.connect(self.start_check)
        self.stop_btn.clicked.connect(self.stop_check)
        self.pause_btn.clicked.connect(self.pause_check)

        self.update_data_signal.connect(self.update_table_from_data)
        self.update_realtime_signal.connect(self.update_table_realtime)

        self.update_data_signal.connect(lambda d: setattr(self, '_stend_fv_data', d))
        self.update_lz_signal.connect(self._accumulate_lz_data)
        self.update_lz_signal.connect(self.update_delay_table_from_lz)
        self.check_finished_signal.connect(self.on_check_finished)

        self.set_buttons_enabled(True)
        self.pna_settings = {}

        self.check_criteria = {
            'phase_shifter_tolerances': {
                5.625: {'min': -2.0, 'max': 2.0},
                11.25: {'min': -2.0, 'max': 2.0},
                22.5: {'min': -2.0, 'max': 2.0},
                45: {'min': -2.0, 'max': 2.0},
                90: {'min': -2.0, 'max': 2.0},
                180: {'min': -2.0, 'max': 2.0}
            }
        }

        self.ppm_data = {}
        self.check_completed = False  # Флаг завершения основной проверки

        self.set_button_connection_state(self.pna_connect_btn, False)
        self.set_button_connection_state(self.ma_connect_btn, False)

        # Настройки UI (персистентность)
        self._ui_settings = QtCore.QSettings('PULSAR', 'CheckStendMA')
        self.load_ui_settings()



    @QtCore.pyqtSlot()
    def on_check_finished(self):
        """Слот для завершения проверки - выполняется в главном потоке GUI"""
        self.set_buttons_enabled(True)
        self.pause_btn.setText('Пауза')
        self.check_completed = True
        logger.info('Проверка завершена, интерфейс восстановлен')

    @QtCore.pyqtSlot(bool)
    def set_buttons_enabled(self, enabled: bool):
        """Управляет доступностью кнопок"""
        self.ma_connect_btn.setEnabled(enabled)
        self.pna_connect_btn.setEnabled(enabled)
        self.apply_btn.setEnabled(enabled)
        self.start_btn.setEnabled(enabled)
        self.stop_btn.setEnabled(not enabled)
        self.pause_btn.setEnabled(not enabled)




    @QtCore.pyqtSlot(dict)
    def update_delay_table_from_lz(self, lz_results: dict):
        """Отрисовывает усреднённые значения ЛЗ и статусы по допускам.
        Ожидается формат {lz:int: (amp_delta_db:float, delay_delta_ps:float)}"""
        try:
            order = [1, 2, 4, 8]
            for lz, (amp_delta, delay_delta) in lz_results.items():
                if lz not in order:
                    continue 
                    
                row = order.index(lz)
                self.delay_table.setItem(row, 1, self.create_centered_table_item("" if np.isnan(amp_delta) else f"{amp_delta:.2f}"))
                self.delay_table.setItem(row, 2, self.create_centered_table_item("" if np.isnan(delay_delta) else f"{delay_delta:.1f}"))

                if np.isnan(amp_delta):
                    amp_item = self.create_neutral_status_item("-")
            else:
                amp_tol = float(self.lz_amp_tolerances_db.get(lz).value()) if self.lz_amp_tolerances_db.get(lz) else 1.0
                amp_ok = (-amp_tol <= amp_delta <= amp_tol)
                amp_item = self.create_status_table_item("OK" if amp_ok else "FAIL", amp_ok)
            self.delay_table.setItem(row, 3, amp_item)

            if np.isnan(delay_delta):
                delay_item = self.create_neutral_status_item("-")
            else:
                tol = self.lz_delay_tolerances.get(lz)
                dmin = float(tol['min'].value()) if tol else -float('inf')
                dmax = float(tol['max'].value()) if tol else float('inf')
                delay_ok = (dmin <= delay_delta <= dmax)
                delay_item = self.create_status_table_item("OK" if delay_ok else "FAIL", delay_ok)
            self.delay_table.setItem(row, 4, delay_item)

            try:
                self.delay_table.viewport().update()
            except Exception:
                pass
        except Exception as e:
            logger.error(f"Ошибка обновления таблицы ЛЗ: {e}")

    @QtCore.pyqtSlot(dict)
    def update_table_from_data(self, data: dict):
        """Заполняет таблицу по словарю {fv_angle: [A1,P1,...,A32,P32]}.
        Фазы считаются относительными (для 0° – всегда 0). Статусы считаем только по фазе.
        """
        try:
            fv_order = [0.0, 5.625, 11.25, 22.5, 45.0, 90.0, 180.0]

            def get_phase_tolerance(angle: float):
                if angle == 0.0:
                    return None
                tol = self.check_criteria.get('phase_shifter_tolerances', {})
                return tol.get(angle) or tol.get(float(angle))

            def get_abs_amp_min():
                return float(self.abs_amp_min_rx.value()) if self.channel_combo.currentText() == 'Приемник' else float(self.abs_amp_min_tx.value())


            for ppm_idx in range(32):
                row = ppm_idx
                self.results_table.setItem(row, 0, self.create_centered_table_item(str(ppm_idx + 1)))

                col = 1
                for angle in fv_order:
                    values = data.get(angle)
                    if not values or len(values) < (ppm_idx * 2 + 2):
                        # Пустые ячейки
                        self.results_table.setItem(row, col, self.create_centered_table_item(""))
                        self.results_table.setItem(row, col + 1, self.create_centered_table_item(""))
                        col += 2
                        continue

                    amp_val = values[ppm_idx * 2]
                    phase_rel = values[ppm_idx * 2 + 1]

                    abs_min = get_abs_amp_min()
                    amp_ok = (amp_val >= abs_min)
                    self.results_table.setItem(row, col, self.create_status_table_item(f"{amp_val:.2f}", amp_ok))

                    if angle == 0.0:
                        self.results_table.setItem(row, col + 1, self.create_centered_table_item(f"{phase_rel:.1f}"))
                    else:
                        tol = get_phase_tolerance(angle)
                        if tol:
                            ok = tol['min'] <= phase_rel - angle <= tol['max']
                        else:
                            ok = (-2.0 <= phase_rel - angle <= 2.0)
                        self.results_table.setItem(row, col + 1, self.create_status_table_item(f"{phase_rel:.1f}", ok))

                    col += 2

            self.results_table.viewport().update()
        except Exception as e:
            logger.error(f"Ошибка заполнения таблицы из словаря данных: {e}")

    @QtCore.pyqtSlot(float, int, float, float)
    def update_table_realtime(self, angle: float, ppm_index: int, amp_abs: float, phase_rel: float):
        """Точечное обновление таблицы по мере поступления данных."""
        try:
            fv_order = [0.0, 5.625, 11.25, 22.5, 45.0, 90.0, 180.0]
            if angle not in fv_order:
                return
            row = ppm_index - 1
            if row < 0 or row >= 32:
                return

            base_col = 1 + fv_order.index(angle) * 2

            abs_min = float(self.abs_amp_min_rx.value()) if self.channel_combo.currentText() == 'Приемник' else float(self.abs_amp_min_tx.value())
            amp_ok = (amp_abs >= abs_min)
            self.results_table.setItem(row, base_col, self.create_status_table_item(f"{amp_abs:.2f}", amp_ok))
            # Фаза (+ статус кроме 0°)
            if angle == 0.0:
                self.results_table.setItem(row, base_col + 1, self.create_centered_table_item(f"{phase_rel:.1f}"))
            else:
                tol = self.check_criteria.get('phase_shifter_tolerances', {}).get(angle)
                if tol is None:
                    tol = self.check_criteria.get('phase_shifter_tolerances', {}).get(float(angle))
                ok = (tol['min'] <= phase_rel - angle <= tol['max']) if tol else (-2.0 <= phase_rel - angle <= 2.0)
                self.results_table.setItem(row, base_col + 1, self.create_status_table_item(f"{phase_rel:.1f}", ok))

            try:
                self.results_table.viewport().update()
            except Exception:
                pass
        except Exception as e:
            logger.error(f"Ошибка realtime-обновления таблицы: {e}")

    def apply_params(self):
        """Сохраняет параметры из вкладок"""
        # MA
        self.channel = self.channel_combo.currentText()
        self.direction = self.direction_combo.currentText()

        # PNA
        self.pna_settings['s_param'] = self.s_param_combo.currentText()
        self.pna_settings['power'] = self.pna_power.value()
        self.pna_settings['freq_start'] = self.pna_start_freq.value() * 10 ** 6
        self.pna_settings['freq_stop'] = self.pna_stop_freq.value() * 10 ** 6
        self.pna_settings['freq_points'] = self.pna_number_of_points.currentText()
        self.pna_settings['settings_file'] = self.settings_file_edit.text()

        # Meas - критерии проверки
        self.check_criteria = {
            'phase_shifter_tolerances': {}
        }

        for angle, controls in self.phase_shifter_tolerances.items():
            self.check_criteria['phase_shifter_tolerances'][angle] = {
                'min': controls['min'].value(),
                'max': controls['max'].value()
            }




        logger.info('Параметры успешно применены')
        try:
            self.save_ui_settings()
        except Exception:
            pass

    def save_ui_settings(self):
        s = self._ui_settings
        # MA
        s.setValue('channel', self.channel_combo.currentText())
        s.setValue('direction', self.direction_combo.currentText())
        s.setValue('ma_command_delay', float(self.ma_command_delay.value()))
        # PNA
        s.setValue('s_param', self.s_param_combo.currentText())
        s.setValue('pna_power', float(self.pna_power.value()))
        s.setValue('pna_start_freq', int(self.pna_start_freq.value()))
        s.setValue('pna_stop_freq', int(self.pna_stop_freq.value()))
        s.setValue('pna_points', self.pna_number_of_points.currentText())
        s.setValue('pna_settings_file', self.settings_file_edit.text())
        # Criteria
        s.setValue('abs_amp_min_rx', float(self.abs_amp_min_rx.value()))
        s.setValue('abs_amp_min_tx', float(self.abs_amp_min_tx.value()))
        # Phase shifters
        for angle, controls in self.phase_shifter_tolerances.items():
            s.setValue(f'ps_tol_{angle}_min', float(controls['min'].value()))
            s.setValue(f'ps_tol_{angle}_max', float(controls['max'].value()))
        s.sync()

    def load_ui_settings(self):
        s = self._ui_settings
        # MA
        if (v := s.value('channel')):
            idx = self.channel_combo.findText(v)
            if idx >= 0: self.channel_combo.setCurrentIndex(idx)
        if (v := s.value('direction')):
            idx = self.direction_combo.findText(v)
            if idx >= 0: self.direction_combo.setCurrentIndex(idx)
        if (v := s.value('ma_command_delay')) is not None:
            try: self.ma_command_delay.setValue(float(v))
            except Exception: pass
        # PNA
        if (v := s.value('s_param')):
            idx = self.s_param_combo.findText(v)
            if idx >= 0: self.s_param_combo.setCurrentIndex(idx)
        for key, widget in [
            ('pna_power', self.pna_power),
            ('pna_start_freq', self.pna_start_freq),
            ('pna_stop_freq', self.pna_stop_freq)
        ]:
            val = s.value(key)
            if val is not None:
                try:
                    if hasattr(widget, 'setValue'):
                        widget.setValue(float(val))
                except Exception:
                    pass
        if (v := s.value('pna_points')):
            idx = self.pna_number_of_points.findText(v)
            if idx >= 0: self.pna_number_of_points.setCurrentIndex(idx)
        if (v := s.value('pna_settings_file')):
            self.settings_file_edit.setText(v)
        # Criteria
        if (v := s.value('abs_amp_min_rx')) is not None:
            try: 
                self.abs_amp_min_rx.setValue(float(v))
            except Exception: 
                pass
        if (v := s.value('abs_amp_min_tx')) is not None:
            try: 
                self.abs_amp_min_tx.setValue(float(v))
            except Exception: 
                pass


        # Phase shifters
        for angle, controls in self.phase_shifter_tolerances.items():
            if (v := s.value(f'ps_tol_{angle}_min')) is not None:
                try: controls['min'].setValue(float(v))
                except Exception: pass
            if (v := s.value(f'ps_tol_{angle}_max')) is not None:
                try: controls['max'].setValue(float(v))
                except Exception: pass


    def start_check(self):
        """Запускает процесс проверки"""
        # Проверяем подключение всех устройств: MA, PNA и устройства синхронизации
        if not (self.ma and self.pna and self.trigger and getattr(self.trigger, 'connection', None)):
            self.show_error_message("Ошибка", "Сначала подключите все устройства!")
            return

        self._stop_flag.clear()
        self._pause_flag.clear()
        self.pause_btn.setText('Пауза')

        self.results_table.clearContents()
        for row in range(32):
            self.results_table.setItem(row, 0, self.create_centered_table_item(str(row + 1)))
            for col in range(1, 15):
                self.results_table.setItem(row, col, QtWidgets.QTableWidgetItem(""))

        self.ppm_data.clear()
        self.check_completed = False

        self.set_buttons_enabled(False)
        logger.info("Запуск проверки МА...")
        self.apply_params()
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
        self._pause_flag.clear()
        self.pause_btn.setText('Пауза')
        self.set_buttons_enabled(True)
        logger.info('Проверка остановлена.')

    def _run_check(self):
        logger.info("Начало выполнения проверки в отдельном потоке")
        try:
            channel = Channel.Receiver if self.channel_combo.currentText() == 'Приемник' else Channel.Transmitter
            direction = Direction.Horizontal if self.direction_combo.currentText() == 'Горизонтальная' else Direction.Vertical
            logger.info(f'Используем канал: {channel.value}, поляризация: {direction.value}')

            if self.pna and self.pna_settings:
                try:
                    self.pna.preset()
                    if self.pna_settings.get('settings_file'):
                        settings_file = self.pna_settings.get('settings_file')
                        base_path = self.device_settings.get('pna_files_path', '')
                        if settings_file and base_path and not os.path.isabs(settings_file):
                            settings_file = os.path.join(base_path, settings_file)
                        self.pna.load_settings_file(settings_file)
                    else:
                        self.pna.create_measure(self.pna_settings.get('s_param'))
                        self.pna.turn_window(state=True)
                        self.pna.put_and_visualize_trace()
                    self.pna.set_freq_start(self.pna_settings.get('freq_start'))
                    self.pna.set_freq_stop(self.pna_settings.get('freq_stop'))
                    self.pna.set_points(self.pna_settings.get('freq_points'))
                    self.pna.set_power(self.pna_settings.get('power'))
                    self.pna.set_output(True)
                    meas = self.pna.get_selected_meas()
                    if not meas:
                        measures = self.pna.get_all_meas()
                        self.pna.set_current_meas(measures[0])
                except Exception as e:
                    logger.error(f"Ошибка при настройке PNA: {e}")
                    raise

            class CheckMAWithCallback(CheckMAStend):
                def __init__(self, ma, pna, stop_event, pause_event, criteria=None,
                             parent_widget=None):
                    # Сначала сохраним parent_widget, чтобы получить gen до super().__init__
                    self.parent_widget = parent_widget
                    gen_device = getattr(parent_widget, 'trigger', None) if parent_widget else None
                    super().__init__(ma, pna, gen_device, stop_event, pause_event)

                    if criteria:
                        self.phase_shifter_tolerances = criteria.get('phase_shifter_tolerances', None)

                def start(self, chanel: Channel, direction: Direction):
                    """Переопределяем метод start для сохранения нормировочных значений"""
                    results = super().start(chanel, direction)


                    return results

                # Поэлементные методы колбэка не нужны: обновление идёт через realtime/paket

            check = CheckMAWithCallback(
                ma=self.ma,
                pna=self.pna,
                stop_event=self._stop_flag,
                pause_event=self._pause_flag,
                criteria=self.check_criteria,
                parent_widget=self
            )

            # Пробросим колбэк для пачки данных
            try:
                check.data_callback = self.update_data_signal
            except Exception:
                pass
            # Пробросим колбэк для поэлементных обновлений
            try:
                check.realtime_callback = self.update_realtime_signal
            except Exception:
                pass
            # Колбэк с усреднёнными данными ЛЗ
            try:
                check.delay_callback = self.update_lz_signal
            except Exception:
                pass

            # Установим тайминги триггера из UI перед стартом
            try:
                # Период в UI в мкс → секунды; lead в мс → секунды; post_trigger_delay в мс → секунды
                check.period = float(self.trig_pulse_period.value()) * 1e-6
                check.lead = float(self.trig_start_lead.value()) * 1e-3
                check.post_trigger_delay = float(self.trig_post_trigger_delay.value()) * 1e-3
            except Exception:
                pass

            check.start(chanel=channel, direction=direction)

            if not self._stop_flag.is_set():
                logger.info('Проверка завершена успешно.')

        except Exception as e:
            self.error_signal.emit("Ошибка проверки", f"Произошла ошибка при выполнении проверки: {str(e)}")
            logger.error(f"Ошибка при выполнении проверки: {e}")
            try:
                if self.pna:
                    self.pna.set_output(False)
            except Exception as pna_error:
                logger.error(f"Ошибка при аварийном выключении PNA: {pna_error}")
        finally:
            self.check_finished_signal.emit()



    def show_ppm_details_graphics(self, ppm_num, global_pos):
        menu = QtWidgets.QMenu()

        if ppm_num not in self.ppm_data:
            header_action = menu.addAction(f"ППМ {ppm_num} - данные не готовы")
            header_action.setEnabled(False)
        else:
            data = self.ppm_data[ppm_num]
            status_text = "OK" if data['result'] else "FAIL"
            status_color = "🟢" if data['result'] else "🔴"
            header_action = menu.addAction(f"{status_color} ППМ {ppm_num} - {status_text}")
            header_action.setEnabled(False)
            menu.addSeparator()

            if not np.isnan(data['amp_zero']):
                amp_action = menu.addAction(f"Амплитуда: {data['amp_zero']:.2f} дБ")
            else:
                amp_action = menu.addAction("Амплитуда: ---")
            amp_action.setEnabled(False)

            if not np.isnan(data['amp_diff']):
                amp_action = menu.addAction(f"Амплитуда_дельта: {data['amp_diff']:.2f} дБ")
            else:
                amp_action = menu.addAction("Амплитуда_дельта: ---")
            amp_action.setEnabled(False)


            if not np.isnan(data['phase_zero']):
                phase_action = menu.addAction(f"Фаза: {data['phase_zero']:.1f}°")
            else:
                phase_action = menu.addAction("Фаза: ---")
            phase_action.setEnabled(False)

            if not np.isnan(data['phase_diff']):
                phase_action = menu.addAction(f"Фаза_дельта: {data['phase_diff']:.1f}°")
            else:
                phase_action = menu.addAction("Фаза_делта: ---")
            phase_action.setEnabled(False)

            if data['fv_data'] and len(data['fv_data']) > 0:
                menu.addSeparator()
                fv_header = menu.addAction("Значения ФВ:")
                fv_header.setEnabled(False)

                fv_names = ["Дельта ФВ", "5,625°", "11,25°", "22,5°", "45°", "90°", "180°"]
                for i, value in enumerate(data['fv_data']):
                    if i < len(fv_names):
                        if not np.isnan(value):
                            fv_action = menu.addAction(f"  {fv_names[i]}: {value:.1f}°")
                        else:
                            fv_action = menu.addAction(f"  {fv_names[i]}: ---")
                        fv_action.setEnabled(False)
                    else:
                        if not np.isnan(value):
                            fv_action = menu.addAction(f"  ФВ {i + 1}: {value:.1f}°")
                        else:
                            fv_action = menu.addAction(f"  ФВ {i + 1}: ---")
                        fv_action.setEnabled(False)

        if self.check_completed and self._can_remeasure():
            menu.addSeparator()
            remeasure_action = menu.addAction("🔄 Перемерить ППМ")
            remeasure_action.triggered.connect(lambda: self.remeasure_ppm(ppm_num))

        menu.exec_(global_pos)

    def show_bottom_rect_details(self, global_pos):
        """Показывает контекстное меню для нижнего прямоугольника (Линии задержки)"""
        menu = QtWidgets.QMenu()

        header_action = menu.addAction("Линии задержки")
        header_action.setEnabled(False)
        menu.addSeparator()

        if self.bottom_rect_data:
            for key, value in self.bottom_rect_data.items():
                data_action = menu.addAction(f"{key}: {value}")
                data_action.setEnabled(False)
        else:
            info_action = menu.addAction("Данные будут добавлены позже...")
            info_action.setEnabled(False)

        menu.exec_(global_pos)

    def update_bottom_rect_data(self, data: dict):
        """Обновляет данные для нижнего прямоугольника (Линии задержки)"""
        self.bottom_rect_data = data



    def _accumulate_lz_data(self, lz_chunk: dict):
        try:
            for k, v in lz_chunk.items():
                self._stend_lz_data[k] = v
        except Exception:
            pass



    def open_file_dialog(self):
        """Открытие диалога выбора файла настроек PNA"""
        try:
            if not self.pna or not self.pna.connection:
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

    def apply_parsed_settings(self):
        """Применение параметров PNA настроек к интерфейсу"""
        try:
            s_param = self.pna.get_s_param()
            logger.info(f'S_PARAM={s_param}')
            if s_param:
                index = self.s_param_combo.findText(s_param)
                if index >= 0:
                    self.s_param_combo.setCurrentIndex(index)

            power = self.pna.get_power()
            if power:
                self.pna_power.setValue(power)

            freq_start = self.pna.get_start_freq()
            if freq_start:
                self.pna_start_freq.setValue(int(freq_start / 10 ** 6))

            freq_stop = self.pna.get_stop_freq()
            if freq_stop:
                self.pna_stop_freq.setValue(int(freq_stop / 10 ** 6))

            points = self.pna.get_amount_of_points()
            if points:
                index = self.pna_number_of_points.findText(str(int(points)))
                if index >= 0:
                    self.pna_number_of_points.setCurrentIndex(index)

        except Exception as e:
            logger.error(f'Ошибка при применении настроек к интерфейсу: {e}')



