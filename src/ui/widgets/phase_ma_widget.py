from PyQt5 import QtWidgets, QtCore, QtGui
from PyQt5.QtGui import QTextCursor
from PyQt5.QtWidgets import QMessageBox, QStyle
from PyQt5.QtCore import QSize
from loguru import logger
import os
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

from ui.dialogs.pna_file_dialog import PnaFileDialog
from ui.widgets.base_measurement_widget import BaseMeasurementWidget, QTextEditLogHandler
from ui.dialogs.add_coord_syst_dialog import AddCoordinateSystemDialog




class PhaseMaWidget(BaseMeasurementWidget):
    update_gui_signal = QtCore.pyqtSignal(int, int, float, float)
    
    def __init__(self):
        super().__init__()

        self.update_gui_signal.connect(self.on_measurement_update)
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

        ma_widget = QtWidgets.QWidget()
        ma_layout = QtWidgets.QHBoxLayout(ma_widget)
        ma_layout.setContentsMargins(0, 0, 0, 0)
        self.ma_connect_btn = QtWidgets.QPushButton('МА')
        self.ma_connect_btn.setMinimumHeight(40)

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
        self.amp_img_item = pg.ImageItem()
        self.amp_plot.addItem(self.amp_img_item)

        # Фаза: график + интерактивная легенда справа
        self.phase_plot = pg.PlotWidget(title="Фаза (2D)")
        self.phase_plot.setBackground('w')
        self.phase_plot.showGrid(x=True, y=True, alpha=0.3)
        self.phase_img_item = pg.ImageItem()
        self.phase_plot.addItem(self.phase_img_item)

        self._amp_cmap = ColorMap(pos=[0.0, 1.0], color=[(255, 0, 0), (0, 255, 0)])
        self._phase_cmap = ColorMap(
            pos=[0.0, 0.2, 0.4, 0.6, 0.8, 1.0],
            color=[(0, 0, 255), (0, 255, 255), (0, 255, 0), (255, 255, 0), (255, 165, 0), (255, 0, 0)]
        )
        self._amp_levels = (-10.0, 5.0)
        self._phase_levels = (-180.0, 180.0)

        self.amp_cbar = pg.ColorBarItem(values=self._amp_levels, colorMap=self._amp_cmap, orientation='v', width=14)
        self.amp_cbar.setImageItem(self.amp_img_item, insert_in=self.amp_plot.getPlotItem())

        self.phase_cbar = pg.ColorBarItem(values=self._phase_levels, colorMap=self._phase_cmap, orientation='v', width=14)
        self.phase_cbar.setImageItem(self.phase_img_item, insert_in=self.phase_plot.getPlotItem())

        self.amp_hover_label = pg.TextItem(color=(0, 0, 0), anchor=(0.5, 0.5))
        self.phase_hover_label = pg.TextItem(color=(0, 0, 0), anchor=(0.5, 0.5))
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
        
        self.plot_tabs.addTab(self.amp_plot, "Амплитуда")
        self.plot_tabs.addTab(self.phase_plot, "Фаза")
        self.right_layout.addWidget(self.plot_tabs, stretch=5)

        self.console = QtWidgets.QTextEdit()
        self.console.setReadOnly(True)

        self.console.setFixedHeight(200)
        self.right_layout.addWidget(self.console, stretch=1)

        self.log_handler = QTextEditLogHandler(self.console)
        logger.add(self.log_handler, format="{time:HH:mm:ss} | {level} | {message}")

        self._meas_thread = None
        
        self.amp_field = np.full((4,8), np.nan)
        self.phase_field = np.full((4,8), np.nan)
        self.x_cords = [-42, -14, 14, 42]
        self.y_cords = [7.7, 5.5, 3.3, 1.1, -1.1, -3.3, -5.5, -7.7]

        self.ma_connect_btn.clicked.connect(self.connect_ma)
        self.pna_connect_btn.clicked.connect(self.connect_pna)
        self.psn_connect_btn.clicked.connect(self.connect_psn)
        self.apply_btn.clicked.connect(self.apply_params)
        self.start_btn.clicked.connect(self.start_phase_meas)
        self.stop_btn.clicked.connect(self.stop_phase_meas)
        
        self.pause_btn.clicked.connect(self.pause_phase_meas)

        self.set_buttons_enabled(True)
        self.pna_settings = {}

        self.update_coord_buttons_state()
        

        self.set_button_connection_state(self.pna_connect_btn, False)
        self.set_button_connection_state(self.psn_connect_btn, False)
        self.set_button_connection_state(self.ma_connect_btn, False)

        # Персистентные настройки UI
        self._ui_settings = QtCore.QSettings('PULSAR', 'PhaseMA_UI')
        self.load_ui_settings()


    def update_pna_settings_files(self):
        """Обновляет список файлов настроек PNA в ComboBox"""
        if not self.pna or not self.pna.connection:
            return
        try:
            files = self.pna.get_files_in_dir(folder='C:\\Users\\Public\\Documents\\Network Analyzer\\')
            csa_files = [f for f in files if f.lower().endswith('.csa')]
            self.settings_file_combo.clear()
            self.settings_file_combo.addItems(csa_files)
            logger.info(f'Список файлов настроек PNA обновлен: {len(csa_files)} файлов')
        except Exception as e:
            logger.error(f'Ошибка при получении списка файлов настроек PNA: {e}')

    def set_buttons_enabled(self, enabled: bool):
        self.ma_connect_btn.setEnabled(enabled)
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
        if not (self.ma and self.pna and self.psn):
            logger.error('Сначала подключите все устройства!')
            return

        self.set_buttons_enabled(False)
        self._stop_flag.clear()
        self.amp_field = np.full((4,8), np.nan)
        self.phase_field = np.full((4,8), np.nan)

        self.amp_plot.clear()
        self.phase_plot.clear()
        self.amp_plot.addItem(self.amp_img_item)
        self.phase_plot.addItem(self.phase_img_item)
        try:
            self.amp_cbar.setImageItem(self.amp_img_item, insert_in=self.amp_plot.getPlotItem())
        except Exception:
            pass
        try:
            self.phase_cbar.setImageItem(self.phase_img_item, insert_in=self.phase_plot.getPlotItem())
        except Exception:
            pass

        self.amp_plot.addItem(self.amp_hover_label)
        self.phase_plot.addItem(self.phase_hover_label)
        self.apply_params()
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
        logger.info('Начало выполнения процесса фазировки МА')
        try:
            # Настройка сканера
            self.setup_scanner_common()


            # Настройка PNA
            self.setup_pna_common()
            
            chanel = Channel.Receiver if self.channel_combo.currentText() == 'Приемник' else Channel.Transmitter
            direction = Direction.Horizontal if self.direction_combo.currentText() == 'Горизонтальная' else Direction.Vertical
            logger.info(f'Используем канал: {chanel.value}, поляризация: {direction.value}')
            
            def point_callback(i, j, x, y, amp, phase):
                self.amp_field[i, j] = amp
                self.phase_field[i, j] = phase

                self.update_gui_signal.emit(i, j, amp, phase)
            
            phase_meas = PhaseMaMeas(
                ma=self.ma,
                psn=self.psn,
                pna=self.pna,
                point_callback=point_callback,
                stop_flag=self._stop_flag
            )
            logger.info('Запуск фазировки...')
            phase_meas.start(chanel=chanel, direction=direction)
            logger.info('Фазировка завершена')
        except Exception as e:
            logger.error(f'Ошибка фазировки: {e}')
        finally:
            self.set_buttons_enabled(True)

    def _on_mouse_moved_amp(self, pos):
        self._handle_mouse_move(pos, self.amp_plot, self.amp_hover_label, self.amp_field)

    def _on_mouse_moved_phase(self, pos):
        self._handle_mouse_move(pos, self.phase_plot, self.phase_hover_label, self.phase_field)

    def _handle_mouse_move(self, pos, plot_widget: pg.PlotWidget, label: pg.TextItem, data_field: np.ndarray):
        try:
            if not hasattr(self, '_rect'):
                label.hide()
                return
            vb = plot_widget.getViewBox()
            if vb is None:
                label.hide()
                return
            point = vb.mapSceneToView(pos)
            x, y = float(point.x()), float(point.y())
            rect: QtCore.QRectF = self._rect
            if not rect.contains(x, y):
                label.hide()
                return

            i = int((x - rect.left()) / self._dx)
            j_from_top = int((y - rect.top()) / self._dy)
            i = max(0, min(self._nx - 1, i))
            j_from_top = max(0, min(self._ny - 1, j_from_top))


            cx = rect.left() + (i + 0.5) * self._dx
            cy = rect.top() + (j_from_top + 0.5) * self._dy


            x_val = self._x_positions[i]
            y_sorted_desc = np.sort(self._y_positions)[::-1]
            y_val = y_sorted_desc[j_from_top]


            j_data = (self._ny - 1 - j_from_top) if self._y_is_desc else j_from_top
            if 0 <= i < data_field.shape[0] and 0 <= j_data < data_field.shape[1]:
                value = float(data_field[i, j_data])
            else:
                value = float('nan')

            label.setText(f"x={x_val:.2f}, y={y_val:.2f}\nval={value if np.isfinite(value) else 'NaN'}")
            label.setPos(cx, cy)
            label.show()
        except Exception:
            label.hide()

    @QtCore.pyqtSlot(int, int, float, float)
    def on_measurement_update(self, i, j, amp, phase):
        """Слот для обновления графика при получении новых данных"""
        self.amp_field[i, j] = amp
        self.phase_field[i, j] = phase
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
    @QtCore.pyqtSlot()
    def update_heatmaps(self):
        x_positions = np.asarray(self.x_cords, dtype=float)
        y_positions = np.asarray(self.y_cords, dtype=float)
        if x_positions.size < 2 or y_positions.size < 2:
            return
        nx, ny = x_positions.size, y_positions.size
        dx = float(np.mean(np.diff(x_positions)))
        dy = float(np.mean(np.abs(np.diff(y_positions))))

        y_is_desc = bool(y_positions[0] > y_positions[-1])
        amp_data = np.flip(self.amp_field, axis=1) if y_is_desc else self.amp_field
        phase_data = np.flip(self.phase_field, axis=1) if y_is_desc else self.phase_field

        self.amp_img_item.setImage(amp_data, axisOrder='col-major', autoLevels=False)
        self.amp_img_item.setColorMap(self._amp_cmap)
        if hasattr(self, 'amp_cbar'):
            try:
                self.amp_cbar.setLevels(self._amp_levels)
                self.amp_cbar.setColorMap(self._amp_cmap)
            except Exception:
                pass

        self.phase_img_item.setImage(phase_data, axisOrder='col-major', autoLevels=False)
        self.phase_img_item.setColorMap(self._phase_cmap)
        if hasattr(self, 'phase_cbar'):
            try:
                self.phase_cbar.setLevels(self._phase_levels)
                self.phase_cbar.setColorMap(self._phase_cmap)
            except Exception:
                pass

        x0 = float(x_positions.min() - dx / 2.0)
        y0 = float(y_positions.min() - dy / 2.0)
        width = dx * nx
        height = dy * ny
        rect = QtCore.QRectF(x0, y0, width, height)
        self.amp_img_item.setRect(rect)
        self.phase_img_item.setRect(rect)

        self._rect = rect
        self._x_positions = x_positions
        self._y_positions = y_positions
        self._dx, self._dy = dx, dy
        self._nx, self._ny = nx, ny

        self._y_is_desc = bool(y_positions[0] > y_positions[-1])

        if hasattr(self, 'amp_hover_label') and self.amp_hover_label not in self.amp_plot.listDataItems():
            self.amp_plot.addItem(self.amp_hover_label)
        if hasattr(self, 'phase_hover_label') and self.phase_hover_label not in self.phase_plot.listDataItems():
            self.phase_plot.addItem(self.phase_hover_label)

        self.amp_plot.setRange(xRange=(x_positions.min() - dx, x_positions.max() + dx),
                               yRange=(y_positions.min() - dy, y_positions.max() + dy), padding=0)
        self.phase_plot.setRange(xRange=(x_positions.min() - dx, x_positions.max() + dx),
                                 yRange=(y_positions.min() - dy, y_positions.max() + dy), padding=0)

        self.amp_plot.setAspectLocked(False)
        self.phase_plot.setAspectLocked(False)


    