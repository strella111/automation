from PyQt5 import QtWidgets, QtCore
import os
from PyQt5.QtWidgets import QMessageBox, QStyle
from PyQt5.QtCore import QSize
from loguru import logger
import threading
import time
import numpy as np
from core.measurements.check_stend_afar.check_stend_afar import CheckAfarStend
from core.common.enums import Channel, Direction
from config.settings_manager import get_ui_settings

from ui.dialogs.pna_file_dialog import PnaFileDialog
from ui.widgets.base_measurement_widget import BaseMeasurementWidget



class StendCheckAfarWidget(BaseMeasurementWidget):
    update_data_signal = QtCore.pyqtSignal(dict, int)   # словарь {fv_angle: [A1,P1,...,A32,P32] с относительными фазами}, bu_num
    update_amp_data_signal = QtCore.pyqtSignal(list, int)  # список амплитуд [A1, A2, ..., A32], bu_num
    update_realtime_signal = QtCore.pyqtSignal(float, int, float, float, int)  # angle, ppm_index(1..32), amp_abs, phase_rel, bu_num
    update_lz_signal = QtCore.pyqtSignal(dict, int)  # {lz: (mean_amp_delta, mean_delay_delta)}, bu_num
    bu_completed_signal = QtCore.pyqtSignal(int)  # номер БУ, для которого завершено измерение
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

        afar_widget = QtWidgets.QWidget()
        afar_layout = QtWidgets.QHBoxLayout(afar_widget)
        afar_layout.setContentsMargins(0, 0, 0, 0)
        self.afar_connect_btn = QtWidgets.QPushButton('АФАР')
        self.afar_connect_btn.setMinimumHeight(40)
        self.set_button_connection_state(self.afar_connect_btn, False)
        afar_layout.addWidget(self.afar_connect_btn)
        self.connect_layout.addWidget(afar_widget)

        self.left_layout.addWidget(self.connect_group)

        self.param_tabs = QtWidgets.QTabWidget()

        self.afar_tab = QtWidgets.QWidget()
        self.afar_tab_layout = QtWidgets.QFormLayout(self.afar_tab)

        self.channel_combo = QtWidgets.QComboBox()
        self.channel_combo.addItems(['Приемник', 'Передатчик'])
        self.afar_tab_layout.addRow('Канал:', self.channel_combo)

        self.direction_combo = QtWidgets.QComboBox()
        self.direction_combo.addItems(['Горизонтальная', 'Вертикальная'])
        self.afar_tab_layout.addRow('Поляризация:', self.direction_combo)


        self.param_tabs.addTab(self.afar_tab, 'АФАР')

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
        self.pna_tab_layout.addRow('Выходная мощность (дБм):', self.pna_power)

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
        self.pna_number_of_points.addItems(['3', '11', '21','33', '51', '101', '201'])
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
        self.pulse_width.setDecimals(3)
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

        # Группа режимов проверки
        check_mode_group = QtWidgets.QGroupBox('Режимы проверки')
        check_mode_layout = QtWidgets.QVBoxLayout(check_mode_group)
        check_mode_layout.setContentsMargins(15, 15, 15, 15)
        
        self.check_fv_checkbox = QtWidgets.QCheckBox('Проверять ФВ')
        self.check_fv_checkbox.setChecked(True)  # По умолчанию включено
        check_mode_layout.addWidget(self.check_fv_checkbox)
        
        self.check_lz_checkbox = QtWidgets.QCheckBox('Проверять ЛЗ')
        self.check_lz_checkbox.setChecked(True)  # По умолчанию включено
        check_mode_layout.addWidget(self.check_lz_checkbox)
        
        self.meas_tab_layout.addWidget(check_mode_group)

        # Группа выбора БУ для проверки
        bu_selection_group = QtWidgets.QGroupBox('Выбор БУ для проверки')
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
        self.bu_list_widget.setMinimumHeight(200)
        self.bu_list_widget.setMaximumHeight(300)
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
        self.bu_selection_mode.buttonClicked.connect(lambda: self.save_ui_settings())
        self.bu_start_spin.valueChanged.connect(self.on_range_changed)
        self.bu_start_spin.valueChanged.connect(lambda: self.save_ui_settings())
        self.bu_end_spin.valueChanged.connect(self.on_range_changed)
        self.bu_end_spin.valueChanged.connect(lambda: self.save_ui_settings())
        self.section_spin.valueChanged.connect(lambda: self.save_ui_settings())
        self.check_fv_checkbox.stateChanged.connect(lambda: self.save_ui_settings())
        self.check_lz_checkbox.stateChanged.connect(lambda: self.save_ui_settings())
        self.bu_list_widget.itemChanged.connect(lambda: self.save_ui_settings())

        self.meas_tab_layout.addWidget(bu_selection_group)


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

        scroll_layout = QtWidgets.QGridLayout()
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

        ps_main_layout.addLayout(scroll_layout)

        self.meas_tab_layout.addWidget(ps_group)


        self.meas_tab_layout.addStretch()

        meas_scroll = QtWidgets.QScrollArea()
        meas_scroll.setWidgetResizable(True)
        meas_scroll.setWidget(self.meas_tab)
        meas_scroll.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAsNeeded)
        meas_scroll.setVerticalScrollBarPolicy(QtCore.Qt.ScrollBarAsNeeded)
        
        self.param_tabs.addTab(meas_scroll, 'Настройки измерения')
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

        bu_selector_widget = QtWidgets.QWidget()
        bu_selector_layout = QtWidgets.QHBoxLayout(bu_selector_widget)
        bu_selector_layout.setContentsMargins(5, 5, 5, 5)
        bu_selector_layout.setSpacing(5)
        bu_selector_layout.addStretch()
        
        self.bu_prev_btn = QtWidgets.QPushButton('◄')
        self.bu_prev_btn.setFixedWidth(30)
        self.bu_prev_btn.setToolTip('Предыдущий БУ')
        bu_selector_layout.addWidget(self.bu_prev_btn)
        
        bu_label = QtWidgets.QLabel('БУ:')
        bu_label.setAlignment(QtCore.Qt.AlignCenter)
        bu_selector_layout.addWidget(bu_label)
        
        self.bu_combo = QtWidgets.QComboBox()
        for i in range(1, 41):
            self.bu_combo.addItem(f'БУ №{i}', i)
        self.bu_combo.setCurrentIndex(0)
        self.bu_combo.setMaximumWidth(200)
        bu_selector_layout.addWidget(self.bu_combo, 0)
        
        self.bu_next_btn = QtWidgets.QPushButton('►')
        self.bu_next_btn.setFixedWidth(30)
        self.bu_next_btn.setToolTip('Следующий БУ')
        bu_selector_layout.addWidget(self.bu_next_btn)
        
        bu_selector_layout.addStretch()
        
        self.right_layout.addWidget(bu_selector_widget)

        self.bu_prev_btn.clicked.connect(self.select_prev_bu)
        self.bu_next_btn.clicked.connect(self.select_next_bu)
        self.bu_combo.currentIndexChanged.connect(self.on_bu_selected)
        self.bu_combo.currentIndexChanged.connect(lambda: self.save_ui_settings())

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
        self.right_layout.addWidget(self.view_tabs, stretch=5)

        self.console, self.log_handler, self.log_level_combo = self.create_console_with_log_level(self.right_layout, console_height=180)
        logger.add(self.log_handler, format="{time:HH:mm:ss.SSS} | {level} | {name}:{function}:{line} | {message}")

        self._check_thread = None

        self.afar_connect_btn.clicked.connect(self.connect_afar)
        self.pna_connect_btn.clicked.connect(self.connect_pna)
        self.gen_connect_btn.clicked.connect(self.connect_trigger)
        self.apply_btn.clicked.connect(self.apply_params)
        self.start_btn.clicked.connect(self.start_check)
        self.stop_btn.clicked.connect(self.stop_check)
        self.pause_btn.clicked.connect(self.pause_check)

        self.update_data_signal.connect(self.update_table_from_data)
        self.update_amp_data_signal.connect(self.update_table_from_amp_data_with_bu)
        self.update_realtime_signal.connect(self.update_table_realtime)
        self.update_lz_signal.connect(self._accumulate_lz_data)
        self.update_lz_signal.connect(self.update_delay_table_from_lz)
        self.bu_completed_signal.connect(self.on_bu_completed)
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
        self.measurement_start_time = None  # Время начала измерения
        self._stend_lz_data = {}  # Инициализация данных ЛЗ
        self._stend_fv_data = {}  # Инициализация данных ФВ
        self.bu_data = {}  # Словарь для хранения данных по БУ: {bu_num: {'amp_data': [...], 'fv_data': {...}, 'lz_data': {...}}}
        
        # Хранение данных по БУ: {bu_num: {'fv_data': {...}, 'lz_data': {...}, 'amp_data': [...]}}
        self.bu_data = {}

        self.set_button_connection_state(self.pna_connect_btn, False)
        self.set_button_connection_state(self.afar_connect_btn, False)

        self._ui_settings = get_ui_settings('check_stend_afar')
        self.check_fv_checkbox.blockSignals(True)
        self.check_lz_checkbox.blockSignals(True)
        self.load_ui_settings()
        self.check_fv_checkbox.blockSignals(False)
        self.check_lz_checkbox.blockSignals(False)

        self.log_level_combo.currentTextChanged.connect(lambda: self._ui_settings.setValue('log_level', self.log_level_combo.currentText()))



    @QtCore.pyqtSlot()
    def on_check_finished(self):
        """Слот для завершения проверки"""
        self.set_buttons_enabled(True)
        self.pause_btn.setText('Пауза')
        self.check_completed = True
        logger.info('Проверка завершена, интерфейс восстановлен')

        self.show_completion_dialog()

    def show_completion_dialog(self):
        """Показывает диалог завершения измерения с временем выполнения"""
        if self.measurement_start_time is None:
            duration_text = "Время выполнения неизвестно"
        else:
            duration_seconds = time.time() - self.measurement_start_time
            hours = int(duration_seconds // 3600)
            minutes = int((duration_seconds % 3600) // 60)
            seconds = int(duration_seconds % 60)
            
            if hours > 0:
                duration_text = f"{hours}ч {minutes}м {seconds}с"
            elif minutes > 0:
                duration_text = f"{minutes}м {seconds}с"
            else:
                duration_text = f"{seconds}с"

        msg_box = QMessageBox()
        msg_box.setWindowTitle("Измерение завершено")
        msg_box.setIcon(QMessageBox.Information)
        msg_box.setText("Измерение успешно завершено!")
        msg_box.setInformativeText(f"Время выполнения: {duration_text}")
        msg_box.setStandardButtons(QMessageBox.Ok)
        msg_box.setDefaultButton(QMessageBox.Ok)

        msg_box.exec_()

    def show_stop_dialog(self):
        """Показывает диалог остановки измерения с временем выполнения"""
        if self.measurement_start_time is None:
            duration_text = "Время выполнения неизвестно"
        else:
            duration_seconds = time.time() - self.measurement_start_time
            hours = int(duration_seconds // 3600)
            minutes = int((duration_seconds % 3600) // 60)
            seconds = int(duration_seconds % 60)
            
            if hours > 0:
                duration_text = f"{hours}ч {minutes}м {seconds}с"
            elif minutes > 0:
                duration_text = f"{minutes}м {seconds}с"
            else:
                duration_text = f"{seconds}с"

        msg_box = QMessageBox()
        msg_box.setWindowTitle("Измерение остановлено")
        msg_box.setIcon(QMessageBox.Warning)
        msg_box.setText("Измерение было остановлено пользователем.")
        msg_box.setInformativeText(f"Время выполнения до остановки: {duration_text}")
        msg_box.setStandardButtons(QMessageBox.Ok)
        msg_box.setDefaultButton(QMessageBox.Ok)

        msg_box.exec_()

    @QtCore.pyqtSlot(bool)
    def set_buttons_enabled(self, enabled: bool):
        """Управляет доступностью кнопок"""
        self.afar_connect_btn.setEnabled(enabled)
        self.pna_connect_btn.setEnabled(enabled)
        self.apply_btn.setEnabled(enabled)
        self.start_btn.setEnabled(enabled)
        self.stop_btn.setEnabled(not enabled)
        self.pause_btn.setEnabled(not enabled)


    @QtCore.pyqtSlot(dict, int)
    def update_delay_table_from_lz(self, lz_results: dict, bu_num: int):
        """Отрисовывает усреднённые значения ЛЗ и статусы по допускам.
        Ожидается формат {lz:int: (amp_delta_db:float, delay_delta_ps:float)}, bu_num:int
        Сохраняет данные в bu_data и отрисовывает только для текущего выбранного БУ"""
        try:
            if bu_num is not None:
                if bu_num not in self.bu_data:
                    self.bu_data[bu_num] = {}
                if 'lz_data' not in self.bu_data[bu_num]:
                    self.bu_data[bu_num]['lz_data'] = {}
                self.bu_data[bu_num]['lz_data'].update(lz_results)

            current_bu = self.bu_combo.currentData()
            if bu_num is not None and current_bu != bu_num:
                return

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

    def _update_delay_table_from_lz_data(self, lz_results: dict):
        """Внутренний метод для отрисовки данных ЛЗ без сохранения (используется при переключении БУ)"""
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
            logger.error(f"Ошибка отрисовки данных ЛЗ: {e}")

    def update_table_from_amp_data(self, amp_data: list):
        """Заполняет таблицу только амплитудой.
        amp_data: список из 32 значений амплитуды для каждого ППМ
        """
        try:
            def get_abs_amp_min():
                return float(self.abs_amp_min_rx.value()) if self.channel_combo.currentText() == 'Приемник' else float(self.abs_amp_min_tx.value())

            for row in range(32):
                self.results_table.setItem(row, 0, self.create_centered_table_item(str(row + 1)))
                for col in range(1, 15):
                    self.results_table.setItem(row, col, self.create_centered_table_item(""))

            abs_min = get_abs_amp_min()
            for ppm_idx in range(min(32, len(amp_data))):
                row = ppm_idx
                amp_val = amp_data[ppm_idx]
                amp_ok = (amp_val >= abs_min)
                self.results_table.setItem(row, 1, self.create_status_table_item(f"{amp_val:.2f}", amp_ok))

            self.results_table.viewport().update()
        except Exception as e:
            logger.error(f"Ошибка заполнения таблицы данными амплитуды: {e}")

    @QtCore.pyqtSlot(dict, int)
    def update_table_from_data(self, data: dict, bu_num: int):
        """Заполняет таблицу по словарю {fv_angle: [A1,P1,...,A32,P32]}.
        Фазы считаются относительными (для 0° – всегда 0). Статусы считаем только по фазе.
        Если передан bu_num, сохраняет данные для этого БУ.
        """
        try:
            if bu_num is not None:
                if bu_num not in self.bu_data:
                    self.bu_data[bu_num] = {}
                existing_keys = list(self.bu_data[bu_num].keys()) if bu_num in self.bu_data else []
                if 'fv_data' not in self.bu_data[bu_num]:
                    self.bu_data[bu_num]['fv_data'] = {}
                self.bu_data[bu_num]['fv_data'] = data
                logger.debug(f"Сохранены данные ФВ для БУ №{bu_num}. Существующие ключи до: {existing_keys}, после: {list(self.bu_data[bu_num].keys())}")

                current_bu = self.bu_combo.currentData()

                if current_bu == bu_num:
                    self._update_table_from_fv_data(data)
                else:
                    index = self.bu_combo.findData(bu_num)
                    if index >= 0:
                        QtCore.QTimer.singleShot(0, lambda bu=bu_num: self._switch_to_bu(bu))
            else:
                self._update_table_from_fv_data(data)
        except Exception as e:
            logger.error(f"Ошибка заполнения таблицы из словаря данных: {e}")

    def _update_table_from_fv_data(self, data: dict):
        """Внутренний метод для обновления таблицы данными ФВ (без сохранения и переключения)"""
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
                    idx = ppm_idx * 2
                    if not values or len(values) <= idx + 1:
                        self.results_table.setItem(row, col, self.create_centered_table_item(""))
                        self.results_table.setItem(row, col + 1, self.create_centered_table_item(""))
                        col += 2
                        continue

                    amp_val = values[idx] if idx < len(values) else 0.0
                    phase_rel = values[idx + 1] if idx + 1 < len(values) else 0.0

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
            logger.error(f"Ошибка обновления таблицы данными ФВ: {e}")

    def update_table_from_amp_data_with_bu(self, amp_data: list, bu_num: int):
        """Обновляет таблицу данными амплитуды для конкретного БУ"""
        if bu_num not in self.bu_data:
            self.bu_data[bu_num] = {}
        self.bu_data[bu_num]['amp_data'] = amp_data.copy()
        logger.debug(f"Сохранены данные амплитуды для БУ №{bu_num}: {len(amp_data)} значений. Ключи в bu_data[{bu_num}]: {list(self.bu_data[bu_num].keys())}")

        current_bu = self.bu_combo.currentData()

        if current_bu == bu_num:
            self.update_table_from_amp_data(amp_data)
        else:
            index = self.bu_combo.findData(bu_num)
            if index >= 0:
                QtCore.QTimer.singleShot(0, lambda bu=bu_num: self._switch_to_bu(bu))

    @QtCore.pyqtSlot(float, int, float, float, int)
    def update_table_realtime(self, angle: float, ppm_index: int, amp_abs: float, phase_rel: float, bu_num: int):
        """Точечное обновление таблицы по мере поступления данных. Сохраняет данные в bu_data."""
        try:
            if bu_num not in self.bu_data:
                self.bu_data[bu_num] = {}
            if 'fv_data' not in self.bu_data[bu_num]:
                self.bu_data[bu_num]['fv_data'] = {}

            if angle not in self.bu_data[bu_num]['fv_data']:
                self.bu_data[bu_num]['fv_data'][angle] = [0.0] * 64

            idx = (ppm_index - 1) * 2
            if idx < len(self.bu_data[bu_num]['fv_data'][angle]):
                self.bu_data[bu_num]['fv_data'][angle][idx] = amp_abs
                phase_normalized = self._normalize_phase(phase_rel)
                self.bu_data[bu_num]['fv_data'][angle][idx + 1] = phase_normalized

            current_bu = self.bu_combo.currentData()
            if current_bu != bu_num:
                return

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
            phase_normalized = self._normalize_phase(phase_rel)
            if angle == 0.0:
                self.results_table.setItem(row, base_col + 1, self.create_centered_table_item(f"{phase_normalized:.1f}"))
            else:
                tol = self.check_criteria.get('phase_shifter_tolerances', {}).get(angle)
                if tol is None:
                    tol = self.check_criteria.get('phase_shifter_tolerances', {}).get(float(angle))
                ok = (tol['min'] <= phase_normalized - angle <= tol['max']) if tol else (-2.0 <= phase_normalized - angle <= 2.0)
                self.results_table.setItem(row, base_col + 1, self.create_status_table_item(f"{phase_normalized:.1f}", ok))

            try:
                self.results_table.viewport().update()
            except Exception:
                pass
        except Exception as e:
            logger.error(f"Ошибка realtime-обновления таблицы: {e}")

    def apply_params(self):
        """Сохраняет параметры из вкладок"""
        # АФАР
        self.channel = self.channel_combo.currentText()
        self.direction = self.direction_combo.currentText()

        # PNA
        self.pna_settings['s_param'] = self.s_param_combo.currentText()
        self.pna_settings['power'] = self.pna_power.value()
        self.pna_settings['freq_start'] = self.pna_start_freq.value() * 10 ** 6
        self.pna_settings['freq_stop'] = self.pna_stop_freq.value() * 10 ** 6
        self.pna_settings['freq_points'] = self.pna_number_of_points.currentText()
        self.pna_settings['settings_file'] = self.settings_file_edit.text()
        self.pna_settings['pulse_mode'] = self.pulse_mode_combo.currentText()
        self.pna_settings['pulse_period'] = self.pulse_period.value() / 10 ** 6
        self.pna_settings['pulse_width'] = self.pulse_width.value() / 10 ** 6

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
        # АФАР
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
        # Criteria
        s.setValue('abs_amp_min_rx', float(self.abs_amp_min_rx.value()))
        s.setValue('abs_amp_min_tx', float(self.abs_amp_min_tx.value()))
        # Phase shifters
        for angle, controls in self.phase_shifter_tolerances.items():
            s.setValue(f'ps_tol_{angle}_min', float(controls['min'].value()))
            s.setValue(f'ps_tol_{angle}_max', float(controls['max'].value()))
        # Synchronization parameters
        s.setValue('trig_ttl_channel', self.trig_ttl_channel.currentText())
        s.setValue('trig_ext_channel', self.trig_ext_channel.currentText())
        s.setValue('trig_start_lead', float(self.trig_start_lead.value()))
        s.setValue('trig_pulse_period', float(self.trig_pulse_period.value()))
        s.setValue('trig_min_alarm_guard', float(self.trig_min_alarm_guard.value()))
        s.setValue('trig_ext_debounce', float(self.trig_ext_debounce.value()))
        # Log level
        s.setValue('log_level', self.log_level_combo.currentText())
        # Режимы проверки
        check_fv_value = self.check_fv_checkbox.isChecked()
        check_lz_value = self.check_lz_checkbox.isChecked()
        s.setValue('check_fv', check_fv_value)
        s.setValue('check_lz', check_lz_value)
        logger.debug(f"Сохранены режимы проверки: check_fv={check_fv_value}, check_lz={check_lz_value}")
        # Режим выбора БУ
        s.setValue('bu_selection_mode', self.bu_selection_mode.checkedId())
        # Диапазон БУ
        s.setValue('bu_start', self.bu_start_spin.value())
        s.setValue('bu_end', self.bu_end_spin.value())
        # Секция
        s.setValue('section', self.section_spin.value())
        # Выбранные БУ в режиме "Выборочно"
        selected_bu_list = []
        for i in range(self.bu_list_widget.count()):
            item = self.bu_list_widget.item(i)
            if item.checkState() == QtCore.Qt.Checked:
                selected_bu_list.append(item.data(QtCore.Qt.UserRole))
        s.setValue('selected_bu_list', selected_bu_list)
        # Текущий выбранный БУ в комбобоксе
        s.setValue('current_bu', self.bu_combo.currentData())
        s.sync()

    def load_ui_settings(self):
        s = self._ui_settings
        if (v := s.value('channel')):
            idx = self.channel_combo.findText(v)
            if idx >= 0: self.channel_combo.setCurrentIndex(idx)
        if (v := s.value('direction')):
            idx = self.direction_combo.findText(v)
            if idx >= 0: self.direction_combo.setCurrentIndex(idx)
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

        for angle, controls in self.phase_shifter_tolerances.items():
            if (v := s.value(f'ps_tol_{angle}_min')) is not None:
                try: controls['min'].setValue(float(v))
                except Exception: pass
            if (v := s.value(f'ps_tol_{angle}_max')) is not None:
                try: controls['max'].setValue(float(v))
                except Exception: pass

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
                try: widget.setValue(float(val))
                except Exception: pass
        if (v := s.value('log_level')):
            idx = self.log_level_combo.findText(v)
            if idx >= 0:
                self.log_level_combo.setCurrentIndex(idx)
        v = s.value('check_fv')
        if v is not None:
            if isinstance(v, bool):
                check_fv_loaded = v
            elif isinstance(v, str):
                check_fv_loaded = v.lower() in ('true', '1', 'yes')
            else:
                check_fv_loaded = bool(v)
            self.check_fv_checkbox.setChecked(check_fv_loaded)
            logger.debug(f"Загружен режим проверки ФВ: {check_fv_loaded} (исходное значение: {v}, тип: {type(v)})")
        v = s.value('check_lz')
        if v is not None:
            if isinstance(v, bool):
                check_lz_loaded = v
            elif isinstance(v, str):
                check_lz_loaded = v.lower() in ('true', '1', 'yes')
            else:
                check_lz_loaded = bool(v)
            self.check_lz_checkbox.setChecked(check_lz_loaded)
            logger.debug(f"Загружен режим проверки ЛЗ: {check_lz_loaded} (исходное значение: {v}, тип: {type(v)})")
        if (v := s.value('bu_selection_mode')) is not None:
            mode_id = int(v)
            button = self.bu_selection_mode.button(mode_id)
            if button:
                button.setChecked(True)
                self.on_bu_selection_mode_changed(button)
        if (v := s.value('bu_start')) is not None:
            self.bu_start_spin.setValue(int(v))
        if (v := s.value('bu_end')) is not None:
            self.bu_end_spin.setValue(int(v))
        if (v := s.value('section')) is not None:
            self.section_spin.setValue(int(v))
        if (v := s.value('selected_bu_list')):
            try:
                selected_list = v if isinstance(v, list) else []
                for i in range(self.bu_list_widget.count()):
                    item = self.bu_list_widget.item(i)
                    bu_num = item.data(QtCore.Qt.UserRole)
                    if bu_num in selected_list:
                        item.setCheckState(QtCore.Qt.Checked)
                    else:
                        item.setCheckState(QtCore.Qt.Unchecked)
            except Exception:
                pass
        if (v := s.value('current_bu')) is not None:
            try:
                bu_num = int(v)
                index = self.bu_combo.findData(bu_num)
                if index >= 0:
                    self.bu_combo.setCurrentIndex(index)
            except Exception:
                pass


    def start_check(self):
        """Запускает процесс проверки"""
        if not (self.afar and self.pna and self.trigger and getattr(self.trigger, 'connection', None)):
            self.show_error_message("Ошибка", "Сначала подключите все устройства!")
            return

        selected_bu = self.get_selected_bu_numbers()
        if not selected_bu:
            self.show_error_message("Ошибка", "Выберите хотя бы один БУ для проверки!")
            return

        self._stop_flag.clear()
        self._pause_flag.clear()
        self.pause_btn.setText('Пауза')

        self.results_table.clearContents()
        for row in range(32):
            self.results_table.setItem(row, 0, self.create_centered_table_item(str(row + 1)))
            for col in range(1, 15):
                self.results_table.setItem(row, col, QtWidgets.QTableWidgetItem(""))

        self.delay_table.clearContents()
        delay_discretes = [1, 2, 4, 8]
        for row, discrete in enumerate(delay_discretes):
            self.delay_table.setItem(row, 0, self.create_centered_table_item(f"ЛЗ{discrete}"))
            for col in range(1, 5):
                self.delay_table.setItem(row, col, QtWidgets.QTableWidgetItem(""))

        self.ppm_data.clear()
        self.check_completed = False
        self._stend_lz_data = {}
        self._stend_fv_data = {}

        check_fv = self.check_fv_checkbox.isChecked()
        self.update_table_headers_for_bu(has_fv=check_fv)

        self.measurement_start_time = time.time()

        self.set_buttons_enabled(False)
        logger.info(f"Запуск проверки АФАР для БУ: {selected_bu}...")
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

        self.show_stop_dialog()

    def _run_check(self):
        logger.info("Начало выполнения проверки в отдельном потоке")
        try:
            channel = Channel.Receiver if self.channel_combo.currentText() == 'Приемник' else Channel.Transmitter
            direction = Direction.Horizontal if self.direction_combo.currentText() == 'Горизонтальная' else Direction.Vertical
            logger.info(f'Используем канал: {channel.value}, поляризация: {direction.value}')

            self.setup_pna_common()

            selected_bu = self.get_selected_bu_numbers()
            logger.info(f'Проверка будет выполнена для БУ: {selected_bu}')

            self._current_measurement_bu_list = selected_bu

            class CheckAfarWithCallback(CheckAfarStend):
                def __init__(self, afar, pna, gen, bu_numbers, stop_event, pause_event, check_fv=True, check_lz=True,
                             criteria=None, parent_widget=None):
                    super().__init__(afar, pna, gen, bu_numbers, stop_event, pause_event, check_fv=check_fv, check_lz=check_lz)

                    if criteria:
                        self.phase_shifter_tolerances = criteria.get('phase_shifter_tolerances', None)

                def start(self, chanel: Channel, direction: Direction):
                    """Переопределяем метод start для очистки оперативных данных"""
                    self.data_relative = None
                    
                    results = super().start(chanel, direction)
                    return results

            check_fv = self.check_fv_checkbox.isChecked()
            check_lz = self.check_lz_checkbox.isChecked()

            check = CheckAfarWithCallback(
                afar=self.afar,
                pna=self.pna,
                gen=self.trigger,
                bu_numbers=selected_bu,
                stop_event=self._stop_flag,
                pause_event=self._pause_flag,
                check_fv=check_fv,
                check_lz=check_lz,
                criteria=self.check_criteria,
                parent_widget=self
            )

            try:
                check.realtime_callback = self.update_realtime_signal
            except Exception:
                pass
            try:
                check.delay_callback = self.update_lz_signal
            except Exception:
                pass
            try:
                check.amp_data_callback = self.update_amp_data_signal
            except Exception:
                pass
            try:
                check.data_callback = self.update_data_signal
            except Exception:
                pass
            try:
                check.bu_completed_callback = self.bu_completed_signal
            except Exception:
                pass

            try:
                check.period = float(self.trig_pulse_period.value()) * 1e-6
                check.lead = float(self.trig_start_lead.value()) * 1e-3
            except Exception:
                pass

            check.start(chanel=channel, direction=direction)

            if not self._stop_flag.is_set():
                logger.info('Проверка всех БУ завершена успешно.')

        except Exception as e:
            self.error_signal.emit("Ошибка проверки", f"Произошла ошибка при выполнении проверки: {str(e)}")
            logger.error(f"Ошибка при выполнении проверки: {e}")
            self.turn_off_pna()
        finally:
            self.check_finished_signal.emit()

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
        for y in range(5):
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

    def select_prev_bu(self):
        """Переключает на предыдущий БУ"""
        current_index = self.bu_combo.currentIndex()
        if current_index > 0:
            self.bu_combo.setCurrentIndex(current_index - 1)

    def select_next_bu(self):
        """Переключает на следующий БУ"""
        current_index = self.bu_combo.currentIndex()
        if current_index < self.bu_combo.count() - 1:
            self.bu_combo.setCurrentIndex(current_index + 1)

    def on_bu_selected(self, index: int):
        """Обработчик изменения выбранного БУ - обновляет таблицу данными из bu_data"""
        if index < 0:
            return
        bu_num = self.bu_combo.itemData(index)
        
        if not bu_num:
            return
        
        logger.debug(f"Переключение на БУ №{bu_num} через комбобокс")

        if bu_num in self.bu_data:
            data = self.bu_data[bu_num]
            logger.debug(f"Найдены данные для БУ №{bu_num}: {list(data.keys())}")

            has_amp = 'amp_data' in data
            has_fv = 'fv_data' in data
            has_lz = 'lz_data' in data

            self.update_table_headers_for_bu(has_fv)

            if has_fv:
                logger.debug(f"Отрисовка данных ФВ для БУ №{bu_num}")
                self._update_table_from_fv_data(data['fv_data'])
            elif has_amp:
                logger.debug(f"Отрисовка данных амплитуды для БУ №{bu_num}")
                self.update_table_from_amp_data(data['amp_data'])
            else:
                logger.debug(f"Нет данных для БУ №{bu_num}, очищаем таблицу")
                self._clear_results_table()

            if has_lz:
                logger.debug(f"Отрисовка данных ЛЗ для БУ №{bu_num} из bu_data")
                self._update_delay_table_from_lz_data(data['lz_data'])
            else:
                self._clear_delay_table()
        else:
            logger.debug(f"Данные для БУ №{bu_num} не найдены в bu_data, очищаем таблицу")
            self._clear_results_table()
            self._clear_delay_table()

    def _accumulate_lz_data(self, lz_chunk: dict, bu_num: int):
        """Накопление данных ЛЗ в bu_data (вызывается через сигнал)"""
        try:
            if bu_num not in self.bu_data:
                self.bu_data[bu_num] = {}
            if 'lz_data' not in self.bu_data[bu_num]:
                self.bu_data[bu_num]['lz_data'] = {}
            self.bu_data[bu_num]['lz_data'].update(lz_chunk)

            for k, v in lz_chunk.items():
                self._stend_lz_data[k] = v
        except Exception as e:
            logger.error(f"Ошибка накопления данных ЛЗ: {e}")

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

    def update_table_headers(self):
        """Обновляет заголовки таблицы в зависимости от режима проверки"""
        check_fv = self.check_fv_checkbox.isChecked()
        self.update_table_headers_for_bu(check_fv)

    def update_table_headers_for_bu(self, has_fv: bool):
        """Обновляет заголовки таблицы в зависимости от наличия данных ФВ"""
        if has_fv:
            # Если есть данные ФВ, показываем все колонки (амплитуда + фаза)
            self.results_table.setHorizontalHeaderLabels([
                'ППМ', '0° Амп.', '0° Фаза', '5.625° Амп.', '5.625° Фаза', '11.25° Амп.', '11.25° Фаза',
                '22.5° Амп.', '22.5° Фаза', '45° Амп.', '45° Фаза', '90° Амп.', '90° Фаза', '180° Амп.', '180° Фаза'])
        else:
            # Если нет данных ФВ, показываем только амплитуду
            self.results_table.setHorizontalHeaderLabels([
                'ППМ', 'Амплитуда (дБ)', '', '', '', '', '', '', '', '', '', '', '', '', ''])

    def _clear_results_table(self):
        """Очищает таблицу результатов ППМ"""
        for row in range(32):
            self.results_table.setItem(row, 0, self.create_centered_table_item(str(row + 1)))
            for col in range(1, 15):
                self.results_table.setItem(row, col, self.create_centered_table_item(""))
        try:
            self.results_table.viewport().update()
        except Exception:
            pass

    def _clear_delay_table(self):
        """Очищает таблицу линий задержки"""
        delay_discretes = [1, 2, 4, 8]
        for row, discrete in enumerate(delay_discretes):
            self.delay_table.setItem(row, 0, self.create_centered_table_item(f"ЛЗ{discrete}"))
            for col in range(1, 5):
                self.delay_table.setItem(row, col, self.create_centered_table_item(""))
        try:
            self.delay_table.viewport().update()
        except Exception:
            pass

    def _normalize_phase(self, phase: float) -> float:
        """Нормализует фазу в диапазон [-180, 180]"""
        while phase > 180:
            phase -= 360
        while phase < -180:
            phase += 360
        return phase

    def _switch_to_bu(self, bu_num: int):
        """Переключает комбобокс на указанный БУ и обновляет таблицу данными из bu_data"""
        index = self.bu_combo.findData(bu_num)
        if index >= 0:
            self.bu_combo.blockSignals(True)
            self.bu_combo.setCurrentIndex(index)
            self.bu_combo.blockSignals(False)
            
            logger.debug(f"Автоматическое переключение на БУ №{bu_num}")
            logger.debug(f"Текущее состояние bu_data: {list(self.bu_data.keys())}")
            for key, value in self.bu_data.items():
                logger.debug(f"  БУ {key}: ключи = {list(value.keys())}")

            if bu_num in self.bu_data:
                data = self.bu_data[bu_num]
                logger.debug(f"Найдены данные для БУ №{bu_num}: {list(data.keys())}")
                
                has_amp = 'amp_data' in data
                has_fv = 'fv_data' in data
                has_lz = 'lz_data' in data

                self.update_table_headers_for_bu(has_fv)

                if has_fv:
                    logger.debug(f"Отрисовка данных ФВ для БУ №{bu_num} из bu_data")
                    self._update_table_from_fv_data(data['fv_data'])
                elif has_amp:
                    logger.debug(f"Отрисовка данных амплитуды для БУ №{bu_num} из bu_data")
                    self.update_table_from_amp_data(data['amp_data'])
                else:
                    logger.debug(f"Нет данных для БУ №{bu_num}, очищаем таблицу")
                    self._clear_results_table()

                if has_lz:
                    logger.debug(f"Отрисовка данных ЛЗ для БУ №{bu_num} из bu_data")
                    self._update_delay_table_from_lz_data(data['lz_data'])
                else:
                    self._clear_delay_table()
            else:
                logger.debug(f"Данные для БУ №{bu_num} не найдены в bu_data, очищаем таблицу")
                self._clear_results_table()
                self._clear_delay_table()

    @QtCore.pyqtSlot(int)
    def on_bu_completed(self, bu_num: int):
        """Обработчик завершения измерения БУ - переключает на следующий БУ"""
        try:
            if not hasattr(self, '_current_measurement_bu_list') or not self._current_measurement_bu_list:
                return

            if bu_num not in self._current_measurement_bu_list:
                return
            
            current_index = self._current_measurement_bu_list.index(bu_num)

            if current_index < len(self._current_measurement_bu_list) - 1:
                next_bu = self._current_measurement_bu_list[current_index + 1]
                logger.debug(f"Измерение БУ №{bu_num} завершено, переключаемся на БУ №{next_bu}")

                index = self.bu_combo.findData(next_bu)
                if index >= 0:
                    QtCore.QTimer.singleShot(0, lambda bu=next_bu: self._switch_to_bu(bu))
        except Exception as e:
            logger.error(f"Ошибка при переключении на следующий БУ: {e}")

