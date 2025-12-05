from PyQt5 import QtWidgets, QtCore
import pyqtgraph as pg
from loguru import logger
import threading

from core.common.enums import Channel, Direction
from ui.widgets.base_measurement_widget import BaseMeasurementWidget
from core.measurements.beam_calb_afar.beam_calb_afar import BeamAfarCalb
from config.settings_manager import get_ui_settings




class BeamCalbAfarWidget(BaseMeasurementWidget):
    """Виджет измерения лучей АФАР через калибровочный канал"""

    def __init__(self):

        super().__init__()
        self.currnet_beam = None
        self.current_bu = None
        self.freq_list = []

        self._meas_thread = None

        self._ui_settings = get_ui_settings('beam_calb_afar')


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
        ])
        self.left_layout.addWidget(connect_group)

        self.param_tabs = QtWidgets.QTabWidget()

        self.afar_tab = QtWidgets.QWidget()
        self.afar_tab_layout = QtWidgets.QFormLayout(self.afar_tab)

        self.chanel_combo = QtWidgets.QComboBox()
        self.chanel_combo.addItems(['Приемник', 'Передатчик'])
        self.afar_tab_layout.addRow('Канал: ', self.chanel_combo)

        self.direction_combo = QtWidgets.QComboBox()
        self.direction_combo.addItems(['Горизонтальная', 'Вертикальная'])
        self.afar_tab_layout.addRow('Поляризация:', self.direction_combo)

        self.param_tabs.addTab(self.afar_tab, 'АФАР')

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

        self.create_bu_selector()
        self.create_beam_selector()

        self.with_calb_checkbox = QtWidgets.QCheckBox('Применять калибровку')
        self.with_calb_checkbox.setChecked(True)

        self.meas_tab_layout.addWidget(self.with_calb_checkbox)

        self.meas_tab_layout.addStretch()

        self.param_tabs.addTab(self.meas_tab, 'Настройки измерения')

        self.left_layout.addWidget(self.param_tabs, 1)

        self.apply_btn, control_layout = self.create_control_buttons()
        if self.apply_btn:
            self.left_layout.addWidget(self.apply_btn)
        self.left_layout.addLayout(control_layout)

        self.left_layout.addStretch()

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
        self.apply_btn.clicked.connect(self.apply_params)
        self.start_btn.clicked.connect(self.start_measurement)
        self.stop_btn.clicked.connect(self.stop_measurement)
        self.pause_btn.clicked.connect(self.pause_measurement)

        self.set_buttons_enabled(True)
        self.set_button_connection_state(self.pna_connect_btn, False)
        self.set_button_connection_state(self.afar_connect_btn, False)
        self.set_button_connection_state(self.gen_connect_btn, False)

        self.pna_settings = {}
        self.sync_settings = {}

        self.load_ui_settings()


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

    def apply_params(self):
        """Сохраняет параметры из вкладок"""
        self.setup_pna_common()
        # PNA
        self.pna_settings['s_param'] = self.s_param_combo.currentText()
        self.pna_settings['power'] = self.pna_power.value()
        self.pna_settings['freq_start'] = self.pna_start_freq.value() * 10 ** 6
        self.pna_settings['freq_stop'] = self.pna_stop_freq.value() * 10 ** 6
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


        logger.info(
            f'Параметры применены. Частоты: {len(self.freq_list)} точек от {self.freq_list[0]} до {self.freq_list[-1]} МГц')

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

    @QtCore.pyqtSlot(dict)
    def on_measurement_finished(self, data):
        """Измерение завершено"""
        logger.info("Измерение завершено успешно!")
        self.measurement_data = data
        self.update_view_combos()
        self.update_plots()
        self.set_buttons_enabled(True)

    @QtCore.pyqtSlot(str)
    def on_measurement_error(self, error_msg):
        """Ошибка измерения"""
        logger.error(f"Ошибка измерения: {error_msg}")
        self.show_error_message("Ошибка измерения", error_msg)
        self.set_buttons_enabled(True)

    def save_ui_settings(self):
        """Сохраняет состояние контролов UI в QSettings (как в phase_afar_widget)"""
        s = self._ui_settings

        # AFAR
        s.setValue('channel', self.chanel_combo.currentText())
        s.setValue('direction', self.direction_combo.currentText())
        s.setValue('with_calb', self.with_calb_checkbox.isChecked())
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
        # Log level
        s.setValue('log_level', self.log_level_combo.currentText())
        s.sync()

    def load_ui_settings(self):
        """Восстанавливает состояние контролов UI из QSettings (как в phase_afar_widget)"""
        s = self._ui_settings

        # AFAR
        val = s.value('channel')
        if val:
            idx = self.chanel_combo.findText(val)
            if idx >= 0: self.chanel_combo.setCurrentIndex(idx)

        val = s.value('direction')
        if val:
            idx = self.direction_combo.findText(val)
            if idx >= 0: self.direction_combo.setCurrentIndex(idx)

        val = s.value('with_calb')
        if val is not None:
            self.with_calb_checkbox.setChecked(bool(val))

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
        # Log level
        if (v := s.value('log_level')):
            idx = self.log_level_combo.findText(v)
            if idx >= 0:
                self.log_level_combo.setCurrentIndex(idx)


    def disconnect_all_devices(self):
        """Отключить все устройства"""
        self.afar = None
        self.pna = None
        self.trigger = None
        self.set_button_connection_state(self.afar_connect_btn, False)
        self.set_button_connection_state(self.pna_connect_btn, False)
        self.set_button_connection_state(self.gen_connect_btn, False)

    def start_measurement(self):
        if not (self.afar and self.pna and self.trigger):
            self.show_error_message("Ошибка", "Сначала подключите все устройства!")
            return

        self._stop_flag.clear()
        self._pause_flag.clear()
        self.pause_btn.setText('Пауза')

        self.apply_params()
        self._meas_thread = threading.Thread(target=self._run, daemon=True)
        self._meas_thread.start()

    def _run(self):
        try:
            channel = Channel.Receiver if self.chanel_combo.currentText() == 'Приемник' else Channel.Transmitter
            direction = Direction.Horizontal if self.direction_combo.currentText() == 'Горизонтальная' else Direction.Vertical
            logger.info(f'Используем канал: {channel.value}, поляризация: {direction.value}')

            self.setup_pna_common()

            beam_calb_meas = BeamAfarCalb(
                afar=self.afar,
                pna=self.pna,
                gen=self.trigger,
                stop_event=self._stop_flag,
                pause_event=self._pause_flag,
                with_calb=self.with_calb_checkbox.isChecked(),
                beam_numbers=self.get_selected_beams(),
                bu_numbers=self.get_selected_bu_numbers())

            beam_calb_meas.period = float(self.trig_pulse_period.value()) * 1e-6
            beam_calb_meas.lead = float(self.trig_start_lead.value()) * 1e-3

            beam_calb_meas.start(chanel=channel,
                                 direction=direction,
                                 beams=self.get_selected_beams(),
                                 freq_list=self.freq_list)
        finally:
            pass


