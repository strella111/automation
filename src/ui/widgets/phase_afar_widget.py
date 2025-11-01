from PyQt5 import QtWidgets, QtCore
from PyQt5.QtWidgets import QMessageBox, QStyle
from PyQt5.QtCore import QSize
from loguru import logger
import os
import threading
import numpy as np
import pyqtgraph as pg
from core.measurements.phase_afar.phase_afar import PhaseAfar
from core.common.enums import Channel, Direction
from core.common.coordinate_system import CoordinateSystemManager
from pyqtgraph.colormap import ColorMap
from utils.excel_module import CalibrationCSV
from config.settings_manager import get_ui_settings

from ui.dialogs.pna_file_dialog import PnaFileDialog
from ui.widgets.base_measurement_widget import BaseMeasurementWidget
from ui.dialogs.add_coord_syst_dialog import AddCoordinateSystemDialog


class PhaseAfarWidget(BaseMeasurementWidget):
    update_gui_signal = QtCore.pyqtSignal(int, int, float, float, int)  # i, j, x, y, bu_number
    norm_amplitude_signal = QtCore.pyqtSignal(float)  # Сигнал для передачи амплитуды нормировки
    
    def __init__(self):
        super().__init__()

        self.update_gui_signal.connect(self.on_measurement_update)
        self.norm_amplitude_signal.connect(self.on_norm_amplitude_received)
        self.coord_system_manager = CoordinateSystemManager("config/coordinate_systems.json")
        self.coord_system = None

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
        pna_layout.addWidget(self.pna_connect_btn)
        self.connect_layout.addWidget(pna_widget)

        psn_widget = QtWidgets.QWidget()
        psn_layout = QtWidgets.QHBoxLayout(psn_widget)
        psn_layout.setContentsMargins(0, 0, 0, 0)
        self.psn_connect_btn = QtWidgets.QPushButton('Сканер')
        self.psn_connect_btn.setMinimumHeight(40)
        psn_layout.addWidget(self.psn_connect_btn)
        self.connect_layout.addWidget(psn_widget)

        afar_widget = QtWidgets.QWidget()
        afar_layout = QtWidgets.QHBoxLayout(afar_widget)
        afar_layout.setContentsMargins(0, 0, 0, 0)
        self.afar_connect_btn = QtWidgets.QPushButton('АФАР')
        self.afar_connect_btn.setMinimumHeight(40)
        afar_layout.addWidget(self.afar_connect_btn)
        self.connect_layout.addWidget(afar_widget)

        self.left_layout.addWidget(self.connect_group)

        # Настройки измерений
        self.param_tabs = QtWidgets.QTabWidget()
        self.ma_tab = QtWidgets.QWidget()
        self.ma_tab_layout = QtWidgets.QFormLayout(self.ma_tab)

        self.channel_combo = QtWidgets.QComboBox()
        self.channel_combo.addItems(['Приемник', 'Передатчик'])
        self.ma_tab_layout.addRow('Канал:', self.channel_combo)

        self.direction_combo = QtWidgets.QComboBox()
        self.direction_combo.addItems(['Горизонтальная', 'Вертикальная'])
        self.ma_tab_layout.addRow('Поляризация:', self.direction_combo)
        
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

        self.pulse_mode_combo = QtWidgets.QComboBox()
        self.pulse_mode_combo.addItems(['Standard', 'Off'])
        self.pna_tab_layout.addRow('Импульсный режим', self.pulse_mode_combo)

        self.pulse_width = QtWidgets.QDoubleSpinBox()
        self.pulse_width.setDecimals(3)
        self.pulse_width.setRange(5, 50)
        self.pulse_width.setSingleStep(1)
        self.pulse_width.setValue(20)
        self.pulse_width.setSuffix(' мкс')
        self.pna_tab_layout.addRow('Ширина импульса', self.pulse_width)

        self.pulse_period = QtWidgets.QDoubleSpinBox()
        self.pulse_period.setDecimals(3)
        self.pulse_period.setRange(20, 20000)
        self.pulse_period.setValue(2000)
        self.pulse_period.setSingleStep(10)
        self.pulse_period.setSuffix(' мкс')
        self.pna_tab_layout.addRow('Период импульса', self.pulse_period)

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

        # Группа выбора БУ для фазировки
        bu_selection_group = QtWidgets.QGroupBox('Выбор БУ для фазировки')
        bu_selection_layout = QtWidgets.QVBoxLayout(bu_selection_group)
        bu_selection_layout.setContentsMargins(15, 15, 15, 15)

        # Радиокнопки для выбора режима
        self.bu_selection_mode = QtWidgets.QButtonGroup()
        
        self.all_bu_radio = QtWidgets.QRadioButton('Все БУ (1-40)')
        self.all_bu_radio.setChecked(True)
        self.bu_selection_mode.addButton(self.all_bu_radio, 0)
        bu_selection_layout.addWidget(self.all_bu_radio)

        self.range_bu_radio = QtWidgets.QRadioButton('Диапазон БУ')
        self.bu_selection_mode.addButton(self.range_bu_radio, 1)
        bu_selection_layout.addWidget(self.range_bu_radio)

        # Настройки диапазона
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

        # Настройки секций
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

        # Список выбора БУ
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

        # Кнопки для быстрого выбора
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

        # Подключение сигналов для изменения режима
        self.bu_selection_mode.buttonClicked.connect(self.on_bu_selection_mode_changed)
        self.bu_start_spin.valueChanged.connect(self.on_range_changed)
        self.bu_end_spin.valueChanged.connect(self.on_range_changed)

        self.meas_tab_layout.addWidget(bu_selection_group)

        # Группа настроек нормировки
        normalization_group = QtWidgets.QGroupBox('Нормировка')
        normalization_layout = QtWidgets.QVBoxLayout(normalization_group)
        normalization_layout.setContentsMargins(15, 15, 15, 15)
        
        norm_bu_layout = QtWidgets.QHBoxLayout()
        norm_bu_layout.addWidget(QtWidgets.QLabel('БУ нормировки:'))
        self.norm_bu_spin = QtWidgets.QSpinBox()
        self.norm_bu_spin.setRange(1, 40)
        self.norm_bu_spin.setValue(1)
        norm_bu_layout.addWidget(self.norm_bu_spin)
        normalization_layout.addLayout(norm_bu_layout)
        
        norm_ppm_layout = QtWidgets.QHBoxLayout()
        norm_ppm_layout.addWidget(QtWidgets.QLabel('ППМ нормировки:'))
        self.norm_ppm_spin = QtWidgets.QSpinBox()
        self.norm_ppm_spin.setRange(1, 32)
        self.norm_ppm_spin.setValue(12)
        norm_ppm_layout.addWidget(self.norm_ppm_spin)
        normalization_layout.addLayout(norm_ppm_layout)
        
        self.meas_tab_layout.addWidget(normalization_group)
        
        # Группа управления ВИПами и ЛЗ
        vip_control_group = QtWidgets.QGroupBox('Дополнительные настройки')
        vip_control_layout = QtWidgets.QVBoxLayout(vip_control_group)
        vip_control_layout.setContentsMargins(15, 15, 15, 15)
        
        self.turn_off_vips_checkbox = QtWidgets.QCheckBox('Выключать ВИПы в конце измерения')
        self.turn_off_vips_checkbox.setChecked(True)
        vip_control_layout.addWidget(self.turn_off_vips_checkbox)
        
        self.enable_delay_line_calibration_checkbox = QtWidgets.QCheckBox('Фазировать линии задержки')
        self.enable_delay_line_calibration_checkbox.setChecked(False)
        vip_control_layout.addWidget(self.enable_delay_line_calibration_checkbox)
        
        self.meas_tab_layout.addWidget(vip_control_group)
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

        self.plot_tabs = QtWidgets.QTabWidget()

        # Амплитуда: график + интерактивная легенда справа
        self.amp_plot = pg.PlotWidget(title="Амплитуда (2D)")
        self.amp_plot.setBackground('w')
        self.amp_plot.showGrid(x=True, y=True, alpha=0.3)
        # Прямоугольники амплитуды
        self.amp_rect_items = {}

        # Фаза: график + интерактивная легенда справа
        self.phase_plot = pg.PlotWidget(title="Фаза (2D)")
        self.phase_plot.setBackground('w')
        self.phase_plot.showGrid(x=True, y=True, alpha=0.3)
        # Прямоугольники фазы
        self.phase_rect_items = {}

        self._amp_cmap = ColorMap(pos=[0.0, 1.0], color=[(255, 0, 0), (0, 255, 0)])
        self._phase_cmap = ColorMap(
            pos=[0.0, 0.2, 0.4, 0.6, 0.8, 1.0],
            color=[(0, 0, 255), (0, 255, 255), (0, 255, 0), (255, 255, 0), (255, 165, 0), (255, 0, 0)]
        )
        self._amp_levels = (-10.0, 5.0)
        self._phase_levels = (-180.0, 180.0)
        self._rect_dx_default = 28.0
        self._rect_dy_default = 2.2
        
        self.amp_img_item = pg.ImageItem()
        self.amp_img_item.setVisible(False)
        self.amp_plot.addItem(self.amp_img_item)
        
        self.phase_img_item = pg.ImageItem()
        self.phase_img_item.setVisible(False)
        self.phase_plot.addItem(self.phase_img_item)
        
        self.amp_cbar = pg.ColorBarItem(values=self._amp_levels, colorMap=self._amp_cmap, orientation='v', width=14)
        self.amp_cbar.setImageItem(self.amp_img_item, insert_in=self.amp_plot.getPlotItem())
        
        self.phase_cbar = pg.ColorBarItem(values=self._phase_levels, colorMap=self._phase_cmap, orientation='v', width=14)
        self.phase_cbar.setImageItem(self.phase_img_item, insert_in=self.phase_plot.getPlotItem())

        self.amp_hover_label = pg.TextItem(
            color=(255, 255, 255), 
            anchor=(0, 1),
            fill=pg.mkBrush(0, 0, 0, 180),
            border=pg.mkPen(255, 255, 255, width=2)
        )
        self.amp_hover_label.setZValue(100)  # Поверх всех элементов
        self.phase_hover_label = pg.TextItem(
            color=(255, 255, 255), 
            anchor=(0, 1),
            fill=pg.mkBrush(0, 0, 0, 180),
            border=pg.mkPen(255, 255, 255, width=2)
        )
        self.phase_hover_label.setZValue(100)  # Поверх всех элементов
        self.amp_plot.addItem(self.amp_hover_label)
        self.phase_plot.addItem(self.phase_hover_label)
        self.amp_hover_label.hide()
        self.phase_hover_label.hide()
        try:
            self.amp_plot.scene().sigMouseMoved.disconnect(self._on_mouse_moved_amp)
        except Exception:
            pass
        try:
            self.phase_plot.scene().sigMouseMoved.disconnect(self._on_mouse_moved_phase)
        except Exception:
            pass
        self.amp_plot.scene().sigMouseMoved.connect(self._on_mouse_moved_amp)
        self.phase_plot.scene().sigMouseMoved.connect(self._on_mouse_moved_phase)
        
        # Подключаем обработчик двойного клика
        self.amp_plot.scene().sigMouseClicked.connect(self._on_amp_plot_clicked)
        self.phase_plot.scene().sigMouseClicked.connect(self._on_phase_plot_clicked)
        
        self.plot_tabs.addTab(self.amp_plot, "Амплитуда")
        self.plot_tabs.addTab(self.phase_plot, "Фаза")
        
        # Чекбокс нормировки амплитуды над графиками
        normalize_widget = QtWidgets.QWidget()
        normalize_layout = QtWidgets.QHBoxLayout(normalize_widget)
        normalize_layout.setContentsMargins(5, 2, 5, 2)
        normalize_layout.setSpacing(5)
        self.normalize_amplitude_checkbox = QtWidgets.QCheckBox('Нормировать амплитуду')
        self.normalize_amplitude_checkbox.setChecked(False)
        self.normalize_amplitude_checkbox.setToolTip('При включении: амплитуда = амплитуда текущего ППМ - амплитуда нормировочного ППМ')
        self.normalize_amplitude_checkbox.stateChanged.connect(self.on_normalize_amplitude_changed)
        normalize_layout.addWidget(self.normalize_amplitude_checkbox)
        normalize_layout.addStretch()
        
        self.right_layout.addWidget(normalize_widget)
        self.right_layout.addWidget(self.plot_tabs, stretch=5)

        # Создаем консоль с выбором уровня логов
        self.console, self.log_handler, self.log_level_combo = self.create_console_with_log_level(self.right_layout, console_height=180)
        logger.add(self.log_handler, format="{time:HH:mm:ss.SSS} | {level} | {name}:{function}:{line} | {message}")

        self._meas_thread = None
        
        # Данные для всех ППМ из всех МА
        self.all_amp_data = {}  # Словарь: (bu_num, ppm_num) -> amp_value (отображаемая)
        self.all_amp_data_raw = {}  # Словарь: (bu_num, ppm_num) -> amp_value (исходная с анализатора)
        self.all_phase_data = {}  # Словарь: (bu_num, ppm_num) -> phase_value
        self.all_coordinates = {}  # Словарь: (bu_num, ppm_num) -> (x, y)
        self.norm_amplitude_value = None  # Амплитуда нормировочного ППМ
        
        # Фиксированные размеры прямоугольников (вычисляются один раз)
        self._fixed_dx = None
        self._fixed_dy = None
        # Текущие размеры для hover
        self._dx = self._rect_dx_default
        self._dy = self._rect_dy_default
        # Фиксированные диапазоны для отображения (чтобы не прыгал масштаб)
        self._view_range_set = False
        
        # Координаты для одного МА (4x8)
        self.x_cords = [42, 14, -14, -42]
        self.y_cords = [-7.7, -5.5, -3.3, -1.1, 1.1, 3.3, 5.5, 7.7]
        
        # Текущий БУ для отображения
        self.current_bu = 1
        self.bu_progress = {}
        
        # Для выделения прямоугольника при наведении
        self._highlighted_amp_rect = None
        self._highlighted_phase_rect = None
        
        # Для выделения всех ППМ одного БУ
        self._selected_bu_rects_amp = []
        self._selected_bu_rects_phase = []
        self._selected_bu_number = None

        # Подключение сигналов
        self.pna_connect_btn.clicked.connect(self.connect_pna)
        self.psn_connect_btn.clicked.connect(self.connect_psn)
        self.afar_connect_btn.clicked.connect(self.connect_afar)
        self.apply_btn.clicked.connect(self.apply_params)
        self.start_btn.clicked.connect(self.start_phase_meas)
        self.stop_btn.clicked.connect(self.stop_phase_meas)
        self.pause_btn.clicked.connect(self.pause_phase_meas)
        
        # Подключаем обработчики изменения ColorBar
        try:
            self.amp_cbar.sigLevelsChangeFinished.connect(self._on_colorbar_changed)
            self.phase_cbar.sigLevelsChangeFinished.connect(self._on_colorbar_changed)
        except AttributeError:
            self.amp_cbar.sigLevelsChanged.connect(self._on_colorbar_changed)
            self.phase_cbar.sigLevelsChanged.connect(self._on_colorbar_changed)

        self.set_buttons_enabled(True)
        self.pna_settings = {}

        self.update_coord_buttons_state()

        self.set_button_connection_state(self.pna_connect_btn, False)
        self.set_button_connection_state(self.psn_connect_btn, False)
        self.set_button_connection_state(self.afar_connect_btn, False)

        # Персистентные настройки UI
        self._ui_settings = get_ui_settings('phase_afar')
        self.load_ui_settings()
        
        # Подключаем автосохранение уровня логирования
        self.log_level_combo.currentTextChanged.connect(lambda: self._ui_settings.setValue('log_level', self.log_level_combo.currentText()))

    def set_buttons_enabled(self, enabled: bool):
        self.afar_connect_btn.setEnabled(enabled)
        self.pna_connect_btn.setEnabled(enabled)
        self.psn_connect_btn.setEnabled(enabled)
        self.apply_btn.setEnabled(enabled)
        self.start_btn.setEnabled(enabled)
        self.stop_btn.setEnabled(not enabled)

    def apply_params(self):
        """Сохраняет параметры из вкладок"""
        # MA
        self.channel = self.channel_combo.currentText()
        self.direction = self.direction_combo.currentText()
        # PNA
        self.pna_settings['s_param'] = self.s_param_combo.currentText()
        self.pna_settings['power'] = self.pna_power.value()
        self.pna_settings['freq_start'] = self.pna_start_freq.value() * 10**6
        self.pna_settings['freq_stop'] = self.pna_stop_freq.value() * 10**6
        self.pna_settings['freq_points'] = self.pna_number_of_points.currentText()
        self.pna_settings['settings_file'] = self.settings_file_edit.text()
        self.pna_settings['pulse_mode'] = self.pulse_mode_combo.currentText()
        self.pna_settings['pulse_period'] = self.pulse_period.value() / 10 ** 6
        self.pna_settings['pulse_width'] = self.pulse_width.value() / 10 ** 6

        coord_system_name = self.coord_system_combo.currentText()
        self.coord_system = self.coord_system_manager.get_system_by_name(coord_system_name)
        logger.info('Параметры успешно применены')
        # Сохраняем значения UI
        try:
            self.save_ui_settings()
        except Exception:
            pass

    def start_phase_meas(self):
        if not (self.afar and self.pna and self.psn):
            logger.error('Сначала подключите все устройства!')
            return

        self.set_buttons_enabled(False)
        self._stop_flag.clear()
        # Очищаем данные всех ППМ
        self.all_amp_data.clear()
        self.all_amp_data_raw.clear()
        self.all_phase_data.clear()
        self.all_coordinates.clear()
        self.bu_progress = {}
        self.norm_amplitude_value = None
        # Сбрасываем фиксированные размеры
        self._fixed_dx = None
        self._fixed_dy = None
        self._view_range_set = False

        self.amp_plot.clear()
        self.phase_plot.clear()
        self.amp_rect_items.clear()
        self.phase_rect_items.clear()
        
        # Сбрасываем выделение БУ
        self._selected_bu_rects_amp.clear()
        self._selected_bu_rects_phase.clear()
        self._selected_bu_number = None
        
        self.amp_plot.addItem(self.amp_img_item)
        self.phase_plot.addItem(self.phase_img_item)

        self.amp_plot.addItem(self.amp_hover_label)
        self.phase_plot.addItem(self.phase_hover_label)
        self.apply_params()
        self._meas_thread = threading.Thread(target=self._run_phase_afar_real, daemon=True)
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

    def _run_phase_afar_real(self):
        logger.info('Начало выполнения процесса фазировки АФАР (40 МА)')
        try:
            # Настройка сканера
            self.setup_scanner_common()

            # Настройка PNA
            self.setup_pna_common()
            
            chanel = Channel.Receiver if self.channel_combo.currentText() == 'Приемник' else Channel.Transmitter
            direction = Direction.Horizontal if self.direction_combo.currentText() == 'Горизонтальная' else Direction.Vertical
            logger.info(f'Используем канал: {chanel.value}, поляризация: {direction.value}')
            
            def point_callback(i, j, x, y, amp, phase, bu_number):
                # Вычисляем номер ППМ
                ppm_num = i * 8 + j + 1
                
                # Сохраняем исходную амплитуду с анализатора
                self.all_amp_data_raw[(bu_number, ppm_num)] = amp
                self.all_phase_data[(bu_number, ppm_num)] = phase
                self.all_coordinates[(bu_number, ppm_num)] = (x, y)
                
                # Вычисляем отображаемую амплитуду (с учетом текущего состояния чекбокса)
                if self.normalize_amplitude_checkbox.isChecked() and self.norm_amplitude_value is not None:
                    amp_display = amp - self.norm_amplitude_value
                else:
                    amp_display = amp
                self.all_amp_data[(bu_number, ppm_num)] = amp_display
                
                # Логируем для отладки
                logger.debug(f"ППМ БУ №{bu_number}, ППМ №{ppm_num}: координаты ({x:.2f}, {y:.2f}), амплитуда {amp:.2f}, фаза {phase:.2f}")
                
                self.update_gui_signal.emit(i, j, x, y, bu_number)
            
            def norm_callback(norm_amp):
                # Callback для получения амплитуды нормировки из потока измерения
                self.norm_amplitude_signal.emit(norm_amp)
            
            phase_afar = PhaseAfar(
                afar=self.afar,
                psn=self.psn,
                pna=self.pna,
                point_callback=point_callback,
                norm_callback=norm_callback
            )
            
            # Устанавливаем параметры нормировки из интерфейса
            phase_afar.ppm_norm_number = self.norm_ppm_spin.value()
            phase_afar.bu_norm_number = self.norm_bu_spin.value()
            phase_afar.turn_off_vips = self.turn_off_vips_checkbox.isChecked()
            phase_afar.enable_delay_line_calibration = self.enable_delay_line_calibration_checkbox.isChecked()
            logger.info(f'Параметры нормировки: БУ={phase_afar.bu_norm_number}, ППМ={phase_afar.ppm_norm_number}')
            logger.info(f'Выключение ВИПов в конце: {phase_afar.turn_off_vips}')
            logger.info(f'Фазировка линий задержки: {phase_afar.enable_delay_line_calibration}')
            phase_afar.set_pause_flag(self._pause_flag)
            phase_afar.stop_flag = self._stop_flag
            
            # Получаем список выбранных БУ
            selected_bu_numbers = self.get_selected_bu_numbers()
            if not selected_bu_numbers:
                self.show_error_message("Ошибка", "Не выбрано ни одного БУ для фазировки")
                return
            
            logger.info(f'Выбрано БУ для фазировки: {selected_bu_numbers}')
            
            # Запускаем фазировку выбранных БУ
            phase_afar.start(chanel=chanel, direction=direction, selected_bu_numbers=selected_bu_numbers)
            
            logger.info('Фазировка завершена')
        except Exception as e:
            logger.error(f'Ошибка фазировки: {e}')
        finally:
            self.set_buttons_enabled(True)


    def _on_mouse_moved_amp(self, pos):
        self._handle_mouse_move(pos, self.amp_plot, self.amp_hover_label, 'amp')

    def _on_mouse_moved_phase(self, pos):
        self._handle_mouse_move(pos, self.phase_plot, self.phase_hover_label, 'phase')

    def _handle_mouse_move(self, pos, plot_widget: pg.PlotWidget, label: pg.TextItem, data_type: str):
        try:
            if not hasattr(self, '_dx') or not hasattr(self, '_dy') or not self.all_coordinates:
                label.hide()
                self._clear_highlight(data_type)
                return
            vb = plot_widget.getViewBox()
            if vb is None:
                label.hide()
                self._clear_highlight(data_type)
                return
            point = vb.mapSceneToView(pos)
            x, y = float(point.x()), float(point.y())
            
            closest_ppm = None
            closest_value = float('nan')
            cx, cy = None, None
            for (bu_num, ppm_num), (ppm_x, ppm_y) in self.all_coordinates.items():
                if abs(ppm_x - x) <= self._dx/2 and abs(ppm_y - y) <= self._dy/2:
                    closest_ppm = (bu_num, ppm_num)
                    cx, cy = ppm_x, ppm_y
                    if data_type == 'amp' and (bu_num, ppm_num) in self.all_amp_data:
                        closest_value = self.all_amp_data[(bu_num, ppm_num)]
                    elif data_type == 'phase' and (bu_num, ppm_num) in self.all_phase_data:
                        closest_value = self.all_phase_data[(bu_num, ppm_num)]
                    break

            if closest_ppm and np.isfinite(closest_value) and cx is not None:
                bu_num, ppm_num = closest_ppm
                label.setText(f"МА №{bu_num}\nППМ №{ppm_num}\nЗначение: {closest_value:.2f}")
                label.setPos(cx, cy)
                label.show()
                self._highlight_rect(closest_ppm, data_type)
            else:
                label.hide()
                self._clear_highlight(data_type)
        except Exception:
            label.hide()
            self._clear_highlight(data_type)
    
    def _highlight_rect(self, ppm_key, data_type):
        """Выделяет прямоугольник при наведении"""
        if data_type == 'amp':
            if self._highlighted_amp_rect:
                self._highlighted_amp_rect.setPen(pg.mkPen(None))
            rect = self.amp_rect_items.get(ppm_key)
            if rect:
                rect.setPen(pg.mkPen(color='black', width=3))
                self._highlighted_amp_rect = rect
        else:
            if self._highlighted_phase_rect:
                self._highlighted_phase_rect.setPen(pg.mkPen(None))
            rect = self.phase_rect_items.get(ppm_key)
            if rect:
                rect.setPen(pg.mkPen(color='black', width=3))
                self._highlighted_phase_rect = rect
    
    def _clear_highlight(self, data_type):
        """Снимает выделение прямоугольника"""
        if data_type == 'amp':
            if self._highlighted_amp_rect:
                self._highlighted_amp_rect.setPen(pg.mkPen(None))
                self._highlighted_amp_rect = None
        else:
            if self._highlighted_phase_rect:
                self._highlighted_phase_rect.setPen(pg.mkPen(None))
                self._highlighted_phase_rect = None
    
    def _on_amp_plot_clicked(self, event):
        """Обработчик клика на графике амплитуды"""
        if event.double():
            self._handle_double_click(event, self.amp_plot, 'amp')
    
    def _on_phase_plot_clicked(self, event):
        """Обработчик клика на графике фазы"""
        if event.double():
            self._handle_double_click(event, self.phase_plot, 'phase')
    
    def _handle_double_click(self, event, plot_widget, data_type):
        """Обработка двойного клика по прямоугольнику"""
        try:
            if not hasattr(self, '_dx') or not hasattr(self, '_dy') or not self.all_coordinates:
                return
            
            vb = plot_widget.getViewBox()
            if vb is None:
                return
            
            pos = event.scenePos()
            point = vb.mapSceneToView(pos)
            x, y = float(point.x()), float(point.y())
            
            # Находим кликнутый прямоугольник
            clicked_ppm = None
            for (bu_num, ppm_num), (ppm_x, ppm_y) in self.all_coordinates.items():
                if abs(ppm_x - x) <= self._dx/2 and abs(ppm_y - y) <= self._dy/2:
                    clicked_ppm = (bu_num, ppm_num)
                    break
            
            if clicked_ppm:
                bu_num, ppm_num = clicked_ppm
                # Выделяем все ППМ этого БУ
                self._select_bu_modules(bu_num)
                # Открываем детальное окно
                self._open_detail_window(bu_num, ppm_num)
                # Снимаем выделение после закрытия окна
                self._clear_bu_selection()
        except Exception as e:
            logger.error(f"Ошибка при обработке двойного клика: {e}")
    
    def _select_bu_modules(self, bu_number):
        """Выделяет все ППМ указанного БУ"""
        # Снимаем предыдущее выделение
        for rect in self._selected_bu_rects_amp:
            rect.setPen(pg.mkPen(None))
        for rect in self._selected_bu_rects_phase:
            rect.setPen(pg.mkPen(None))
        
        self._selected_bu_rects_amp.clear()
        self._selected_bu_rects_phase.clear()
        self._selected_bu_number = bu_number
        
        # Выделяем все ППМ этого БУ
        for (bu_num, ppm_num) in self.all_coordinates.keys():
            if bu_num == bu_number:
                # Амплитуда
                rect_amp = self.amp_rect_items.get((bu_num, ppm_num))
                if rect_amp:
                    rect_amp.setPen(pg.mkPen(color='blue', width=2))
                    self._selected_bu_rects_amp.append(rect_amp)
                
                # Фаза
                rect_phase = self.phase_rect_items.get((bu_num, ppm_num))
                if rect_phase:
                    rect_phase.setPen(pg.mkPen(color='blue', width=2))
                    self._selected_bu_rects_phase.append(rect_phase)
        
        logger.info(f"Выделены все ППМ для БУ №{bu_number}")
    
    def _clear_bu_selection(self):
        """Снимает выделение со всех ППМ БУ"""
        for rect in self._selected_bu_rects_amp:
            rect.setPen(pg.mkPen(None))
        for rect in self._selected_bu_rects_phase:
            rect.setPen(pg.mkPen(None))
        
        self._selected_bu_rects_amp.clear()
        self._selected_bu_rects_phase.clear()
        self._selected_bu_number = None
        logger.info("Выделение БУ снято")
    
    def _open_detail_window(self, bu_number, ppm_number):
        """Открывает детальное окно с графиками для ППМ"""
        try:
            # Собираем данные для этого ППМ
            amp_value = self.all_amp_data.get((bu_number, ppm_number))
            phase_value = self.all_phase_data.get((bu_number, ppm_number))
            coords = self.all_coordinates.get((bu_number, ppm_number))
            
            if amp_value is None or phase_value is None:
                logger.warning(f"Нет данных для БУ №{bu_number}, ППМ №{ppm_number}")
                return
            
            # Создаем диалоговое окно
            from PyQt5.QtWidgets import QDialog, QVBoxLayout, QLabel, QHBoxLayout
            
            dialog = QDialog(self)
            dialog.setWindowTitle(f"Детали: БУ №{bu_number}, ППМ №{ppm_number}")
            dialog.setMinimumSize(600, 400)
            
            layout = QVBoxLayout(dialog)
            
            # Информация
            info_layout = QHBoxLayout()
            info_text = f"""
            <h3>БУ №{bu_number}, ППМ №{ppm_number}</h3>
            <p><b>Координаты:</b> ({coords[0]:.2f}, {coords[1]:.2f})</p>
            <p><b>Амплитуда:</b> {amp_value:.2f} дБ</p>
            <p><b>Фаза:</b> {phase_value:.2f}°</p>
            """
            info_label = QLabel(info_text)
            info_layout.addWidget(info_label)
            layout.addLayout(info_layout)
            
            # График амплитуд всех ППМ этого БУ
            amp_plot = pg.PlotWidget(title=f"Амплитуды всех ППМ в БУ №{bu_number}")
            amp_plot.setBackground('w')
            amp_plot.showGrid(x=True, y=True)
            amp_plot.setLabel('left', 'Амплитуда', units='дБ')
            amp_plot.setLabel('bottom', 'Номер ППМ')
            
            # Данные для графика
            ppm_numbers = []
            amp_values = []
            for i in range(1, 33):  # 4x8 = 32 ППМ в БУ
                if (bu_number, i) in self.all_amp_data:
                    ppm_numbers.append(i)
                    amp_values.append(self.all_amp_data[(bu_number, i)])
            
            if ppm_numbers:
                # Рисуем график
                amp_plot.plot(ppm_numbers, amp_values, pen=pg.mkPen(color='b', width=2), 
                             symbol='o', symbolBrush='b', symbolSize=8)
                # Выделяем текущий ППМ
                if ppm_number in ppm_numbers:
                    idx = ppm_numbers.index(ppm_number)
                    amp_plot.plot([ppm_number], [amp_values[idx]], 
                                 pen=None, symbol='o', symbolBrush='r', symbolSize=12)
            
            layout.addWidget(amp_plot)
            
            # График фаз всех ППМ этого БУ
            phase_plot = pg.PlotWidget(title=f"Фазы всех ППМ в БУ №{bu_number}")
            phase_plot.setBackground('w')
            phase_plot.showGrid(x=True, y=True)
            phase_plot.setLabel('left', 'Фаза', units='°')
            phase_plot.setLabel('bottom', 'Номер ППМ')
            
            ppm_numbers_phase = []
            phase_values = []
            for i in range(1, 33):
                if (bu_number, i) in self.all_phase_data:
                    ppm_numbers_phase.append(i)
                    phase_values.append(self.all_phase_data[(bu_number, i)])
            
            if ppm_numbers_phase:
                phase_plot.plot(ppm_numbers_phase, phase_values, pen=pg.mkPen(color='g', width=2),
                               symbol='o', symbolBrush='g', symbolSize=8)
                if ppm_number in ppm_numbers_phase:
                    idx = ppm_numbers_phase.index(ppm_number)
                    phase_plot.plot([ppm_number], [phase_values[idx]],
                                   pen=None, symbol='o', symbolBrush='r', symbolSize=12)
            
            layout.addWidget(phase_plot)
            
            dialog.exec_()
            
        except Exception as e:
            logger.error(f"Ошибка при открытии детального окна: {e}")

    @QtCore.pyqtSlot(float)
    def on_norm_amplitude_received(self, norm_amp):
        """Слот для получения амплитуды нормировки из потока измерения"""
        self.norm_amplitude_value = norm_amp
        logger.info(f'Получена амплитуда нормировки: {norm_amp:.2f} дБ - нормировка доступна во время измерения')
    
    @QtCore.pyqtSlot(int, int, float, float, int)
    def on_measurement_update(self, i, j, x, y, bu_number):
        """Слот для обновления графика при получении новых данных"""
        # Данные уже сохранены в point_callback
        self.update_heatmaps()
    
    def stop_phase_meas(self):
        logger.info('Остановка фазировки...')
        self._stop_flag.set()
        if self._meas_thread and self._meas_thread.is_alive():
            self._meas_thread.join(timeout=2)
        self.set_buttons_enabled(True)

    def set_device_settings(self, settings: dict):
        """Сохраняет параметры устройств (PSN/PNA) из настроек для последующего применения."""
        self.device_settings = settings or {}
        # Настройка сканера
        self.setup_scanner_common()

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
        # Логика определения БУ по секции X
        # Предполагаем, что БУ расположены в сетке 8x5
        # Секции по X: 1-8
        bu_numbers = []
        for y in range(5):  # 5 рядов по Y
            bu_num = (y * 8) + section  # Номер БУ в сетке
            if 1 <= bu_num <= 40:
                bu_numbers.append(bu_num)
        return bu_numbers

    def _get_bu_numbers_by_y_section(self, section: int):
        """Возвращает номера БУ для секции по Y"""
        # Логика определения БУ по секции Y
        # Предполагаем, что БУ расположены в сетке 8x5
        # Секции по Y: 1-5
        bu_numbers = []
        start_bu = (section - 1) * 8 + 1  # Начальный БУ секции
        end_bu = section * 8  # Конечный БУ секции
        for bu_num in range(start_bu, end_bu + 1):
            if 1 <= bu_num <= 40:
                bu_numbers.append(bu_num)
        return bu_numbers

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

    def save_ui_settings(self):
        """Сохраняет состояние контролов UI в QSettings."""
        s = self._ui_settings
        # MA
        s.setValue('channel', self.channel_combo.currentText())
        s.setValue('direction', self.direction_combo.currentText())
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
        # Coord system
        s.setValue('coord_system', self.coord_system_combo.currentText())
        # BU selection
        s.setValue('bu_selection_mode', self.bu_selection_mode.checkedId())
        s.setValue('bu_start', self.bu_start_spin.value())
        s.setValue('bu_end', self.bu_end_spin.value())
        s.setValue('section_number', self.section_spin.value())
        # Normalization
        s.setValue('norm_bu', self.norm_bu_spin.value())
        s.setValue('norm_ppm', self.norm_ppm_spin.value())
        s.setValue('normalize_amplitude', self.normalize_amplitude_checkbox.isChecked())
        # VIP control
        s.setValue('turn_off_vips', self.turn_off_vips_checkbox.isChecked())
        # Сохраняем выбранные БУ
        selected_bu = []
        for i in range(self.bu_list_widget.count()):
            item = self.bu_list_widget.item(i)
            if item.checkState() == QtCore.Qt.Checked:
                selected_bu.append(item.data(QtCore.Qt.UserRole))
        s.setValue('selected_bu', selected_bu)
        # Log level
        s.setValue('log_level', self.log_level_combo.currentText())
        s.sync()

    def load_ui_settings(self):
        """Восстанавливает состояние контролов UI из QSettings."""
        s = self._ui_settings
        # MA
        if (v := s.value('channel')):
            idx = self.channel_combo.findText(v)
            if idx >= 0:
                self.channel_combo.setCurrentIndex(idx)
        if (v := s.value('direction')):
            idx = self.direction_combo.findText(v)
            if idx >= 0:
                self.direction_combo.setCurrentIndex(idx)
        # PNA
        if (v := s.value('s_param')):
            idx = self.s_param_combo.findText(v)
            if idx >= 0:
                self.s_param_combo.setCurrentIndex(idx)
        if (v := s.value('pulse_mode')):
            idx = self.pulse_mode_combo.findText(v)
            if idx > 0:
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
        # Coord system
        if (v := s.value('coord_system')):
            idx = self.coord_system_combo.findText(v)
            if idx >= 0:
                self.coord_system_combo.setCurrentIndex(idx)
        # BU selection
        if (v := s.value('bu_selection_mode')):
            try:
                mode_id = int(v)
                if mode_id >= 0 and mode_id < 5:
                    button = self.bu_selection_mode.button(mode_id)
                    if button:
                        button.setChecked(True)
                        self.on_bu_selection_mode_changed(button)
            except Exception:
                pass
        if (v := s.value('bu_start')):
            try:
                self.bu_start_spin.setValue(int(v))
            except Exception:
                pass
        if (v := s.value('bu_end')):
            try:
                self.bu_end_spin.setValue(int(v))
            except Exception:
                pass
        if (v := s.value('section_number')):
            try:
                self.section_spin.setValue(int(v))
            except Exception:
                pass
        # Normalization
        if (v := s.value('norm_bu')):
            try:
                self.norm_bu_spin.setValue(int(v))
            except Exception:
                pass
        if (v := s.value('norm_ppm')):
            try:
                self.norm_ppm_spin.setValue(int(v))
            except Exception:
                pass
        if (v := s.value('normalize_amplitude')):
            try:
                self.normalize_amplitude_checkbox.setChecked(bool(v) if isinstance(v, bool) else v == 'true')
            except Exception:
                pass
        # VIP control
        if (v := s.value('turn_off_vips')):
            try:
                self.turn_off_vips_checkbox.setChecked(bool(v) if isinstance(v, bool) else v == 'true')
            except Exception:
                pass
        if (v := s.value('selected_bu')):
            try:
                selected_bu = v if isinstance(v, list) else []
                for i in range(self.bu_list_widget.count()):
                    item = self.bu_list_widget.item(i)
                    bu_num = item.data(QtCore.Qt.UserRole)
                    if bu_num in selected_bu:
                        item.setCheckState(QtCore.Qt.Checked)
                    else:
                        item.setCheckState(QtCore.Qt.Unchecked)
            except Exception:
                pass
        # Log level
        if (v := s.value('log_level')):
            idx = self.log_level_combo.findText(v)
            if idx >= 0:
                self.log_level_combo.setCurrentIndex(idx)

    @QtCore.pyqtSlot()
    def update_heatmaps(self):
        """Обновляет 2D графики: рисует прямоугольники в точках с заливкой по цветовой шкале."""
        if hasattr(self, '_updating_heatmaps') and self._updating_heatmaps:
            return
        
        if not self.all_coordinates:
            return
        
        self._updating_heatmaps = True
        try:
            self._update_heatmaps_internal()
        finally:
            self._updating_heatmaps = False
    
    def _update_heatmaps_internal(self):
        """Внутренний метод обновления графиков"""
        all_x = [coord[0] for coord in self.all_coordinates.values()]
        all_y = [coord[1] for coord in self.all_coordinates.values()]
        
        if not all_x or not all_y:
            return
        
        try:
            amp_range = self.amp_cbar.axis.range
            amp_levels = (amp_range[0], amp_range[1])
        except:
            amp_levels = self._amp_levels
            
        try:
            phase_range = self.phase_cbar.axis.range
            phase_levels = (phase_range[0], phase_range[1])
        except:
            phase_levels = self._phase_levels
        
        if self._fixed_dx is None or self._fixed_dy is None:
            uniq_x = np.unique(all_x)
            uniq_y = np.unique(all_y)
            dx = float(np.median(np.diff(uniq_x))) if uniq_x.size > 1 else self._rect_dx_default
            dy = float(np.median(np.abs(np.diff(uniq_y)))) if uniq_y.size > 1 else self._rect_dy_default
            if dx <= 0: dx = self._rect_dx_default
            if dy <= 0: dy = self._rect_dy_default
            self._fixed_dx = dx
            self._fixed_dy = dy
        else:
            dx = self._fixed_dx
            dy = self._fixed_dy

        for (bu_num, ppm_num), (x, y) in self.all_coordinates.items():
            amp_val = self.all_amp_data.get((bu_num, ppm_num))
            phase_val = self.all_phase_data.get((bu_num, ppm_num))
            if amp_val is None or phase_val is None:
                continue
            key = (bu_num, ppm_num)

            rect_amp = self.amp_rect_items.get(key)
            if rect_amp is None:
                from PyQt5.QtWidgets import QGraphicsRectItem
                rect_amp = QGraphicsRectItem(x - dx/2, y - dy/2, dx, dy)
                self.amp_plot.addItem(rect_amp)
                self.amp_rect_items[key] = rect_amp
            else:
                rect_amp.setRect(x - dx/2, y - dy/2, dx, dy)
            amp_color = self._map_value_to_rgb(amp_val, amp_levels, self._amp_cmap)
            rect_amp.setPen(pg.mkPen(None))
            rect_amp.setBrush(pg.mkBrush(amp_color))

            rect_phase = self.phase_rect_items.get(key)
            if rect_phase is None:
                from PyQt5.QtWidgets import QGraphicsRectItem
                rect_phase = QGraphicsRectItem(x - dx/2, y - dy/2, dx, dy)
                self.phase_plot.addItem(rect_phase)
                self.phase_rect_items[key] = rect_phase
            else:
                rect_phase.setRect(x - dx/2, y - dy/2, dx, dy)
            phase_color = self._map_value_to_rgb(phase_val, phase_levels, self._phase_cmap)
            rect_phase.setPen(pg.mkPen(None))
            rect_phase.setBrush(pg.mkBrush(phase_color))

        x_min = min(all_x) - dx
        x_max = max(all_x) + dx
        y_min = min(all_y) - dy
        y_max = max(all_y) + dy
        rect_bounds = QtCore.QRectF(float(x_min), float(y_min), float(x_max - x_min), float(y_max - y_min))
        
        self._dx, self._dy = dx, dy
        self._rect = rect_bounds
        
        if hasattr(self, 'amp_hover_label') and self.amp_hover_label not in self.amp_plot.listDataItems():
            self.amp_plot.addItem(self.amp_hover_label)
        if hasattr(self, 'phase_hover_label') and self.phase_hover_label not in self.phase_plot.listDataItems():
            self.phase_plot.addItem(self.phase_hover_label)

        if not self._view_range_set:
            self.amp_plot.setRange(xRange=(x_min, x_max), yRange=(y_min, y_max), padding=0)
            self.phase_plot.setRange(xRange=(x_min, x_max), yRange=(y_min, y_max), padding=0)
            self._view_range_set = True

        self.amp_plot.setAspectLocked(False)
        self.phase_plot.setAspectLocked(False)

    def _map_value_to_rgb(self, value, levels, colormap):
        """Преобразует значение в RGB-кортеж по заданным уровням и ColorMap."""
        try:
            if value is None or np.isnan(value):
                return (160, 160, 160)
            vmin, vmax = levels
            if vmax == vmin:
                t = 0.0
            else:
                t = (float(value) - float(vmin)) / (float(vmax) - float(vmin))
            t = max(0.0, min(1.0, t))
            rgba = colormap.map([t])[0]
            return (int(rgba[0]), int(rgba[1]), int(rgba[2]))
        except Exception:
            return (160, 160, 160)
    
    def _on_colorbar_changed(self):
        """Обработчик изменения ColorBar - перерисовывает графики с новыми цветами"""
        if not self.all_coordinates:
            return
        
        try:
            amp_range = self.amp_cbar.axis.range
            amp_levels = (amp_range[0], amp_range[1])
        except:
            amp_levels = self._amp_levels
            
        try:
            phase_range = self.phase_cbar.axis.range
            phase_levels = (phase_range[0], phase_range[1])
        except:
            phase_levels = self._phase_levels
        
        for (bu_num, ppm_num) in self.all_coordinates.keys():
            amp_val = self.all_amp_data.get((bu_num, ppm_num))
            if amp_val is not None:
                rect_amp = self.amp_rect_items.get((bu_num, ppm_num))
                if rect_amp:
                    color = self._map_value_to_rgb(amp_val, amp_levels, self._amp_cmap)
                    rect_amp.setBrush(pg.mkBrush(color))
            
            phase_val = self.all_phase_data.get((bu_num, ppm_num))
            if phase_val is not None:
                rect_phase = self.phase_rect_items.get((bu_num, ppm_num))
                if rect_phase:
                    color = self._map_value_to_rgb(phase_val, phase_levels, self._phase_cmap)
                    rect_phase.setBrush(pg.mkBrush(color))

    def on_normalize_amplitude_changed(self, state):
        """Обработчик изменения состояния чекбокса нормировки амплитуды"""
        if not self.all_amp_data_raw:
            # Нет данных для пересчета
            return
        
        is_normalized = self.normalize_amplitude_checkbox.isChecked()
        logger.info(f"Переключение нормировки амплитуды: {'включена' if is_normalized else 'выключена'}")
        
        # Пересчитываем все амплитуды
        for key, amp_raw in self.all_amp_data_raw.items():
            if is_normalized and self.norm_amplitude_value is not None:
                # Нормированная амплитуда
                self.all_amp_data[key] = amp_raw - self.norm_amplitude_value
            else:
                # Абсолютная амплитуда
                self.all_amp_data[key] = amp_raw
        
        # Перерисовываем графики
        self.update_heatmaps()
        logger.info("Графики амплитуды обновлены")
    
    def autoscale_axes(self):
        """Автомасштабирование осей X и Y для обоих графиков"""
        self.amp_plot.autoRange()
        self.phase_plot.autoRange()
        logger.info("Автомасштабирование осей выполнено")

    def keyPressEvent(self, event):
        """Обработка нажатий клавиш"""
        from PyQt5.QtCore import Qt
        
        if event.key() == Qt.Key_A:
            logger.info("Нажата клавиша 'A' - автомасштабирование осей")
            self.autoscale_axes()
        else:
            super().keyPressEvent(event)