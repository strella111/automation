from PyQt5 import QtWidgets, QtCore, QtGui
from PyQt5.QtCore import QThread, pyqtSignal
from PyQt5.QtWidgets import QStyle, QMessageBox, QProgressDialog
from PyQt5.QtCore import QSize
import os
import pyqtgraph as pg
import numpy as np
from loguru import logger

from ui.widgets.base_measurement_widget import BaseMeasurementWidget
from core.measurements.beam_pattern.beam_measurement import BeamMeasurement
from config.settings_manager import get_ui_settings
from utils.excel_module import load_beam_pattern_results
from PyQt5.QtWidgets import QFileDialog
from core.common.coordinate_system import CoordinateSystemManager
from ui.dialogs.add_coord_syst_dialog import AddCoordinateSystemDialog


class LoadRescanWorker(QThread):
    """Рабочий поток для загрузки данных досканирования"""
    finished_signal = pyqtSignal(dict)  # Загруженные данные
    error_signal = pyqtSignal(str)  # Ошибка
    
    def __init__(self, folder_path: str):
        super().__init__()
        self.folder_path = folder_path
    
    def run(self):
        try:
            loaded_data = load_beam_pattern_results(self.folder_path)
            if not loaded_data:
                self.error_signal.emit("Не удалось загрузить данные из выбранной папки.")
                return
            self.finished_signal.emit(loaded_data)
        except Exception as e:
            logger.error(f"Ошибка при загрузке данных в потоке: {e}", exc_info=True)
            self.error_signal.emit(f"Не удалось загрузить данные: {str(e)}")


class BeamMeasurementWorker(QThread):
    """Рабочий поток для измерений"""
    progress_signal = pyqtSignal(int, int, str, int, int)  # current, total, message, elapsed_time, estimated_remaining
    data_signal = pyqtSignal(dict)  # Данные измерений
    finished_signal = pyqtSignal(dict)  # Финальные результаты
    error_signal = pyqtSignal(str)  # Ошибка
    
    def __init__(self, measurement_obj, beams, scan_params, freq_list, pna_settings=None, sync_settings=None):
        super().__init__()
        self.measurement = measurement_obj
        self.beams = beams
        self.scan_params = scan_params
        self.freq_list = freq_list
        self.pna_settings = pna_settings
        self.sync_settings = sync_settings
    
    def run(self):
        try:
            result = self.measurement.measure(
                beams=self.beams,
                scan_params=self.scan_params,
                freq_list=self.freq_list,
                progress_callback=self.on_progress,
                data_callback=self.on_data,
                pna_settings=self.pna_settings,
                sync_settings=self.sync_settings
            )
            self.finished_signal.emit(result)
        except Exception as e:
            logger.error(f"Ошибка в потоке измерений: {e}", exc_info=True)
            self.error_signal.emit(str(e))
    
    def on_progress(self, current, total, message, elapsed_time, estimated_remaining):
        self.progress_signal.emit(current, total, message, elapsed_time, estimated_remaining)
    
    def on_data(self, data):
        self.data_signal.emit(data)


class BeamPatternWidget(BaseMeasurementWidget):
    """Виджет измерения лучей АФАР"""
    
    update_gui_signal = pyqtSignal(int, int, dict)  # bu_num, beam_num, freq, data
    
    def __init__(self):
        super().__init__()

        # {beam_num: {freq: {'x': [...], 'y': [...], 'amp': [[...]], 'phase': [[...]]}}}
        # где amp и phase - 2D массивы (len_x x len_y)
        self.measurement_data = {}
        self.current_beam = None
        self.current_freq = None
        self.freq_list = []

        self.rescan_data = None  # Загруженные данные из папки
        self.rescan_save_dir = None  # Путь к папке для досканирования

        self.trigger = None

        self._measurement_thread = None
        self._load_rescan_thread = None  # Поток для загрузки данных досканирования

        self._is_updating_plots = False  # Флаг: идет ли сейчас отрисовка
        self._pending_data_update = None  # Последние данные, ожидающие отрисовки
        self._update_pending = False  # Флаг: есть ли отложенное обновление

        self._ui_settings = get_ui_settings('beam_pattern')
        self.coord_system_manager = CoordinateSystemManager("config/coordinate_systems.json")
        self.coord_system = None

        self.update_gui_signal.connect(self.on_measurement_update)

        """Создание интерфейса"""
        self.layout = QtWidgets.QHBoxLayout(self)

        self.left_panel = QtWidgets.QWidget()
        self.left_panel.setFixedWidth(400)
        self.left_layout = QtWidgets.QVBoxLayout(self.left_panel)
        self.layout.addWidget(self.left_panel)

        self.right_panel = QtWidgets.QWidget()
        self.right_layout = QtWidgets.QVBoxLayout(self.right_panel)
        self.layout.addWidget(self.right_panel, stretch=3)

        connect_group = self.build_connect_group([
            ('pna', 'Анализатор'),
            ('afar', 'АФАР'),
            ('gen', 'Устройство синхронизации'),
            ('psn', 'Планарный сканер'),
        ])
        self.left_layout.addWidget(connect_group)

        self.param_tabs = QtWidgets.QTabWidget()


        self.pna_tab, self.pna_tab_layout = self.build_pna_form(
            points_options=['3', '11', '21', '33', '51', '101', '201'],
            default_points='11',
            include_pulse=True,
            include_file=True,
            include_pulse_source=True,
            include_trig_polarity=True,
        )

        self.load_file_btn.clicked.connect(self.open_file_dialog)
        self.param_tabs.addTab(self.pna_tab, 'Анализатор')

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
        self.trig_pulse_period.setRange(0, 100000)
        self.trig_pulse_period.setSingleStep(10)
        self.trig_pulse_period.setSuffix(' мкс')
        self.trig_pulse_period.setValue(500.000)
        self.trig_tab_layout.addRow('Период импульса:', self.trig_pulse_period)
        
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

        coord_group = QtWidgets.QGroupBox('Система координат')
        coord_layout = QtWidgets.QFormLayout(coord_group)
        coord_layout.setContentsMargins(15, 15, 15, 15)

        coord_selection_layout = QtWidgets.QHBoxLayout()
        coord_selection_layout.setSpacing(5)
        coord_selection_layout.setContentsMargins(0, 0, 0, 0)
        
        self.coord_system_combo = QtWidgets.QComboBox()
        self.coord_system_combo.addItems(self.coord_system_manager.get_system_names())
        self.coord_system_combo.setMinimumWidth(200)
        self.coord_system_combo.currentTextChanged.connect(self.update_coord_buttons_state)
        coord_selection_layout.addWidget(self.coord_system_combo, 1)

        self.add_coord_system_btn = QtWidgets.QPushButton('+')
        self.add_coord_system_btn.setFixedSize(24, 22)
        self.add_coord_system_btn.setToolTip('Добавить новую систему координат')
        self.add_coord_system_btn.clicked.connect(self.add_coordinate_system)
        coord_selection_layout.addWidget(self.add_coord_system_btn, 0, QtCore.Qt.AlignVCenter)

        self.remove_coord_system_btn = QtWidgets.QPushButton('−')
        self.remove_coord_system_btn.setFixedSize(24, 22)
        self.remove_coord_system_btn.setToolTip('Удалить выбранную систему координат')
        self.remove_coord_system_btn.clicked.connect(self.remove_coordinate_system)
        coord_selection_layout.addWidget(self.remove_coord_system_btn, 0, QtCore.Qt.AlignVCenter)
        
        coord_layout.addRow('Система координат:', coord_selection_layout)
        self.meas_tab_layout.addWidget(coord_group)

        scan_group = QtWidgets.QGroupBox('Параметры планарного сканирования')
        scan_layout = QtWidgets.QFormLayout(scan_group)
        
        self.left_x = QtWidgets.QDoubleSpinBox()
        self.left_x.setRange(-1000, 1000)
        self.left_x.setDecimals(4)
        self.left_x.setValue(1.39)
        self.left_x.setSuffix(' см')
        scan_layout.addRow('Левая граница X:', self.left_x)
        
        self.right_x = QtWidgets.QDoubleSpinBox()
        self.right_x.setRange(-1000, 1000)
        self.right_x.setDecimals(4)
        self.right_x.setValue(54.67)
        self.right_x.setSuffix(' см')
        scan_layout.addRow('Правая граница X:', self.right_x)
        
        self.up_y = QtWidgets.QDoubleSpinBox()
        self.up_y.setRange(-1000, 1000)
        self.up_y.setDecimals(4)
        self.up_y.setValue(-0.11)
        self.up_y.setSuffix(' см')
        scan_layout.addRow('Верхняя граница Y:', self.up_y)
        
        self.down_y = QtWidgets.QDoubleSpinBox()
        self.down_y.setRange(-1000, 1000)
        self.down_y.setDecimals(4)
        self.down_y.setValue(-14.10)
        self.down_y.setSuffix(' см')
        scan_layout.addRow('Нижняя граница Y:', self.down_y)
        
        self.step_x = QtWidgets.QDoubleSpinBox()
        self.step_x.setRange(0.1, 100)
        self.step_x.setDecimals(4)
        self.step_x.setValue(1.40)
        self.step_x.setSuffix(' см')
        scan_layout.addRow('Шаг X:', self.step_x)
        
        self.step_y = QtWidgets.QDoubleSpinBox()
        self.step_y.setRange(-100, 100)
        self.step_y.setDecimals(4)
        self.step_y.setValue(-0.22)
        self.step_y.setSuffix(' см')
        scan_layout.addRow('Шаг Y:', self.step_y)
        
        self.meas_tab_layout.addWidget(scan_group)

        self.create_beam_selector()

        self.meas_tab_layout.addStretch()
        self.param_tabs.addTab(self.meas_tab, 'Настройки измерения')
        
        self.left_layout.addWidget(self.param_tabs, 1)

        self.apply_btn, control_layout = self.create_control_buttons()
        if self.apply_btn:
            self.left_layout.addWidget(self.apply_btn)
        self.left_layout.addLayout(control_layout)

        self.load_folder_btn = QtWidgets.QPushButton('Загрузить папку для продолжения')
        self.left_layout.addWidget(self.load_folder_btn)
        
        self.left_layout.addStretch()

        self.create_view_controls()

        self.plot_tabs = QtWidgets.QTabWidget()

        self.amp_plot = pg.PlotWidget(title="Амплитуда (2D)")
        self.amp_plot.setBackground('w')
        self.amp_plot.showGrid(x=True, y=True, alpha=0.3)
        self.amp_plot.setLabel('left', 'Y (мм)')
        self.amp_plot.setLabel('bottom', 'X (мм)')
        self.amp_rect_items = {}  # {(x, y): QGraphicsRectItem}

        self.phase_plot = pg.PlotWidget(title="Фаза (2D)")
        self.phase_plot.setBackground('w')
        self.phase_plot.showGrid(x=True, y=True, alpha=0.3)
        self.phase_plot.setLabel('left', 'Y (мм)')
        self.phase_plot.setLabel('bottom', 'X (мм)')
        self.phase_rect_items = {}  # {(x, y): QGraphicsRectItem}
        
        self.plot_tabs.addTab(self.amp_plot, "Амплитуда")
        self.plot_tabs.addTab(self.phase_plot, "Фаза")
        
        self.right_layout.addWidget(self.plot_tabs, stretch=5)

        self.console, self.log_handler, self.log_level_combo = self.create_console_with_log_level(
            self.right_layout, console_height=180
        )
        logger.add(self.log_handler, format="{time:HH:mm:ss.SSS} | {level} | {name}:{function}:{line} | {message}")
        self.log_level_combo.currentTextChanged.connect(
            lambda: self._ui_settings.setValue('log_level', self.log_level_combo.currentText())
        )

        self.pna_connect_btn.clicked.connect(self.connect_pna)
        self.afar_connect_btn.clicked.connect(self.connect_afar)
        self.gen_connect_btn.clicked.connect(self.connect_trigger)
        self.psn_connect_btn.clicked.connect(self.connect_psn)
        self.apply_btn.clicked.connect(self.apply_params)
        self.start_btn.clicked.connect(self.start_measurement)
        self.stop_btn.clicked.connect(self.stop_measurement)
        self.pause_btn.clicked.connect(self.pause_measurement)
        self.load_folder_btn.clicked.connect(self.load_folder_for_rescan)

        self.set_buttons_enabled(True)
        self.set_button_connection_state(self.pna_connect_btn, False)
        self.set_button_connection_state(self.afar_connect_btn, False)
        self.set_button_connection_state(self.gen_connect_btn, False)
        self.set_button_connection_state(self.psn_connect_btn, False)
        
        self.pna_settings = {}
        self.sync_settings = {}

        self.measurement_start_time = None
        self.last_progress_time = None
        self.last_estimated_remaining = 0

        self.load_ui_settings()
        
    def create_view_controls(self):
        """Управление отображением (переключатели луча/частоты + таймеры)"""
        widget = QtWidgets.QWidget()
        layout = QtWidgets.QHBoxLayout(widget)
        layout.setContentsMargins(5, 2, 5, 2)
        layout.setSpacing(10)

        layout.addWidget(QtWidgets.QLabel('Луч:'))
        self.prev_beam_btn = QtWidgets.QPushButton('◄')
        self.prev_beam_btn.setFixedWidth(30)
        self.prev_beam_btn.setToolTip('Предыдущий луч')
        self.prev_beam_btn.clicked.connect(self.prev_beam)
        layout.addWidget(self.prev_beam_btn)
        
        self.view_beam_combo = QtWidgets.QComboBox()
        self.view_beam_combo.setMinimumWidth(100)  # Устанавливаем ширину для "Луч 123"
        self.view_beam_combo.currentIndexChanged.connect(self.update_plots)
        self.view_beam_combo.currentIndexChanged.connect(self.update_nav_buttons)
        layout.addWidget(self.view_beam_combo)
        
        self.next_beam_btn = QtWidgets.QPushButton('►')
        self.next_beam_btn.setFixedWidth(30)
        self.next_beam_btn.setToolTip('Следующий луч')
        self.next_beam_btn.clicked.connect(self.next_beam)
        layout.addWidget(self.next_beam_btn)
        
        layout.addSpacing(20)

        layout.addWidget(QtWidgets.QLabel('Частота:'))
        self.prev_freq_btn = QtWidgets.QPushButton('◄')
        self.prev_freq_btn.setFixedWidth(30)
        self.prev_freq_btn.setToolTip('Предыдущая частота')
        self.prev_freq_btn.clicked.connect(self.prev_freq)
        layout.addWidget(self.prev_freq_btn)
        
        self.view_freq_combo = QtWidgets.QComboBox()
        self.view_freq_combo.setMinimumWidth(120)  # Увеличиваем ширину для "9300 МГц"
        self.view_freq_combo.currentIndexChanged.connect(self.update_plots)
        self.view_freq_combo.currentIndexChanged.connect(self.update_nav_buttons)
        layout.addWidget(self.view_freq_combo)
        
        self.next_freq_btn = QtWidgets.QPushButton('►')
        self.next_freq_btn.setFixedWidth(30)
        self.next_freq_btn.setToolTip('Следующая частота')
        self.next_freq_btn.clicked.connect(self.next_freq)
        layout.addWidget(self.next_freq_btn)
        
        layout.addStretch()

        self.elapsed_time_label = QtWidgets.QLabel('Прошло: 00:00:00')
        self.elapsed_time_label.setStyleSheet('font-weight: bold; color: #2196F3;')
        layout.addWidget(self.elapsed_time_label)
        
        self.remaining_time_label = QtWidgets.QLabel('Осталось: --:--:--')
        self.remaining_time_label.setStyleSheet('font-weight: bold; color: #FF9800;')
        layout.addWidget(self.remaining_time_label)

        self.time_update_timer = QtCore.QTimer()
        self.time_update_timer.timeout.connect(self.update_time_labels)
        
        self.right_layout.addWidget(widget)
    
    def create_beam_selector(self):
        """Селектор лучей"""
        beam_group = QtWidgets.QGroupBox('Выбор лучей')
        beam_layout = QtWidgets.QVBoxLayout(beam_group)
        beam_layout.setContentsMargins(15, 15, 15, 15)

        self.beam_list_widget = QtWidgets.QListWidget()
        self.beam_list_widget.setMaximumHeight(120)
        beam_layout.addWidget(self.beam_list_widget)

        buttons_layout = QtWidgets.QHBoxLayout()
        
        self.add_beam_edit = QtWidgets.QLineEdit()
        self.add_beam_edit.setPlaceholderText('Номер луча')
        buttons_layout.addWidget(self.add_beam_edit, 1)
        
        self.add_beam_btn = QtWidgets.QPushButton('+ Добавить')
        self.add_beam_btn.clicked.connect(self.add_beam)
        buttons_layout.addWidget(self.add_beam_btn)
        
        beam_layout.addLayout(buttons_layout)

        remove_buttons_layout = QtWidgets.QHBoxLayout()
        
        self.remove_beam_btn = QtWidgets.QPushButton('− Удалить выбранный')
        self.remove_beam_btn.clicked.connect(self.remove_selected_beam)
        remove_buttons_layout.addWidget(self.remove_beam_btn)
        
        self.clear_all_beams_btn = QtWidgets.QPushButton('✕ Очистить все')
        self.clear_all_beams_btn.clicked.connect(self.clear_all_beams)
        remove_buttons_layout.addWidget(self.clear_all_beams_btn)
        
        beam_layout.addLayout(remove_buttons_layout)
        
        self.meas_tab_layout.addWidget(beam_group)
    
    def create_bu_selector(self):
        """Селектор БУ"""
        bu_selection_group = QtWidgets.QGroupBox('Выбор БУ для измерения')
        bu_selection_layout = QtWidgets.QVBoxLayout(bu_selection_group)
        bu_selection_layout.setContentsMargins(15, 15, 15, 15)

        self.bu_selection_mode = QtWidgets.QButtonGroup()
        
        self.all_bu_radio = QtWidgets.QRadioButton('Все БУ (1-40)')
        self.all_bu_radio.setChecked(True)
        self.bu_selection_mode.addButton(self.all_bu_radio, 0)
        bu_selection_layout.addWidget(self.all_bu_radio)
        
        self.range_bu_radio = QtWidgets.QRadioButton('Диапазон БУ')
        self.bu_selection_mode.addButton(self.range_bu_radio, 1)
        bu_selection_layout.addWidget(self.range_bu_radio)

        range_layout = QtWidgets.QHBoxLayout()
        range_layout.addWidget(QtWidgets.QLabel('От:'))
        self.bu_start_spin = QtWidgets.QSpinBox()
        self.bu_start_spin.setRange(1, 40)
        self.bu_start_spin.setValue(1)
        self.bu_start_spin.setEnabled(False)
        range_layout.addWidget(self.bu_start_spin)
        
        range_layout.addWidget(QtWidgets.QLabel('До:'))
        self.bu_end_spin = QtWidgets.QSpinBox()
        self.bu_end_spin.setRange(1, 40)
        self.bu_end_spin.setValue(40)
        self.bu_end_spin.setEnabled(False)
        range_layout.addWidget(self.bu_end_spin)
        
        bu_selection_layout.addLayout(range_layout)
        
        self.custom_bu_radio = QtWidgets.QRadioButton('Выборочно')
        self.bu_selection_mode.addButton(self.custom_bu_radio, 2)
        bu_selection_layout.addWidget(self.custom_bu_radio)
        
        self.section_x_radio = QtWidgets.QRadioButton('Секция по X')
        self.bu_selection_mode.addButton(self.section_x_radio, 3)
        bu_selection_layout.addWidget(self.section_x_radio)
        
        self.section_y_radio = QtWidgets.QRadioButton('Секция по Y')
        self.bu_selection_mode.addButton(self.section_y_radio, 4)
        bu_selection_layout.addWidget(self.section_y_radio)

        section_layout = QtWidgets.QHBoxLayout()
        section_layout.addWidget(QtWidgets.QLabel('Секция:'))
        self.section_spin = QtWidgets.QSpinBox()
        self.section_spin.setRange(1, 8)
        self.section_spin.setValue(1)
        self.section_spin.setEnabled(False)
        section_layout.addWidget(self.section_spin)
        
        self.section_type_label = QtWidgets.QLabel('(X)')
        self.section_type_label.setEnabled(False)
        section_layout.addWidget(self.section_type_label)
        
        bu_selection_layout.addLayout(section_layout)

        self.bu_list_widget = QtWidgets.QListWidget()
        self.bu_list_widget.setMaximumHeight(120)
        self.bu_list_widget.setEnabled(False)
        for i in range(1, 41):
            item = QtWidgets.QListWidgetItem(f'БУ №{i}')
            item.setData(QtCore.Qt.UserRole, i)
            item.setFlags(item.flags() | QtCore.Qt.ItemIsUserCheckable)
            item.setCheckState(QtCore.Qt.Unchecked)
            self.bu_list_widget.addItem(item)
        bu_selection_layout.addWidget(self.bu_list_widget)

        quick_select_layout = QtWidgets.QHBoxLayout()
        self.select_all_bu_btn = QtWidgets.QPushButton('Выбрать все')
        self.select_all_bu_btn.setEnabled(False)
        self.select_all_bu_btn.clicked.connect(self.select_all_bu)
        quick_select_layout.addWidget(self.select_all_bu_btn)
        
        self.clear_all_bu_btn = QtWidgets.QPushButton('Очистить все')
        self.clear_all_bu_btn.setEnabled(False)
        self.clear_all_bu_btn.clicked.connect(self.clear_all_bu)
        quick_select_layout.addWidget(self.clear_all_bu_btn)
        
        bu_selection_layout.addLayout(quick_select_layout)

        self.bu_selection_mode.buttonClicked.connect(self.on_bu_selection_mode_changed)
        self.bu_start_spin.valueChanged.connect(self.on_range_changed)
        self.bu_end_spin.valueChanged.connect(self.on_range_changed)
        
        self.meas_tab_layout.addWidget(bu_selection_group)

    def set_buttons_enabled(self, enabled: bool):
        """Управление состоянием кнопок"""
        self.afar_connect_btn.setEnabled(enabled)
        self.pna_connect_btn.setEnabled(enabled)
        self.gen_connect_btn.setEnabled(enabled)
        self.apply_btn.setEnabled(enabled)
        self.start_btn.setEnabled(enabled)
        self.stop_btn.setEnabled(not enabled)
    
    def add_coordinate_system(self):
        """Открывает диалог для добавления новой системы координат"""
        dialog = AddCoordinateSystemDialog(self)
        
        if dialog.exec_() == QtWidgets.QDialog.Accepted:
            name, x_offset, y_offset = dialog.get_values()

            if self.coord_system_manager.add_system(name, x_offset, y_offset):
                current_text = self.coord_system_combo.currentText()
                self.coord_system_combo.clear()
                self.coord_system_combo.addItems(self.coord_system_manager.get_system_names())

                index = self.coord_system_combo.findText(name)
                if index >= 0:
                    self.coord_system_combo.setCurrentIndex(index)

                self.update_coord_buttons_state()
                
                self.show_info_message("Успех", f"Система координат '{name}' успешно добавлена")
            else:
                self.show_error_message("Ошибка", "Не удалось добавить систему координат. Возможно, такое имя уже используется.")

    def remove_coordinate_system(self):
        """Удаляет выбранную систему координат"""
        current_name = self.coord_system_combo.currentText()
        
        if not current_name:
            self.show_error_message("Ошибка", "Нет выбранной системы координат для удаления")
            return

        if len(self.coord_system_manager.get_system_names()) <= 1:
            self.show_error_message("Ошибка", "Нельзя удалить последнюю систему координат")
            return

        reply = QMessageBox.question(
            self, 
            'Подтверждение удаления',
            f'Вы уверены, что хотите удалить систему координат "{current_name}"?',
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        
        if reply == QMessageBox.Yes:
            if self.coord_system_manager.remove_system(current_name):
                self.coord_system_combo.clear()
                self.coord_system_combo.addItems(self.coord_system_manager.get_system_names())

                if self.coord_system_combo.count() > 0:
                    self.coord_system_combo.setCurrentIndex(0)

                self.update_coord_buttons_state()
                
                self.show_info_message("Успех", f"Система координат '{current_name}' успешно удалена")
            else:
                self.show_error_message("Ошибка", "Не удалось удалить систему координат")

    def update_coord_buttons_state(self):
        """Обновляет состояние кнопок управления системами координат"""
        can_remove = len(self.coord_system_manager.get_system_names()) > 1
        self.remove_coord_system_btn.setEnabled(can_remove)

    def apply_params(self):
        """Сохраняет параметры из вкладок"""
        self.setup_pna_common()
        # PNA
        self.pna_settings['s_param'] = self.s_param_combo.currentText()
        self.pna_settings['power'] = self.pna_power.value()
        self.pna_settings['freq_start'] = self.pna_start_freq.value() * 10**6
        self.pna_settings['freq_stop'] = self.pna_stop_freq.value() * 10**6
        self.pna_settings['freq_points'] = int(self.pna_number_of_points.currentText())
        self.pna_settings['settings_file'] = self.settings_file_edit.text()
        self.pna_settings['pulse_mode'] = self.pulse_mode_combo.currentText()
        self.pna_settings['pulse_period'] = self.pulse_period.value() / 10 ** 6
        self.pna_settings['pulse_width'] = self.pulse_width.value() / 10 ** 6
        self.pna_settings['pulse_source'] = self.pulse_source.currentText().lower()
        self.pna_settings['polarity_trig'] = 'POS' if self.trig_polarity.currentText().lower().strip() == 'positive' else 'NEG'
        
        # Вычисляем частоты из начальной/конечной + количество точек
        freq_start = self.pna_settings['freq_start']
        freq_stop = self.pna_settings['freq_stop']
        num_points = self.pna_settings['freq_points']
        
        if num_points > 1:
            self.freq_list = [freq_start + (freq_stop - freq_start) * i / (num_points - 1) 
                              for i in range(num_points)]
        else:
            self.freq_list = [freq_start]

        self.freq_list = [round(f / 1e6) for f in self.freq_list]

        self.sync_settings = {}
        self.sync_settings['trig_ttl_channel'] = self.trig_ttl_channel.currentText()
        self.sync_settings['trig_ext_channel'] = self.trig_ext_channel.currentText()
        self.sync_settings['trig_start_lead'] = self.trig_start_lead.value() / 1000  # мс -> сек
        self.sync_settings['trig_pulse_period'] = self.trig_pulse_period.value() / 1e6  # мкс -> сек
        self.sync_settings['trig_min_alarm_guard'] = self.trig_min_alarm_guard.value() / 1e6  # мкс -> сек
        self.sync_settings['trig_ext_debounce'] = self.trig_ext_debounce.value() / 1000  # мс -> сек

        self.pna_settings['trig_start_lead'] = self.sync_settings['trig_start_lead']
        self.pna_settings['trig_pulse_period'] = self.sync_settings['trig_pulse_period']
        
        # Система координат
        coord_system_name = self.coord_system_combo.currentText()
        self.coord_system = self.coord_system_manager.get_system_by_name(coord_system_name)
        
        logger.info(f'Параметры применены. Частоты: {len(self.freq_list)} точек от {self.freq_list[0]} до {self.freq_list[-1]} МГц')

        try:
            self.save_ui_settings()
        except Exception:
            pass
    
    def add_beam(self):
        """Добавить луч в список"""
        try:
            beam_num = int(self.add_beam_edit.text())
            if beam_num < 1 or beam_num > 10000:
                raise ValueError("Номер луча должен быть от 1 до 10000")
            
            # Проверка дубликатов
            for i in range(self.beam_list_widget.count()):
                item = self.beam_list_widget.item(i)
                if item.data(QtCore.Qt.UserRole) == beam_num:
                    logger.warning(f"Луч {beam_num} уже добавлен")
                    return

            item = QtWidgets.QListWidgetItem(f'Луч {beam_num}')
            item.setData(QtCore.Qt.UserRole, beam_num)
            item.setFlags(item.flags() | QtCore.Qt.ItemIsUserCheckable)
            item.setCheckState(QtCore.Qt.Checked)
            self.beam_list_widget.addItem(item)
            
            self.add_beam_edit.clear()
            logger.info(f"Добавлен луч {beam_num}")
            
        except ValueError as e:
            logger.error(f"Ошибка добавления луча: {e}")
    
    def remove_selected_beam(self):
        """Удалить выбранный луч из списка"""
        current_row = self.beam_list_widget.currentRow()
        if current_row >= 0:
            item = self.beam_list_widget.takeItem(current_row)
            beam_num = item.data(QtCore.Qt.UserRole)
            logger.info(f"Удален луч {beam_num}")
        else:
            logger.warning("Не выбран луч для удаления")
    
    def clear_all_beams(self):
        """Очистить все лучи из списка"""
        self.beam_list_widget.clear()
        logger.info("Все лучи удалены")
    
    def load_folder_for_rescan(self):
        """Загрузить папку с сохраненными результатами для досканирования"""
        base_dir = self.device_settings.get('base_save_dir', '').strip() or ''
        if not base_dir:
            self.show_error_message("Ошибка", "Не задана базовая директория для сохранения. Укажите её в настройках.")
            return

        luchi_dir = os.path.join(base_dir, 'beams\scan_beams')
        if not os.path.exists(luchi_dir):
            os.makedirs(luchi_dir, exist_ok=True)

        folder_path = QFileDialog.getExistingDirectory(
            self,
            "Выберите папку с результатами для продолжения сканирования",
            luchi_dir,
            QFileDialog.ShowDirsOnly | QFileDialog.DontResolveSymlinks
        )
        
        if not folder_path:
            return

        # Показываем диалог загрузки
        progress_dialog = QProgressDialog(
            "Загрузка данных для досканирования...\nПожалуйста, подождите.",
            "Отмена",
            0,
            0,
            self
        )
        progress_dialog.setWindowTitle("Загрузка данных")
        progress_dialog.setWindowModality(QtCore.Qt.WindowModal)
        progress_dialog.setMinimumDuration(0)  # Показываем сразу
        progress_dialog.setCancelButton(None)  # Убираем кнопку отмены (загрузка должна завершиться)
        progress_dialog.setRange(0, 0)  # Неопределенный прогресс
        progress_dialog.show()
        
        # Обновляем интерфейс, чтобы диалог отобразился
        QtWidgets.QApplication.processEvents()

        # Создаем и запускаем поток загрузки
        self._load_rescan_thread = LoadRescanWorker(folder_path)
        self._load_rescan_thread.finished_signal.connect(
            lambda data: self._on_rescan_data_loaded(data, folder_path, progress_dialog)
        )
        self._load_rescan_thread.error_signal.connect(
            lambda error: self._on_rescan_load_error(error, progress_dialog)
        )
        self._load_rescan_thread.start()
    
    def _on_rescan_data_loaded(self, loaded_data: dict, folder_path: str, progress_dialog: QProgressDialog):
        """Обработчик успешной загрузки данных досканирования"""
        try:
            # Обновляем текст диалога для обработки данных
            progress_dialog.setLabelText("Очистка старых данных...\nПожалуйста, подождите.")
            QtWidgets.QApplication.processEvents()
            
            # Очищаем старые данные и графики
            self.measurement_data.clear()
            self.amp_plot.clear()
            self.phase_plot.clear()
            self.amp_rect_items.clear()
            self.phase_rect_items.clear()
            
            # Обновляем UI
            QtWidgets.QApplication.processEvents()
            
            progress_dialog.setLabelText("Обработка данных...\nПожалуйста, подождите.")
            QtWidgets.QApplication.processEvents()
            
            logger.info(f"Загружены данные для досканирования из {folder_path}")

            # Сохраняем данные
            self.rescan_data = loaded_data
            self.rescan_save_dir = folder_path
            
            # Обновляем UI для отображения прогресса
            QtWidgets.QApplication.processEvents()
            
            # Восстанавливаем параметры UI
            progress_dialog.setLabelText("Восстановление параметров...\nПожалуйста, подождите.")
            QtWidgets.QApplication.processEvents()
            self._restore_params_from_loaded_data(loaded_data)
            
            # Обновляем UI
            QtWidgets.QApplication.processEvents()
            
            # Используем ссылку на данные вместо глубокого копирования для ускорения
            # Данные из загруженного файла не изменяются, поэтому можно использовать ссылку
            progress_dialog.setLabelText("Подготовка данных...\nПожалуйста, подождите.")
            QtWidgets.QApplication.processEvents()
            # Просто используем ссылку - это намного быстрее, чем глубокое копирование
            self.measurement_data = loaded_data['data']
            
            # Обновляем UI
            QtWidgets.QApplication.processEvents()
            
            # Инициализируем комбобоксы
            progress_dialog.setLabelText("Инициализация интерфейса...\nПожалуйста, подождите.")
            QtWidgets.QApplication.processEvents()
            self.initialize_view_combos(loaded_data['beams'], loaded_data['freq_list'])
            
            # Обновляем UI перед отрисовкой графиков
            QtWidgets.QApplication.processEvents()
            
            # Закрываем диалог перед отрисовкой графиков
            progress_dialog.close()
            
            # Отрисовку графиков делаем отложенной на большее время, чтобы интерфейс успел обновиться
            # Графики отрисуются только когда пользователь переключится на луч/частоту
            QtCore.QTimer.singleShot(200, lambda: self._finalize_rescan_load(loaded_data))
            
        except Exception as e:
            progress_dialog.close()
            logger.error(f"Ошибка при обработке загруженных данных: {e}", exc_info=True)
            self.show_error_message("Ошибка", f"Не удалось обработать загруженные данные: {str(e)}")
            self._load_rescan_thread = None
    
    def _finalize_rescan_load(self, loaded_data: dict):
        """Завершающая обработка после загрузки данных досканирования"""
        try:
            # Отрисовываем графики только для текущего выбранного луча/частоты
            # Остальные отрисуются по требованию при переключении
            # Это намного быстрее, чем отрисовывать все данные сразу
            self.update_plots()
            
            logger.info("Параметры и данные восстановлены. Можно нажать 'Старт' для продолжения сканирования.")
            self.show_info_message("Данные загружены", 
                                  f"Загружены данные для {len(loaded_data['beams'])} лучей, "
                                  f"{len(loaded_data['freq_list'])} частот. "
                                  f"Нажмите 'Старт' для продолжения сканирования.")
        except Exception as e:
            logger.error(f"Ошибка при финализации загрузки: {e}", exc_info=True)
            self.show_error_message("Ошибка", f"Не удалось завершить обработку данных: {str(e)}")
        finally:
            self._load_rescan_thread = None
    
    def _on_rescan_load_error(self, error_msg: str, progress_dialog: QProgressDialog):
        """Обработчик ошибки загрузки данных досканирования"""
        progress_dialog.close()
        logger.error(f"Ошибка при загрузке папки для досканирования: {error_msg}")
        self.show_error_message("Ошибка загрузки", error_msg)
        self._load_rescan_thread = None
    
    def _restore_params_from_loaded_data(self, loaded_data: dict):
        """Восстанавливает параметры UI из загруженных данных"""
        try:
            self.beam_list_widget.clear()
            for beam_num in loaded_data['beams']:
                item = QtWidgets.QListWidgetItem(f'Луч {beam_num}')
                item.setData(QtCore.Qt.UserRole, beam_num)
                item.setFlags(item.flags() | QtCore.Qt.ItemIsUserCheckable)
                item.setCheckState(QtCore.Qt.Checked)
                self.beam_list_widget.addItem(item)

            if loaded_data['freq_list']:
                self.freq_list = loaded_data['freq_list']
                if len(loaded_data['freq_list']) > 0:
                    self.pna_start_freq.setValue(int(loaded_data['freq_list'][0]))
                    self.pna_stop_freq.setValue(int(loaded_data['freq_list'][-1]))
                    self.pna_number_of_points.setCurrentText(str(len(loaded_data['freq_list'])))

            # Конвертируем значения из мм в см для отображения в UI
            if loaded_data.get('step_x'):
                self.step_x.setValue(float(loaded_data['step_x']))
            if loaded_data.get('step_y'):
                self.step_y.setValue(float(loaded_data['step_y']))

            if loaded_data.get('left_x') is not None:
                self.left_x.setValue(float(loaded_data['left_x']))
            if loaded_data.get('right_x') is not None:
                self.right_x.setValue(float(loaded_data['right_x']))
            if loaded_data.get('up_y') is not None:
                self.up_y.setValue(float(loaded_data['up_y']))
            if loaded_data.get('down_y') is not None:
                self.down_y.setValue(float(loaded_data['down_y']))

            if loaded_data.get('pna_settings'):
                pna_params = loaded_data['pna_settings']
                if 's_param' in pna_params:
                    idx = self.s_param_combo.findText(pna_params['s_param'])
                    if idx >= 0:
                        self.s_param_combo.setCurrentIndex(idx)
                if 'power' in pna_params:
                    self.pna_power.setValue(float(pna_params['power']))
                if 'freq_start' in pna_params:
                    self.pna_start_freq.setValue(int(float(pna_params['freq_start']) / 1e6))
                if 'freq_stop' in pna_params:
                    self.pna_stop_freq.setValue(int(float(pna_params['freq_stop']) / 1e6))
                if 'freq_points' in pna_params:
                    idx = self.pna_number_of_points.findText(str(int(pna_params['freq_points'])))
                    if idx >= 0:
                        self.pna_number_of_points.setCurrentIndex(idx)
                if 'settings_file' in pna_params:
                    self.settings_file_edit.setText(str(pna_params['settings_file']))
                if 'pulse_mode' in pna_params:
                    idx = self.pulse_mode_combo.findText(pna_params['pulse_mode'])
                    if idx >= 0:
                        self.pulse_mode_combo.setCurrentIndex(idx)
                if 'pulse_period' in pna_params:
                    self.pulse_period.setValue(float(pna_params['pulse_period']) * 1e6)
                if 'pulse_width' in pna_params:
                    self.pulse_width.setValue(float(pna_params['pulse_width']) * 1e6)

            if loaded_data.get('sync_settings'):
                sync_params = loaded_data['sync_settings']
                if 'trig_ttl_channel' in sync_params:
                    idx = self.trig_ttl_channel.findText(sync_params['trig_ttl_channel'])
                    if idx >= 0:
                        self.trig_ttl_channel.setCurrentIndex(idx)
                if 'trig_ext_channel' in sync_params:
                    idx = self.trig_ext_channel.findText(sync_params['trig_ext_channel'])
                    if idx >= 0:
                        self.trig_ext_channel.setCurrentIndex(idx)
                if 'trig_start_lead' in sync_params:
                    self.trig_start_lead.setValue(float(sync_params['trig_start_lead']) * 1000)  # сек -> мс
                if 'trig_pulse_period' in sync_params:
                    self.trig_pulse_period.setValue(float(sync_params['trig_pulse_period']) * 1e6)  # сек -> мкс
                if 'trig_min_alarm_guard' in sync_params:
                    self.trig_min_alarm_guard.setValue(float(sync_params['trig_min_alarm_guard']) * 1e6)  # сек -> мкс
                if 'trig_ext_debounce' in sync_params:
                    self.trig_ext_debounce.setValue(float(sync_params['trig_ext_debounce']) * 1000)  # сек -> мс
            
            logger.info("Параметры UI восстановлены из загруженных данных")
            
        except Exception as e:
            logger.error(f"Ошибка при восстановлении параметров: {e}", exc_info=True)
    
    def get_selected_beams(self) -> list:
        """Получить список выбранных лучей"""
        beams = []
        for i in range(self.beam_list_widget.count()):
            item = self.beam_list_widget.item(i)
            if item.checkState() == QtCore.Qt.Checked:
                beams.append(item.data(QtCore.Qt.UserRole))
        return beams

    
    def on_bu_selection_mode_changed(self, button):
        """Обработчик изменения режима выбора БУ"""
        if button == self.all_bu_radio:
            self.bu_start_spin.setEnabled(False)
            self.bu_end_spin.setEnabled(False)
            self.bu_list_widget.setEnabled(False)
            self.select_all_bu_btn.setEnabled(False)
            self.clear_all_bu_btn.setEnabled(False)
            self.section_spin.setEnabled(False)
            self.section_type_label.setEnabled(False)
        elif button == self.range_bu_radio:
            self.bu_start_spin.setEnabled(True)
            self.bu_end_spin.setEnabled(True)
            self.bu_list_widget.setEnabled(False)
            self.select_all_bu_btn.setEnabled(False)
            self.clear_all_bu_btn.setEnabled(False)
            self.section_spin.setEnabled(False)
            self.section_type_label.setEnabled(False)
        elif button == self.custom_bu_radio:
            self.bu_start_spin.setEnabled(False)
            self.bu_end_spin.setEnabled(False)
            self.bu_list_widget.setEnabled(True)
            self.select_all_bu_btn.setEnabled(True)
            self.clear_all_bu_btn.setEnabled(True)
            self.section_spin.setEnabled(False)
            self.section_type_label.setEnabled(False)
        elif button == self.section_x_radio:
            self.bu_start_spin.setEnabled(False)
            self.bu_end_spin.setEnabled(False)
            self.bu_list_widget.setEnabled(False)
            self.select_all_bu_btn.setEnabled(False)
            self.clear_all_bu_btn.setEnabled(False)
            self.section_spin.setEnabled(True)
            self.section_type_label.setEnabled(True)
            self.section_type_label.setText('(X)')
            self.section_spin.setRange(1, 8)
        elif button == self.section_y_radio:
            self.bu_start_spin.setEnabled(False)
            self.bu_end_spin.setEnabled(False)
            self.bu_list_widget.setEnabled(False)
            self.select_all_bu_btn.setEnabled(False)
            self.clear_all_bu_btn.setEnabled(False)
            self.section_spin.setEnabled(True)
            self.section_type_label.setEnabled(True)
            self.section_type_label.setText('(Y)')
            self.section_spin.setRange(1, 5)
    
    def on_range_changed(self):
        """Обработчик изменения диапазона БУ"""
        start = self.bu_start_spin.value()
        end = self.bu_end_spin.value()
        if start > end:
            self.bu_end_spin.setValue(start)
    
    def select_all_bu(self):
        """Выбирает все БУ в списке"""
        for i in range(self.bu_list_widget.count()):
            item = self.bu_list_widget.item(i)
            item.setCheckState(QtCore.Qt.Checked)
    
    def clear_all_bu(self):
        """Очищает выбор всех БУ в списке"""
        for i in range(self.bu_list_widget.count()):
            item = self.bu_list_widget.item(i)
            item.setCheckState(QtCore.Qt.Unchecked)
    
    def get_selected_bu_numbers(self):
        """Возвращает список номеров выбранных БУ"""
        if self.all_bu_radio.isChecked():
            return list(range(1, 41))
        elif self.range_bu_radio.isChecked():
            start = self.bu_start_spin.value()
            end = self.bu_end_spin.value()
            return list(range(start, end + 1))
        elif self.custom_bu_radio.isChecked():
            selected_bu = []
            for i in range(self.bu_list_widget.count()):
                item = self.bu_list_widget.item(i)
                if item.checkState() == QtCore.Qt.Checked:
                    selected_bu.append(item.data(QtCore.Qt.UserRole))
            return selected_bu
        elif self.section_x_radio.isChecked():
            section = self.section_spin.value()
            return self._get_bu_numbers_by_x_section(section)
        elif self.section_y_radio.isChecked():
            section = self.section_spin.value()
            return self._get_bu_numbers_by_y_section(section)
        return []
    
    def _get_bu_numbers_by_x_section(self, section: int):
        """Возвращает номера БУ для секции по X"""
        bu_numbers = []
        for y in range(5):  # 5 рядов по Y
            bu_num = (y * 8) + section
            if 1 <= bu_num <= 40:
                bu_numbers.append(bu_num)
        return bu_numbers
    
    def _get_bu_numbers_by_y_section(self, section: int):
        """Возвращает номера БУ для секции по Y"""
        bu_numbers = []
        start_bu = (section - 1) * 8 + 1
        end_bu = section * 8
        for bu_num in range(start_bu, end_bu + 1):
            if 1 <= bu_num <= 40:
                bu_numbers.append(bu_num)
        return bu_numbers
    

    def start_measurement(self):
        """Начать измерение"""
        logger.info("=== Нажата кнопка СТАРТ ===")

        logger.debug(f"PNA подключен: {self.pna is not None}")
        logger.debug(f"АФАР подключен: {self.afar is not None}")
        
        if not self.pna:
            logger.error("PNA не подключен!")
            self.show_error_message("Ошибка", "Сначала подключите Анализатор (PNA)!\n\nНажмите кнопку 'Анализатор' для подключения.")
            return
        
        if not self.afar:
            logger.error("АФАР не подключен!")
            self.show_error_message("Ошибка", "Сначала подключите АФАР!\n\nНажмите кнопку 'АФАР' для подключения.")
            return
        
        beams = self.get_selected_beams()
        logger.debug(f"Выбранные лучи: {beams}")
        
        if not beams:
            logger.error("Не выбраны лучи для измерения!")
            self.show_error_message("Ошибка", "Не выбраны лучи для измерения!\n\nДобавьте лучи в список и отметьте их галочками.")
            return

        # Конвертируем значения из см в мм для передачи в сканер
        scan_params = {
            'left_x': self.left_x.value(),
            'right_x': self.right_x.value(),
            'up_y': self.up_y.value(),
            'down_y': self.down_y.value(),
            'step_x': self.step_x.value() ,
            'step_y': self.step_y.value()
        }

        self.apply_params()

        if not self.freq_list:
            logger.error("Список частот пуст! Проверьте настройки PNA.")
            self.show_error_message("Ошибка", "Список частот пуст!\n\nПроверьте настройки анализатора (частоты и количество точек).")
            return
        
        logger.info(f"Начало измерения: {len(beams)} лучей, {len(self.freq_list)} частот")
        logger.info(f"Частоты: {self.freq_list} МГц")
        logger.info(f"Параметры сканирования: X=[{scan_params['left_x']:.2f}, {scan_params['right_x']:.2f}], Y=[{scan_params['up_y']:.2f}, {scan_params['down_y']:.2f}]")
        logger.info(f"Шаги: step_x={scan_params['step_x']:.4f}, step_y={scan_params['step_y']:.4f}")
        
        # Проверяем, есть ли загруженные данные для досканирования
        if self.rescan_data and self.rescan_save_dir:
            # Используем загруженные данные для досканирования
            logger.info("Используются загруженные данные для досканирования")
            # Используем параметры сканирования из UI (не из загруженных данных, т.к. там индексы)
            # Параметры должны быть указаны пользователем в UI перед продолжением
            beams = self.rescan_data['beams']
            self.freq_list = self.rescan_data['freq_list']
            # Используем загруженные данные как начальные
            self.measurement_data = self.rescan_data['data'].copy()
            base_save_dir = self.rescan_save_dir  # Используем ту же папку для сохранения
        else:
            # Очищаем данные для нового измерения
            self.measurement_data.clear()
            base_save_dir = self.device_settings.get('base_save_dir', '').strip() or ''

        self.amp_plot.clear()
        self.phase_plot.clear()
        self.amp_rect_items.clear()
        self.phase_rect_items.clear()


        self.measurement_start_time = QtCore.QDateTime.currentDateTime()
        self.last_progress_time = None
        self.last_estimated_remaining = 0

        self.time_update_timer.start(1000)

        self.initialize_view_combos(beams, self.freq_list)

        # Настройка сканера с учетом системы координат
        if self.psn:
            self.setup_scanner_common()

        measurement = BeamMeasurement(self.afar, self.pna, self.trigger, self.psn, base_save_dir=base_save_dir)

        if self.rescan_data and self.rescan_save_dir:
            measurement.data = self.rescan_data['data'].copy()
            measurement.save_dir = self.rescan_save_dir

        measurement.period = self.pna_settings.get('trig_pulse_period', 500e-6)  # период в секундах
        measurement.lead = self.pna_settings.get('trig_start_lead', 25e-3)  # задержка старта в секундах
        measurement.number_of_freqs = len(self.freq_list)  # количество импульсов = количество частот
        

        self.apply_params()

        self._measurement_thread = BeamMeasurementWorker(
            measurement, beams, scan_params, self.freq_list,
            pna_settings=self.pna_settings,
            sync_settings=self.sync_settings
        )
        self._measurement_thread.progress_signal.connect(self.on_progress)
        self._measurement_thread.data_signal.connect(self.on_data_update)
        self._measurement_thread.finished_signal.connect(self.on_measurement_finished)
        self._measurement_thread.error_signal.connect(self.on_measurement_error)
        self._measurement_thread.start()

        self.set_buttons_enabled(False)
    
    def pause_measurement(self):
        """Обработчик нажатия кнопки паузы"""
        if not self._measurement_thread or not self._measurement_thread.isRunning():
            return
        
        measurement = self._measurement_thread.measurement

        if measurement._pause_flag.is_set():
            logger.info('Пауза измерения...')
            measurement.pause()
            self.pause_btn.setText('Продолжить')
        else:
            logger.info('Возобновление измерения...')
            measurement.resume()
            self.pause_btn.setText('Пауза')
    
    def stop_measurement(self):
        """Остановить измерение"""
        logger.info('Остановка измерения...')
        
        if self._measurement_thread and self._measurement_thread.isRunning():
            measurement = self._measurement_thread.measurement
            measurement.stop()
            self._measurement_thread.wait(2000)
        
        self.time_update_timer.stop()
        self.set_buttons_enabled(True)
        self.pause_btn.setText('Пауза')
    
    @QtCore.pyqtSlot(int, int, str, int, int)
    def on_progress(self, current, total, message, elapsed_time, estimated_remaining):
        """Обновление прогресса с адаптивным расчетом времени"""
        logger.debug(f"Прогресс: {current}/{total} - {message}")

        self.last_progress_time = QtCore.QDateTime.currentDateTime()
        self.last_estimated_remaining = estimated_remaining

        elapsed_str = self._format_time(elapsed_time)
        self.elapsed_time_label.setText(f'Прошло: {elapsed_str}')
        
        remaining_str = self._format_time(estimated_remaining)
        self.remaining_time_label.setText(f'Осталось: {remaining_str}')
    
    @QtCore.pyqtSlot(dict)
    def on_data_update(self, data):
        """
        Обновление данных в реальном времени
        """
        self.measurement_data.update(data)
        
        # Если GUI сейчас занят отрисовкой - сохраняем данные и выходим
        if self._is_updating_plots:
            self._pending_data_update = data
            return
        
        # Если обновление уже запланировано - просто обновляем данные
        if self._update_pending:
            self._pending_data_update = data
            return

        self._update_pending = True
        QtCore.QTimer.singleShot(0, self._do_plot_update)
    
    def _do_plot_update(self):
        """
        Выполняет отрисовку графиков (вызывается отложенно через event loop)
        После завершения проверяет, есть ли еще данные для обновления
        """
        try:
            self._is_updating_plots = True
            self._update_pending = False
            
            # Обновляем только текущий видимый луч/частоту (не все данные)
            self.update_plots()
            
        except Exception as e:
            logger.error(f"GUI: Ошибка при обновлении графиков: {e}", exc_info=True)
        finally:
            self._is_updating_plots = False
            
            # Если во время отрисовки пришли новые данные - планируем еще одно обновление
            if self._pending_data_update is not None:
                self._pending_data_update = None
                if not self._update_pending:
                    self._update_pending = True
                    QtCore.QTimer.singleShot(0, self._do_plot_update)
    
    @QtCore.pyqtSlot(int, int, dict)
    def on_measurement_update(self, beam_num, freq, data):
        """Обновление данных при получении нового измерения (2D)"""
        if beam_num not in self.measurement_data:
            self.measurement_data[beam_num] = {}
        if freq not in self.measurement_data[beam_num]:
            self.measurement_data[beam_num][freq] = {}
        self.measurement_data[beam_num][freq].update(data)
        
        self.update_view_combos()
        self.update_plots()
    
    @QtCore.pyqtSlot(dict)
    def on_measurement_finished(self, data):
        """Измерение завершено"""
        self.time_update_timer.stop()
        logger.info("Измерение завершено успешно!")
        self.measurement_data = data
        self.update_view_combos()
        self.update_plots()
        self.set_buttons_enabled(True)
    
    @QtCore.pyqtSlot(str)
    def on_measurement_error(self, error_msg):
        """Ошибка измерения"""
        self.time_update_timer.stop()
        logger.error(f"Ошибка измерения: {error_msg}")
        self.show_error_message("Ошибка измерения", error_msg)
        self.set_buttons_enabled(True)
    
    def update_time_labels(self):
        """
        Обновление таймеров (прошло / осталось)
        Использует адаптивный расчет: корректирует оставшееся время на основе прошедшего времени
        """
        if not self.measurement_start_time:
            return

        elapsed_secs = self.measurement_start_time.secsTo(QtCore.QDateTime.currentDateTime())
        elapsed_str = self._format_time(elapsed_secs)
        self.elapsed_time_label.setText(f'Прошло: {elapsed_str}')

        if self.last_progress_time:
            secs_since_progress = self.last_progress_time.secsTo(QtCore.QDateTime.currentDateTime())
            adjusted_remaining = max(0, self.last_estimated_remaining - secs_since_progress)
            remaining_str = self._format_time(int(adjusted_remaining))
            self.remaining_time_label.setText(f'Осталось: {remaining_str}')
        else:
            self.remaining_time_label.setText('Осталось: --:--:--')
    
    def _format_time(self, seconds: int) -> str:
        """Форматирует секунды в HH:MM:SS"""
        hours = seconds // 3600
        minutes = (seconds % 3600) // 60
        secs = seconds % 60
        return f"{hours:02d}:{minutes:02d}:{secs:02d}"

    
    def initialize_view_combos(self, beams, freq_list):
        """Инициализировать комбобоксы всеми лучами и частотами при старте измерения"""
        # Блокируем сигналы, чтобы не вызывать update_plots при заполнении
        self.view_beam_combo.blockSignals(True)
        self.view_freq_combo.blockSignals(True)
        
        # Заполняем лучи
        self.view_beam_combo.clear()
        for beam in sorted(beams):
            self.view_beam_combo.addItem(f"Луч {beam}", beam)
        
        # Заполняем частоты
        self.view_freq_combo.clear()
        for freq in freq_list:
            self.view_freq_combo.addItem(f"{freq} МГц", freq)
        
        # Выбираем первые элементы
        if self.view_beam_combo.count() > 0:
            self.view_beam_combo.setCurrentIndex(0)
        if self.view_freq_combo.count() > 0:
            self.view_freq_combo.setCurrentIndex(0)
        
        # Разблокируем сигналы
        self.view_beam_combo.blockSignals(False)
        self.view_freq_combo.blockSignals(False)
        
        # Обновляем состояние кнопок навигации
        self.update_nav_buttons()
        
        logger.info(f"Комбобоксы инициализированы: {len(beams)} лучей, {len(freq_list)} частот")
    
    def update_view_combos(self):
        """Обновить комбобоксы просмотра"""
        if not self.measurement_data:
            return
        
        # Запоминаем текущий выбор
        current_beam = self.view_beam_combo.currentData()
        current_freq = self.view_freq_combo.currentData()
        
        # Лучи
        beams = list(self.measurement_data.keys())
        
        self.view_beam_combo.clear()
        for beam in sorted(beams):
            self.view_beam_combo.addItem(f"Луч {beam}", beam)
        
        # Восстанавливаем или выбираем первый
        if current_beam in beams:
            idx = self.view_beam_combo.findData(current_beam)
            if idx >= 0:
                self.view_beam_combo.setCurrentIndex(idx)
        elif self.view_beam_combo.count() > 0:
            self.view_beam_combo.setCurrentIndex(0)
        
        # Частоты
        if beams:
            selected_beam = self.view_beam_combo.currentData()
            if selected_beam and selected_beam in self.measurement_data:
                freqs = list(self.measurement_data[selected_beam].keys())
                
                self.view_freq_combo.clear()
                for freq in freqs:
                    self.view_freq_combo.addItem(f"{freq} МГц", freq)
                
                # Восстанавливаем или выбираем первый
                if current_freq in freqs:
                    idx = self.view_freq_combo.findData(current_freq)
                    if idx >= 0:
                        self.view_freq_combo.setCurrentIndex(idx)
                elif self.view_freq_combo.count() > 0:
                    self.view_freq_combo.setCurrentIndex(0)
    
    def update_plots(self):
        """Обновить 2D графики амплитуды и фазы через прямоугольники (как в phase_afar)"""
        beam = self.view_beam_combo.currentData()
        freq = self.view_freq_combo.currentData()
        
        if beam is None or freq is None:
            return
        
        # Проверяем наличие данных для выбранного луча и частоты
        if not self.measurement_data:
            # Очищаем графики, если данных вообще нет
            self.amp_plot.clear()
            self.phase_plot.clear()
            self.amp_rect_items.clear()
            self.phase_rect_items.clear()
            return
        
        if beam not in self.measurement_data:
            # Луч еще не начал измеряться - очищаем графики
            self.amp_plot.clear()
            self.phase_plot.clear()
            self.amp_rect_items.clear()
            self.phase_rect_items.clear()
            return
        
        if freq not in self.measurement_data[beam]:
            # Данные для этой частоты еще не измерены - очищаем графики
            self.amp_plot.clear()
            self.phase_plot.clear()
            self.amp_rect_items.clear()
            self.phase_rect_items.clear()
            return
        
        data = self.measurement_data[beam][freq]
        
        # Получаем координаты и 2D массивы
        x_coords = data.get('x', [])
        y_coords = data.get('y', [])
        amp_2d = np.array(data.get('amp', []))
        phase_2d = np.array(data.get('phase', []))
        
        if amp_2d.size == 0 or phase_2d.size == 0 or not x_coords or not y_coords:
            return
        
        # Вычисляем размеры прямоугольников
        if len(x_coords) > 1:
            dx = abs(x_coords[1] - x_coords[0])
        else:
            dx = 1
        
        if len(y_coords) > 1:
            dy = abs(y_coords[1] - y_coords[0])
        else:
            dy = 1
        
        # Определяем диапазоны значений для цветовой карты
        amp_min, amp_max = np.nanmin(amp_2d), np.nanmax(amp_2d)
        phase_min, phase_max = np.nanmin(phase_2d), np.nanmax(phase_2d)
        
        # Цветовая карта для амплитуды: минимум - синий, центр - желтый, максимум - красный
        amp_cmap = pg.ColorMap(
            pos=np.array([0.0, 0.5, 1.0]),
            color=np.array([[0, 0, 255, 255],    # Синий (минимум)
                          [255, 255, 0, 255],   # Желтый (центр)
                          [255, 0, 0, 255]], dtype=np.ubyte)  # Красный (максимум)
        )
        
        # Цветовая карта для фазы (с гарантированной инициализацией)
        phase_cmap = None
        try:
            phase_cmap = pg.colormap.get('CET-C2', source='colorcet')
        except:
            pass
        
        if phase_cmap is None:
            try:
                phase_cmap = pg.colormap.get('bipolar')
            except:
                pass
        
        if phase_cmap is None:
            # Создаем циклическую карту вручную (гарантированно работает)
            phase_cmap = pg.ColorMap(
                pos=np.array([0.0, 0.25, 0.5, 0.75, 1.0]),
                color=np.array([[255, 0, 0, 255], [255, 255, 0, 255], [0, 255, 0, 255], 
                               [0, 255, 255, 255], [255, 0, 0, 255]], dtype=np.ubyte)
            )
        
        # Проверяем размеры массивов и координат
        amp_shape = amp_2d.shape
        phase_shape = phase_2d.shape
        
        # Проверяем несоответствие размеров (предупреждение)
        if len(y_coords) != amp_shape[0] or len(x_coords) != amp_shape[1]:
            logger.warning(
                f"Несоответствие размеров: y_coords={len(y_coords)}, x_coords={len(x_coords)}, "
                f"amp_shape={amp_shape}, phase_shape={phase_shape}. "
                f"Используются минимальные размеры."
            )
        
        # Ограничиваем индексы размерами массивов
        max_y_idx = min(len(y_coords), amp_shape[0], phase_shape[0])
        max_x_idx = min(len(x_coords), amp_shape[1], phase_shape[1])
        
        # Всегда используем быструю отрисовку через ImageItem для всех данных
        self._update_plots_fast(amp_2d, phase_2d, x_coords, y_coords, 
                               max_x_idx, max_y_idx, amp_min, amp_max, 
                               phase_min, phase_max, amp_cmap, phase_cmap)
    
    def _update_plots_fast(self, amp_2d, phase_2d, x_coords, y_coords,
                           max_x_idx, max_y_idx, amp_min, amp_max,
                           phase_min, phase_max, amp_cmap, phase_cmap):
        """Быстрая отрисовка через ImageItem для больших данных"""
        # Очищаем старые элементы
        self.amp_plot.clear()
        self.phase_plot.clear()
        self.amp_rect_items.clear()
        self.phase_rect_items.clear()
        
        # Обрезаем массивы до нужного размера
        amp_cropped = amp_2d[:max_y_idx, :max_x_idx]
        phase_cropped = phase_2d[:max_y_idx, :max_x_idx]
        
        # Определяем границы для ImageItem
        x_min, x_max = min(x_coords[:max_x_idx]), max(x_coords[:max_x_idx])
        y_min, y_max = min(y_coords[:max_y_idx]), max(y_coords[:max_y_idx])
        
        # Вычисляем размеры пикселей
        if max_x_idx > 1:
            x_step = (x_max - x_min) / (max_x_idx - 1)
        else:
            x_step = 1
        if max_y_idx > 1:
            y_step = (y_max - y_min) / (max_y_idx - 1)
        else:
            y_step = 1
        
        # Нормализуем данные для цветовой карты
        amp_normalized = (amp_cropped - amp_min) / (amp_max - amp_min) if amp_max != amp_min else np.zeros_like(amp_cropped)
        phase_normalized = (phase_cropped - phase_min) / (phase_max - phase_min) if phase_max != phase_min else np.zeros_like(phase_cropped)
        
        # Заменяем NaN на 0 для нормализованных массивов
        amp_normalized = np.nan_to_num(amp_normalized, nan=0.0)
        phase_normalized = np.nan_to_num(phase_normalized, nan=0.0)
        
        # Применяем цветовую карту через lookup table
        try:
            # Используем lookup table для быстрого преобразования
            # Создаем lookup table из 256 значений
            lut_size = 256
            amp_lut = np.zeros((lut_size, 4), dtype=np.ubyte)
            phase_lut = np.zeros((lut_size, 4), dtype=np.ubyte)
            
            for i in range(lut_size):
                val = i / (lut_size - 1)
                # Получаем цвет из colormap
                try:
                    amp_color = amp_cmap.map(val, mode='qcolor')
                    if hasattr(amp_color, 'getRgb'):
                        r, g, b, a = amp_color.getRgb()
                        amp_lut[i] = [r, g, b, a]
                    
                    phase_color = phase_cmap.map(val, mode='qcolor')
                    if hasattr(phase_color, 'getRgb'):
                        r, g, b, a = phase_color.getRgb()
                        phase_lut[i] = [r, g, b, a]
                except:
                    pass
            
            # Преобразуем нормализованные значения в индексы lookup table (0-255)
            amp_indices = np.clip((amp_normalized * (lut_size - 1)).astype(np.uint8), 0, lut_size - 1)
            phase_indices = np.clip((phase_normalized * (lut_size - 1)).astype(np.uint8), 0, lut_size - 1)
            
            # Применяем lookup table
            amp_rgba = amp_lut[amp_indices]
            phase_rgba = phase_lut[phase_indices]
            
            # Создаем ImageItem для амплитуды
            # setRect принимает (x, y, width, height), где x,y - левый верхний угол
            amp_img = pg.ImageItem(image=amp_rgba, axisOrder='row-major')
            amp_img.setRect(QtCore.QRectF(x_min - x_step/2, y_min - y_step/2, 
                                         (x_max - x_min) + x_step, (y_max - y_min) + y_step))
            self.amp_plot.addItem(amp_img)
            
            # Создаем ImageItem для фазы
            phase_img = pg.ImageItem(image=phase_rgba, axisOrder='row-major')
            phase_img.setRect(QtCore.QRectF(x_min - x_step/2, y_min - y_step/2,
                                          (x_max - x_min) + x_step, (y_max - y_min) + y_step))
            self.phase_plot.addItem(phase_img)
        except Exception as e:
            logger.warning(f"Не удалось использовать быструю отрисовку: {e}. Используем прямоугольники.", exc_info=True)
            # Fallback на прямоугольники
            dx = abs(x_coords[1] - x_coords[0]) if len(x_coords) > 1 else 1
            dy = abs(y_coords[1] - y_coords[0]) if len(y_coords) > 1 else 1
            self._update_plots_rectangles(amp_2d, phase_2d, x_coords, y_coords,
                                         max_x_idx, max_y_idx, dx, dy,
                                         amp_min, amp_max, phase_min, phase_max,
                                         amp_cmap, phase_cmap)
    
    def _update_plots_rectangles(self, amp_2d, phase_2d, x_coords, y_coords,
                                max_x_idx, max_y_idx, dx, dy,
                                amp_min, amp_max, phase_min, phase_max,
                                amp_cmap, phase_cmap):
        """Медленная, но точная отрисовка через прямоугольники"""
        total_points = max_y_idx * max_x_idx
        update_interval = max(100, total_points // 20)  # Обновляем UI каждые 5% или минимум каждые 100 точек
        point_count = 0
        
        # Отрисовываем прямоугольники
        for y_idx, y in enumerate(y_coords):
            if y_idx >= max_y_idx:
                break
            for x_idx, x in enumerate(x_coords):
                if x_idx >= max_x_idx:
                    break
                amp_val = amp_2d[y_idx, x_idx]
                phase_val = phase_2d[y_idx, x_idx]
                
                # Пропускаем NaN
                if np.isnan(amp_val) or np.isnan(phase_val):
                    continue
                
                key = (x, y)
                
                # Амплитуда
                rect_amp = self.amp_rect_items.get(key)
                if rect_amp is None:
                    from PyQt5.QtWidgets import QGraphicsRectItem
                    rect_amp = QGraphicsRectItem(x - dx/2, y - dy/2, dx, dy)
                    self.amp_plot.addItem(rect_amp)
                    self.amp_rect_items[key] = rect_amp
                else:
                    rect_amp.setRect(x - dx/2, y - dy/2, dx, dy)
                
                # Нормализуем значение амплитуды и получаем цвет
                amp_norm = (amp_val - amp_min) / (amp_max - amp_min) if amp_max != amp_min else 0.5
                amp_color = amp_cmap.map(amp_norm, mode='qcolor')
                rect_amp.setBrush(pg.mkBrush(amp_color))
                rect_amp.setPen(pg.mkPen(None))
                
                # Фаза
                rect_phase = self.phase_rect_items.get(key)
                if rect_phase is None:
                    from PyQt5.QtWidgets import QGraphicsRectItem
                    rect_phase = QGraphicsRectItem(x - dx/2, y - dy/2, dx, dy)
                    self.phase_plot.addItem(rect_phase)
                    self.phase_rect_items[key] = rect_phase
                else:
                    rect_phase.setRect(x - dx/2, y - dy/2, dx, dy)
                
                # Нормализуем значение фазы и получаем цвет
                phase_norm = (phase_val - phase_min) / (phase_max - phase_min) if phase_max != phase_min else 0.5
                phase_color = phase_cmap.map(phase_norm, mode='qcolor')
                rect_phase.setBrush(pg.mkBrush(phase_color))
                rect_phase.setPen(pg.mkPen(None))
                
                # Периодически обновляем UI для больших объемов данных
                point_count += 1
                if point_count % update_interval == 0:
                    QtWidgets.QApplication.processEvents()
    
    # ========== Навигация между лучами и частотами ==========
    
    def prev_beam(self):
        """Переключиться на предыдущий луч"""
        current_index = self.view_beam_combo.currentIndex()
        if current_index > 0:
            self.view_beam_combo.setCurrentIndex(current_index - 1)
    
    def next_beam(self):
        """Переключиться на следующий луч"""
        current_index = self.view_beam_combo.currentIndex()
        if current_index < self.view_beam_combo.count() - 1:
            self.view_beam_combo.setCurrentIndex(current_index + 1)
    
    def prev_freq(self):
        """Переключиться на предыдущую частоту"""
        current_index = self.view_freq_combo.currentIndex()
        if current_index > 0:
            self.view_freq_combo.setCurrentIndex(current_index - 1)
    
    def next_freq(self):
        """Переключиться на следующую частоту"""
        current_index = self.view_freq_combo.currentIndex()
        if current_index < self.view_freq_combo.count() - 1:
            self.view_freq_combo.setCurrentIndex(current_index + 1)
    
    def update_nav_buttons(self):
        """Обновление состояния кнопок навигации"""
        # Лучи
        beam_index = self.view_beam_combo.currentIndex()
        beam_count = self.view_beam_combo.count()
        self.prev_beam_btn.setEnabled(beam_index > 0)
        self.next_beam_btn.setEnabled(beam_index < beam_count - 1)
        
        # Частоты
        freq_index = self.view_freq_combo.currentIndex()
        freq_count = self.view_freq_combo.count()
        self.prev_freq_btn.setEnabled(freq_index > 0)
        self.next_freq_btn.setEnabled(freq_index < freq_count - 1)
    
    # ========== Сохранение/загрузка настроек UI ==========
    
    def save_ui_settings(self):
        """Сохраняет состояние контролов UI в QSettings (как в phase_afar_widget)"""
        s = self._ui_settings
        # PNA
        s.setValue('s_param', self.s_param_combo.currentText())
        s.setValue('pna_power', float(self.pna_power.value()))
        s.setValue('pna_start_freq', int(self.pna_start_freq.value()))
        s.setValue('pna_stop_freq', int(self.pna_stop_freq.value()))
        s.setValue('pna_points', self.pna_number_of_points.currentText())
        s.setValue('pna_settings_file', self.settings_file_edit.text())
        s.setValue('pulse_mode', self.pulse_mode_combo.currentText())
        s.setValue('pulse_width', float(self.pulse_width.value()))
        s.setValue('pulse_period', float(self.pulse_period.value()))
        # Синхронизатор (E5818)
        s.setValue('trig_ttl_channel', self.trig_ttl_channel.currentText())
        s.setValue('trig_ext_channel', self.trig_ext_channel.currentText())
        s.setValue('trig_start_lead', float(self.trig_start_lead.value()))
        s.setValue('trig_pulse_period', float(self.trig_pulse_period.value()))
        s.setValue('trig_min_alarm_guard', float(self.trig_min_alarm_guard.value()))
        s.setValue('trig_ext_debounce', float(self.trig_ext_debounce.value()))
        # Параметры планарного сканирования
        s.setValue('left_x', float(self.left_x.value()))
        s.setValue('right_x', float(self.right_x.value()))
        s.setValue('up_y', float(self.up_y.value()))
        s.setValue('down_y', float(self.down_y.value()))
        s.setValue('step_x', float(self.step_x.value()))
        s.setValue('step_y', float(self.step_y.value()))
        # Система координат
        s.setValue('coord_system', self.coord_system_combo.currentText())
        # Log level
        s.setValue('log_level', self.log_level_combo.currentText())
        s.sync()
    
    def load_ui_settings(self):
        """Восстанавливает состояние контролов UI из QSettings (как в phase_afar_widget)"""
        s = self._ui_settings
        # PNA
        if (v := s.value('s_param')):
            idx = self.s_param_combo.findText(v)
            if idx >= 0:
                self.s_param_combo.setCurrentIndex(idx)
        if (v := s.value('pulse_mode')):
            idx = self.pulse_mode_combo.findText(v)
            if idx >= 0:
                self.pulse_mode_combo.setCurrentIndex(idx)
        for key, widget in [
            ('pna_power', self.pna_power),
            ('pna_start_freq', self.pna_start_freq),
            ('pna_stop_freq', self.pna_stop_freq),
            ('pulse_width', self.pulse_width),
            ('pulse_period', self.pulse_period)
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
        # Синхронизатор (E5818)
        if (v := s.value('trig_ttl_channel')):
            idx = self.trig_ttl_channel.findText(v)
            if idx >= 0: self.trig_ttl_channel.setCurrentIndex(idx)
        if (v := s.value('trig_ext_channel')):
            idx = self.trig_ext_channel.findText(v)
            if idx >= 0: self.trig_ext_channel.setCurrentIndex(idx)
        for key, widget in [
            ('trig_start_lead', self.trig_start_lead),
            ('trig_pulse_period', self.trig_pulse_period),
            ('trig_min_alarm_guard', self.trig_min_alarm_guard),
            ('trig_ext_debounce', self.trig_ext_debounce)
        ]:
            val = s.value(key)
            if val is not None:
                try:
                    if hasattr(widget, 'setValue'):
                        widget.setValue(float(val))
                except Exception:
                    pass
        # Параметры планарного сканирования
        for key, widget in [
            ('left_x', self.left_x),
            ('right_x', self.right_x),
            ('up_y', self.up_y),
            ('down_y', self.down_y),
            ('step_x', self.step_x),
            ('step_y', self.step_y)
        ]:
            val = s.value(key)
            if val is not None:
                try:
                    widget.setValue(float(val))
                except Exception:
                    pass
        # Система координат
        if (v := s.value('coord_system')):
            idx = self.coord_system_combo.findText(v)
            if idx >= 0:
                self.coord_system_combo.setCurrentIndex(idx)
        # Инициализируем состояние кнопок системы координат
        self.update_coord_buttons_state()
        # Log level
        if (v := s.value('log_level')):
            idx = self.log_level_combo.findText(v)
            if idx >= 0:
                self.log_level_combo.setCurrentIndex(idx)

