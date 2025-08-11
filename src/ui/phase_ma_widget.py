from PyQt5 import QtWidgets, QtCore, QtGui
from PyQt5.QtGui import QTextCursor
from PyQt5.QtWidgets import QMessageBox, QStyle
from PyQt5.QtCore import QSize
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

from ui.pna_file_dialog import PnaFileDialog


class AddCoordinateSystemDialog(QtWidgets.QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle('Добавить систему координат')
        self.setModal(True)
        self.setFixedSize(350, 200)
        
        layout = QtWidgets.QVBoxLayout(self)
        layout.setSpacing(15)
        layout.setContentsMargins(20, 20, 20, 20)
        
        # Поля ввода
        form_layout = QtWidgets.QFormLayout()
        form_layout.setSpacing(10)
        
        self.name_edit = QtWidgets.QLineEdit()
        self.name_edit.setPlaceholderText('Введите название системы координат')
        form_layout.addRow('Название:', self.name_edit)
        
        self.x_offset_spinbox = QtWidgets.QDoubleSpinBox()
        self.x_offset_spinbox.setRange(-9999.0, 9999.0)
        self.x_offset_spinbox.setDecimals(2)
        self.x_offset_spinbox.setSuffix(' см')
        self.x_offset_spinbox.setValue(0.0)
        form_layout.addRow('Смещение X:', self.x_offset_spinbox)
        
        self.y_offset_spinbox = QtWidgets.QDoubleSpinBox()
        self.y_offset_spinbox.setRange(-9999.0, 9999.0)
        self.y_offset_spinbox.setDecimals(2)
        self.y_offset_spinbox.setSuffix(' см')
        self.y_offset_spinbox.setValue(0.0)
        form_layout.addRow('Смещение Y:', self.y_offset_spinbox)
        
        layout.addLayout(form_layout)
        
        # Кнопки
        buttons = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        
        # Валидация при изменении текста
        self.name_edit.textChanged.connect(self.validate_input)
        self.validate_input()
        
    def validate_input(self):
        """Проверяет корректность введенных данных"""
        name = self.name_edit.text().strip()
        ok_button = self.findChild(QtWidgets.QDialogButtonBox).button(QtWidgets.QDialogButtonBox.Ok)
        ok_button.setEnabled(len(name) > 0)
        
    def get_values(self):
        """Возвращает введенные значения"""
        return (
            self.name_edit.text().strip(),
            self.x_offset_spinbox.value(),
            self.y_offset_spinbox.value()
        )


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
        
        self.param_tabs.addTab(self.ma_tab, 'MA')
        
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
        self.param_tabs.addTab(self.pna_tab, 'PNA')
        
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
        
        self.param_tabs.addTab(self.meas_tab, 'Meas')
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

        self.amp_plot = pg.PlotWidget(title="Амплитуда (2D)")
        self.amp_plot.setBackground('w')
        self.amp_plot.showGrid(x=True, y=True, alpha=0.3)
        self.amp_img_item = pg.ImageItem()
        self.amp_plot.addItem(self.amp_img_item)

        self.phase_plot = pg.PlotWidget(title="Фаза (2D)")
        self.phase_plot.setBackground('w')
        self.phase_plot.showGrid(x=True, y=True, alpha=0.3)
        self.phase_img_item = pg.ImageItem()
        self.phase_plot.addItem(self.phase_img_item)
        
        self.plot_tabs.addTab(self.amp_plot, "Амплитуда")
        self.plot_tabs.addTab(self.phase_plot, "Фаза")
        self.right_layout.addWidget(self.plot_tabs, stretch=5)

        self.console = QtWidgets.QTextEdit()
        self.console.setReadOnly(True)

        self.console.setFixedHeight(200)
        self.right_layout.addWidget(self.console, stretch=1)

        self.log_handler = QTextEditLogHandler(self.console)
        logger.add(self.log_handler, format="{time:HH:mm:ss} | {level} | {message}")

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

        self.ma_connect_btn.clicked.connect(self.connect_ma)
        self.pna_connect_btn.clicked.connect(self.connect_pna)
        self.psn_connect_btn.clicked.connect(self.connect_psn)
        self.apply_btn.clicked.connect(self.apply_params)
        self.start_btn.clicked.connect(self.start_phase_meas)
        self.stop_btn.clicked.connect(self.stop_phase_meas)
        self.pause_btn.clicked.connect(self.pause_phase_meas)

        self.set_buttons_enabled(True)
        self.device_settings = {}
        self.pna_settings = {}

        self.update_coord_buttons_state()
        

        self.set_button_connection_state(self.pna_connect_btn, False)
        self.set_button_connection_state(self.psn_connect_btn, False)
        self.set_button_connection_state(self.ma_connect_btn, False)


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
            if self.psn and self.device_settings:
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
                    logger.info(f'Параметры PSN успешно применены перед измерением (смещения: x={x_offset}, y={y_offset})')
                except Exception as e:
                    logger.error(f'Ошибка применения параметров PSN перед измерением: {e}')


            if self.pna and self.pna_settings:
                try:
                    self.pna.preset()
                    if self.pna_settings.get('settings_file'):
                        self.pna.load_settings_file(self.pna_settings.get('settings_file'))
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
            
            chanel = Channel.Receiver if self.channel_combo.currentText() == 'Приемник' else Channel.Transmitter
            direction = Direction.Horizontal if self.direction_combo.currentText() == 'Горизонтальная' else Direction.Vertical
            logger.info(f'Используем канал: {chanel.value}, поляризация: {direction.value}')
            
            def point_callback(i, j, x, y, amp, phase):
                self.amp_field[i, j] = amp
                self.phase_field[i, j] = phase
                # Используем сигнал вместо invokeMethod
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

        amp_cmap = ColorMap(pos=[-10, 0, 10], color=[(0, 0, 255), (0, 255, 0), (255, 0, 0)])
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


    def set_button_connection_state(self, button: QtWidgets.QPushButton, connected: bool):
        """Устанавливает состояние подключения кнопки"""
        if connected:
            # Зеленый фон для подключенного состояния
            button.setStyleSheet("QPushButton { background-color: #28a745; color: white; }")
        else:
            # Красный фон для отключенного состояния
            button.setStyleSheet("QPushButton { background-color: #dc3545; color: white; }")

    def connect_ma(self):
        """Подключает/отключает МА"""
        if self.ma and self.ma.connection:
            try:
                self.ma.disconnect()
                self.ma = None
                self.ma_connect_btn.setText('МА')  # Восстанавливаем исходный текст
                self.set_button_connection_state(self.ma_connect_btn, False)
                logger.info('МА успешно отключен')
                return
            except Exception as e:
                self.show_error_message("Ошибка отключения МА", f"Не удалось отключить МА: {str(e)}")
                return

        com_port = self.device_settings.get('ma_com_port', '')
        mode = self.device_settings.get('ma_mode', 0)

        # В реальном режиме проверяем, что COM-порт задан
        if mode == 0 and (not com_port or com_port == 'Тестовый'):
            self.show_error_message("Ошибка настроек", "COM-порт не выбран. Откройте настройки и выберите COM-порт.")
            return

        logger.info(f'Попытка подключения к МА через {com_port if mode == 0 else "тестовый режим"}, режим: {"реальный" if mode == 0 else "тестовый"}')

        try:
            self.ma = MA(com_port=com_port, mode=mode)
            self.ma.connect()
            if self.ma.bu_addr:
                self.ma_connect_btn.setText(f'МА №{self.ma.bu_addr}')
            self.set_button_connection_state(self.ma_connect_btn, True)
            logger.info(f'МА успешно подключен {"" if mode == 0 else "(тестовый режим)"}')
        except Exception as e:
            self.ma = None
            self.set_button_connection_state(self.ma_connect_btn, False)
            self.show_error_message("Ошибка подключения МА", f"Не удалось подключиться к МА: {str(e)}")

    def connect_pna(self):
        if self.pna and self.pna.connection:
            try:
                self.pna.disconnect()
                self.pna = None
                self.set_button_connection_state(self.pna_connect_btn, False)
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
            self.set_button_connection_state(self.pna_connect_btn, True)
            logger.info(f'PNA успешно подключен {"" if mode == 0 else "(тестовый режим)"}')
            self.update_pna_settings_files()
        except Exception as e:
            self.pna = None
            self.set_button_connection_state(self.pna_connect_btn, False)
            logger.error(f'Ошибка подключения PNA: {e}')

    def connect_psn(self):
        if self.psn and self.psn.connection:
            try:
                self.psn.disconnect()
                self.psn = None
                self.set_button_connection_state(self.psn_connect_btn, False)
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
            self.set_button_connection_state(self.psn_connect_btn, True)
            logger.info(f'PSN успешно подключен {"" if mode == 0 else "(тестовый режим)"}')
        except Exception as e:
            self.psn = None
            self.set_button_connection_state(self.psn_connect_btn, False)
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

    def add_coordinate_system(self):
        """Открывает диалог для добавления новой системы координат"""
        dialog = AddCoordinateSystemDialog(self)
        
        if dialog.exec_() == QtWidgets.QDialog.Accepted:
            name, x_offset, y_offset = dialog.get_values()
            
            # Добавляем систему координат через менеджер
            if self.coord_system_manager.add_system(name, x_offset, y_offset):
                # Обновляем список в комбобоксе
                current_text = self.coord_system_combo.currentText()
                self.coord_system_combo.clear()
                self.coord_system_combo.addItems(self.coord_system_manager.get_system_names())
                
                # Выбираем только что добавленную систему
                index = self.coord_system_combo.findText(name)
                if index >= 0:
                    self.coord_system_combo.setCurrentIndex(index)
                
                # Обновляем состояние кнопок
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
        
        # Проверяем количество систем координат
        if len(self.coord_system_manager.get_system_names()) <= 1:
            self.show_error_message("Ошибка", "Нельзя удалить последнюю систему координат")
            return
        
        # Запрашиваем подтверждение
        reply = QMessageBox.question(
            self, 
            'Подтверждение удаления',
            f'Вы уверены, что хотите удалить систему координат "{current_name}"?',
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        
        if reply == QMessageBox.Yes:
            # Удаляем систему через менеджер
            if self.coord_system_manager.remove_system(current_name):
                # Обновляем список в комбобоксе
                self.coord_system_combo.clear()
                self.coord_system_combo.addItems(self.coord_system_manager.get_system_names())
                
                # Выбираем первую доступную систему
                if self.coord_system_combo.count() > 0:
                    self.coord_system_combo.setCurrentIndex(0)
                
                # Обновляем состояние кнопок
                self.update_coord_buttons_state()
                
                self.show_info_message("Успех", f"Система координат '{current_name}' успешно удалена")
            else:
                self.show_error_message("Ошибка", "Не удалось удалить систему координат")

    def update_coord_buttons_state(self):
        """Обновляет состояние кнопок управления системами координат"""
        # Кнопка удаления активна только если есть больше одной системы координат
        can_remove = len(self.coord_system_manager.get_system_names()) > 1
        self.remove_coord_system_btn.setEnabled(can_remove)

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

        except Exception as e:
            logger.error(f'Ошибка при применении настроек к интерфейсу: {e}') 