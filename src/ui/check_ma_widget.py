from PyQt5 import QtWidgets, QtCore, QtGui
from PyQt5.QtGui import QTextCursor
from PyQt5.QtWidgets import QMessageBox
from loguru import logger
import threading
import numpy as np
from core.devices.ma import MA
from core.devices.pna import PNA
from core.devices.psn import PSN
from core.measurements.check.check_ma import CheckMA
from core.common.enums import Channel, Direction, PpmState
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

class PpmRect(QtWidgets.QGraphicsRectItem):
    def __init__(self, ppm_num, parent_widget, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.ppm_num = ppm_num
        self.parent_widget = parent_widget
        self.setAcceptHoverEvents(True)
        self.setFlag(QtWidgets.QGraphicsItem.ItemIsSelectable, True)
        self.setBrush(QtGui.QBrush(QtGui.QColor("#f0f0f0")))
        self.setPen(QtGui.QPen(QtGui.QColor("#ccc")))
        self.text = None
        self.status = None

    def set_status(self, status):
        color = "#f0f0f0"
        if status == "ok":
            color = "#2ecc40"
        elif status == "fail":
            color = "#e74c3c"
        self.setBrush(QtGui.QBrush(QtGui.QColor(color)))
        self.status = status

    def mousePressEvent(self, event):
        # Обрабатываем только левый клик для выбора
        if event.button() == QtCore.Qt.LeftButton:
            self.setSelected(True)
        super().mousePressEvent(event)

class PpmFieldView(QtWidgets.QGraphicsView):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setScene(QtWidgets.QGraphicsScene(self))
        self.rects = {}
        self.texts = {}
        self.setRenderHint(QtGui.QPainter.Antialiasing)
        self.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        self.parent_widget = parent  # Сохраняем ссылку на CheckMaWidget
        self.create_rects()
        
        # Включаем контекстное меню
        self.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
        self.customContextMenuRequested.connect(self.show_context_menu)

    def create_rects(self):
        self.scene().clear()
        self.rects.clear()
        self.texts.clear()
        for col in range(4):
            for row in range(8):
                ppm_num = col * 8 + row + 1
                rect = PpmRect(ppm_num, self.parent_widget, 0, 0, 1, 1)
                self.scene().addItem(rect)
                self.rects[ppm_num] = rect
                text = self.scene().addText(f"ППМ {ppm_num}", QtGui.QFont("Arial", 8))
                text.setDefaultTextColor(QtGui.QColor("black"))
                self.texts[ppm_num] = text
        self.update_layout()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.update_layout()
        self.fitInView(self.sceneRect(), QtCore.Qt.KeepAspectRatio)

    def update_layout(self):
        w = self.viewport().width() / 4
        h = self.viewport().height() / 8
        for col in range(4):
            for row in range(8):
                ppm_num = col * 8 + row + 1
                rect = self.rects[ppm_num]
                rect.setRect(col*w, row*h, w, h)
                text = self.texts[ppm_num]
                text.setPos(col*w+2, row*h+h/3)
        self.scene().setSceneRect(0, 0, 4*w, 8*h)

    def update_ppm(self, ppm_num, status):
        if ppm_num in self.rects:
            self.rects[ppm_num].set_status(status)
    
    def get_ppm_at_position(self, pos):
        """Определяет номер ППМ по позиции клика"""
        w = self.viewport().width() / 4
        h = self.viewport().height() / 8
        
        col = int(pos.x() / w)
        row = int(pos.y() / h)
        
        # Проверяем границы
        if 0 <= col < 4 and 0 <= row < 8:
            ppm_num = col * 8 + row + 1
            return ppm_num
        return None
    
    def show_context_menu(self, pos):
        """Показывает контекстное меню для ППМ в указанной позиции"""
        ppm_num = self.get_ppm_at_position(pos)
        if ppm_num is not None and self.parent_widget is not None:
            # Выбираем соответствующий элемент
            if ppm_num in self.rects:
                self.rects[ppm_num].setSelected(True)
            # Показываем информацию
            self.parent_widget.show_ppm_details_graphics(ppm_num, self.mapToGlobal(pos))

class CheckMaWidget(QtWidgets.QWidget):
    # Сигнал для обновления таблицы в реальном времени
    update_table_signal = QtCore.pyqtSignal(int, bool, float, float, list)
    
    def __init__(self):
        super().__init__()

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
        self.pna_connect_btn.setStyleSheet(self.btn_style_disconnected)
        pna_layout.addWidget(self.pna_connect_btn)
        self.connect_layout.addWidget(pna_widget)

        psn_widget = QtWidgets.QWidget()
        psn_layout = QtWidgets.QHBoxLayout(psn_widget)
        psn_layout.setContentsMargins(0, 0, 0, 0)
        self.psn_connect_btn = QtWidgets.QPushButton('Сканер')
        self.psn_connect_btn.setMinimumHeight(40)
        self.psn_connect_btn.setStyleSheet(self.btn_style_disconnected)
        psn_layout.addWidget(self.psn_connect_btn)
        self.connect_layout.addWidget(psn_widget)

        ma_widget = QtWidgets.QWidget()
        ma_layout = QtWidgets.QHBoxLayout(ma_widget)
        ma_layout.setContentsMargins(0, 0, 0, 0)
        self.ma_connect_btn = QtWidgets.QPushButton('МА')
        self.ma_connect_btn.setMinimumHeight(40)
        self.ma_connect_btn.setStyleSheet(self.btn_style_disconnected)
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
        self.pna_tab_layout.addRow('Входная мощность:',  self.pna_power)

        only_float = QtGui.QDoubleValidator()
        only_float.setDecimals(2)
        self.pna_start_freq = QtWidgets.QLineEdit()
        self.pna_start_freq.setText('9300')
        self.pna_start_freq.setValidator(only_float)
        self.pna_tab_layout.addRow('Нач. частота (МГц):', self.pna_start_freq)

        self.pna_stop_freq = QtWidgets.QLineEdit()
        self.pna_stop_freq.setText('9300')
        self.pna_stop_freq.setValidator(only_float)
        self.pna_tab_layout.addRow('Кон. частота (МГц):', self.pna_stop_freq)

        self.pna_number_of_points = QtWidgets.QComboBox()
        self.pna_number_of_points.addItems(['3', '11', '101', '201'])
        self.pna_tab_layout.addRow('Кол-во точек:', self.pna_number_of_points)

        self.pna_tab_layout.addRow('Файл настроек:', QtWidgets.QLineEdit())
        self.param_tabs.addTab(self.pna_tab, 'PNA')
        
        # Meas tab
        self.meas_tab = QtWidgets.QWidget()
        self.meas_tab_layout = QtWidgets.QFormLayout(self.meas_tab)

        self.coord_system_combo = QtWidgets.QComboBox()
        self.coord_system_combo.addItems(self.coord_system_manager.get_system_names())
        self.meas_tab_layout.addRow('Система координат:', self.coord_system_combo)
        
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

        self.results_table = QtWidgets.QTableWidget()
        self.results_table.setColumnCount(12)
        self.results_table.setHorizontalHeaderLabels([
            'ППМ', 'Амплитуда', 'Фаза', 'Статус амплитуды', 'Статус фазы',
            'Дельта ФВ', 'ФВ 5,625', 'ФВ 11,25', 'ФВ 22,5', 'ФВ 45', 'ФВ 90', 'ФВ 180'])
        self.results_table.setRowCount(32)
        self.results_table.horizontalHeader().setSectionResizeMode(QtWidgets.QHeaderView.Stretch)
        self.results_table.verticalHeader().setSectionResizeMode(QtWidgets.QHeaderView.Stretch)
        self.results_table.verticalHeader().setVisible(False)
        for row in range(32):
            self.results_table.setItem(row, 0, QtWidgets.QTableWidgetItem(f"{row+1}"))
            for col in range(1, 12):
                self.results_table.setItem(row, col, QtWidgets.QTableWidgetItem(""))

        # --- 2D поле ---
        self.ppm_field_view = PpmFieldView(self)

        # --- Tabs ---
        self.view_tabs = QtWidgets.QTabWidget()
        self.view_tabs.addTab(self.results_table, "Таблица")
        self.view_tabs.addTab(self.ppm_field_view, "2D поле")
        self.right_layout.addWidget(self.view_tabs, stretch=2)

        self.console = QtWidgets.QTextEdit()
        self.console.setReadOnly(True)
        self.console.setStyleSheet('background: #fff; color: #000; font-family: "PT Mono";')
        self.console.setFixedHeight(200)
        self.right_layout.addWidget(self.console, stretch=1)

        self.log_handler = QTextEditLogHandler(self.console)
        logger.add(self.log_handler, format="{time:HH:mm:ss} | {level} | {message}")

        self.ma = None
        self.pna = None
        self.psn = None
        self._check_thread = None
        self._stop_flag = threading.Event()
        self._pause_flag = threading.Event()

        self.ma_connect_btn.clicked.connect(self.connect_ma)
        self.pna_connect_btn.clicked.connect(self.connect_pna)
        self.psn_connect_btn.clicked.connect(self.connect_psn)
        self.apply_btn.clicked.connect(self.apply_params)
        self.start_btn.clicked.connect(self.start_check)
        self.stop_btn.clicked.connect(self.stop_check)
        self.pause_btn.clicked.connect(self.pause_check)
        
        # Подключаем сигнал для обновления таблицы
        self.update_table_signal.connect(self.update_table_row)

        self.set_buttons_enabled(True)
        self.device_settings = {}
        
        # Словарь для хранения данных ППМ
        self.ppm_data = {}

    def show_ppm_details(self, button: QtWidgets.QPushButton, ppm_num: int):
        """Показывает детальную информацию о ППМ в контекстном меню"""
        if ppm_num in self.ppm_data:
            data = self.ppm_data[ppm_num]
            menu = QtWidgets.QMenu()
            
            # Создаем детальную информацию
            details = f"ППМ {ppm_num}\n"
            details += f"Результат: {'OK' if data['result'] else 'FAIL'}\n"
            details += f"Амплитуда: {data['amp']:.2f} дБ\n"
            details += f"Фаза: {data['phase']:.1f}°\n"
            
            if data['fv_data'] and len(data['fv_data']) > 0:
                details += "\nЗначения ФВ:\n"
                for i, value in enumerate(data['fv_data']):
                    if not np.isnan(value):
                        details += f"  {value:.1f}°\n"
            
            # Создаем действие с деталями
            action = menu.addAction(details)
            action.setEnabled(False)  # Делаем неактивным, чтобы показать как текст
            
            # Показываем меню
            menu.exec_(button.mapToGlobal(QtCore.QPoint(0, 0)))
        else:
            # Если данных нет, показываем простое сообщение
            menu = QtWidgets.QMenu()
            action = menu.addAction(f"ППМ {ppm_num} - данные не готовы")
            action.setEnabled(False)
            menu.exec_(button.mapToGlobal(QtCore.QPoint(0, 0)))

    @QtCore.pyqtSlot(int, bool, float, float, list)
    def update_table_row(self, ppm_num: int, result: bool, amp: float, phase: float, fv_data: list):
        """Обновляет строку таблицы и 2D вид с результатами измерения"""
        try:
            # Сохраняем данные ППМ
            self.ppm_data[ppm_num] = {
                'result': result,
                'amp': amp,
                'phase': phase,
                'fv_data': fv_data
            }
            
            # Обновляем таблицу
            row = ppm_num - 1

            self.results_table.setItem(row, 0, QtWidgets.QTableWidgetItem(str(ppm_num)))

            if np.isnan(amp) or np.isnan(phase):
                self.results_table.setItem(row, 1, QtWidgets.QTableWidgetItem(""))
                self.results_table.setItem(row, 2, QtWidgets.QTableWidgetItem(""))
            else:
                self.results_table.setItem(row, 1, QtWidgets.QTableWidgetItem(f"{amp:.2f}"))
                self.results_table.setItem(row, 2, QtWidgets.QTableWidgetItem(f"{phase:.1f}"))

            # Определяем статусы амплитуды и фазы на основе критериев CheckMA
            amp_ok = True
            phase_ok = True
            
            if not np.isnan(amp):
                # Критерии амплитуды (из CheckMA)
                rx_amp_max = 4.5
                tx_amp_max = 2.5
                amp_max = rx_amp_max if self.channel_combo.currentText() == 'Приемник' else tx_amp_max
                amp_ok = -amp_max <= amp <= amp_max
            
            if not np.isnan(phase):
                # Критерии фазы (из CheckMA)
                rx_phase_diff_min, rx_phase_diff_max = 2, 12
                tx_phase_diff_min, tx_phase_diff_max = 2, 20
                
                if self.channel_combo.currentText() == 'Приемник':
                    phase_ok = rx_phase_diff_min <= phase <= rx_phase_diff_max
                else:
                    phase_ok = tx_phase_diff_min < phase < tx_phase_diff_max

            # Статус амплитуды
            amp_status = "OK" if amp_ok else "FAIL"
            amp_status_item = QtWidgets.QTableWidgetItem(amp_status)
            if amp_ok:
                amp_status_item.setBackground(QtGui.QColor("#2ecc40"))
            else:
                amp_status_item.setBackground(QtGui.QColor("#e74c3c"))
            amp_status_item.setForeground(QtGui.QColor("white"))
            self.results_table.setItem(row, 3, amp_status_item)
            
            # Статус фазы
            phase_status = "OK" if phase_ok else "FAIL"
            phase_status_item = QtWidgets.QTableWidgetItem(phase_status)
            if phase_ok:
                phase_status_item.setBackground(QtGui.QColor("#2ecc40"))
            else:
                phase_status_item.setBackground(QtGui.QColor("#e74c3c"))
            phase_status_item.setForeground(QtGui.QColor("white"))
            self.results_table.setItem(row, 4, phase_status_item)

            # Обработка данных ФВ
            if fv_data and len(fv_data) > 0:
                try:
                    # Отображаем дельту ФВ (первое значение) для всех измерений
                    if not np.isnan(fv_data[0]):
                        self.results_table.setItem(row, 5, QtWidgets.QTableWidgetItem(f"{fv_data[0]:.1f}"))
                    else:
                        self.results_table.setItem(row, 5, QtWidgets.QTableWidgetItem(""))
                    
                    # Остальные значения ФВ только для неуспешных измерений
                    if not result:
                        for i in range(1, len(fv_data)):
                            if not np.isnan(fv_data[i]):
                                self.results_table.setItem(row, i + 5, QtWidgets.QTableWidgetItem(f"{fv_data[i]:.1f}"))
                            else:
                                self.results_table.setItem(row, i + 5, QtWidgets.QTableWidgetItem(""))
                    else:
                        # Для успешных измерений очищаем остальные столбцы ФВ
                        for i in range(1, 6):
                            self.results_table.setItem(row, i + 5, QtWidgets.QTableWidgetItem(""))
                            
                except Exception as e:
                    logger.error(f'Ошибка при обновлении значений ФВ для ППМ {ppm_num}: {e}')
                    for i in range(6):
                        self.results_table.setItem(row, i + 5, QtWidgets.QTableWidgetItem(""))
            else:
                # Если данных ФВ нет, очищаем все столбцы ФВ
                for i in range(6):
                    self.results_table.setItem(row, i + 5, QtWidgets.QTableWidgetItem(""))

            # Обновляем 2D вид
            if result:
                self.ppm_field_view.update_ppm(ppm_num, "ok")
            else:
                self.ppm_field_view.update_ppm(ppm_num, "fail")

            self.results_table.viewport().update()
            QtCore.QCoreApplication.processEvents()
        except Exception as e:
            self.show_error_message("Ошибка обновления таблицы", f"Ошибка при обновлении данных ППМ {ppm_num}: {str(e)}")
            logger.error(f'Ошибка при обновлении значений ФВ для ППМ {ppm_num}: {e}')
            for i in range(6):
                self.results_table.setItem(row, i + 5, QtWidgets.QTableWidgetItem(""))

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
        self.channel = self.channel_combo.currentText()
        self.direction = self.direction_combo.currentText()
        # PNA
        self.s_param = self.pna_tab_layout.itemAt(1).widget().currentText()
        self.power = self.pna_tab_layout.itemAt(3).widget().value()
        self.freq_start = self.pna_tab_layout.itemAt(5).widget().text()
        self.freq_stop = self.pna_tab_layout.itemAt(7).widget().text()
        self.freq_points = self.pna_tab_layout.itemAt(9).widget().currentText()
        self.settings_file = self.pna_tab_layout.itemAt(11).widget().text()


        coord_system_name = self.coord_system_combo.currentText()
        self.coord_system = self.coord_system_manager.get_system_by_name(coord_system_name)
        logger.info('Параметры успешно применены')

    def start_check(self):
        """Запускает процесс проверки"""
        if not (self.ma and self.pna and self.psn):
            self.show_error_message("Ошибка", "Сначала подключите все устройства!")
            return
        
        self._stop_flag.clear()
        self._pause_flag.clear()
        self.pause_btn.setText('Пауза') # Reset pause button text
        
        self.results_table.clearContents()
        for row in range(32):
            self.results_table.setItem(row, 0, QtWidgets.QTableWidgetItem(f"{row+1}"))
            for col in range(1, 12):
                self.results_table.setItem(row, col, QtWidgets.QTableWidgetItem(""))
        
        # Очищаем данные ППМ и сбрасываем 2D вид
        self.ppm_data.clear()
        for ppm_num, button in self.ppm_field_view.rects.items():
            button.set_status('')

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
        try:
            channel = Channel.Receiver if self.channel_combo.currentText()== 'Приемник' else Channel.Transmitter
            direction = Direction.Horizontal if self.direction_combo.currentText()=='Горизонтальная' else Direction.Vertical
            logger.info(f'Используем канал: {channel.value}, поляризация: {direction.value}')

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

            # Создаем модифицированный CheckMA с callback для обновления UI
            class CheckMAWithCallback(CheckMA):
                def __init__(self, ma, psn, pna, stop_event, pause_event, callback):
                    super().__init__(ma, psn, pna, stop_event, pause_event)
                    self.callback = callback
                
                def check_ppm(self, ppm_num: int, channel: Channel, direction: Direction):
                    """Переопределяем метод для отправки результатов через callback"""
                    result, measurements = super().check_ppm(ppm_num, channel, direction)
                    amp, phase, fv_data = measurements

                    if self.callback:
                        self.callback.emit(ppm_num, result, amp, phase, fv_data)
                    
                    return result, measurements

            check = CheckMAWithCallback(
                ma=self.ma, 
                psn=self.psn, 
                pna=self.pna, 
                stop_event=self._stop_flag, 
                pause_event=self._pause_flag,
                callback=self.update_table_signal
            )

            check.start(channel=channel, direction=direction)

            if not self._stop_flag.is_set():
                logger.info('Проверка завершена успешно.')

        except Exception as e:
            self.show_error_message("Ошибка проверки", f"Произошла ошибка при выполнении проверки: {str(e)}")
            logger.error(f"Ошибка при выполнении проверки: {e}")
            try:
                self.pna.power_off()
            except Exception as e:
                logger.error(f"Ошибка при аварийном выключении PNA: {e}")
            raise
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
                self.show_error_message("Ошибка отключения МА", f"Не удалось отключить МА: {str(e)}")
                return

        com_port = self.device_settings.get('ma_com_port', '')
        mode = self.device_settings.get('ma_mode', 0)

        try:
            self.ma = MA(com_port=com_port, mode=mode)
            self.ma.connect()
            if self.ma.bu_addr:
                self.ma_connect_btn.setText(f'МА №{self.ma.bu_addr}')
            self.ma_connect_btn.setStyleSheet(self.btn_style_connected)
            logger.info(f'МА успешно подключен {"" if mode == 0 else "(тестовый режим)"}')
        except Exception as e:
            self.ma = None
            self.ma_connect_btn.setStyleSheet(self.btn_style_disconnected)
            self.show_error_message("Ошибка подключения МА", f"Не удалось подключиться к МА: {str(e)}")

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
                self.show_error_message("Ошибка отключения PNA", f"Не удалось отключить PNA: {str(e)}")
                return

        ip = self.device_settings.get('pna_ip', '')
        port = int(self.device_settings.get('pna_port', ''))
        mode = self.device_settings.get('pna_mode', 0)

        try:
            self.pna = PNA(ip=ip, port=port, mode=mode)
            self.pna.connect()
            self.pna_connect_btn.setStyleSheet(self.btn_style_connected)
            logger.info(f'PNA успешно подключен {"" if mode == 0 else "(тестовый режим)"}')
        except Exception as e:
            self.pna = None
            self.pna_connect_btn.setStyleSheet(self.btn_style_disconnected)
            self.show_error_message("Ошибка подключения PNA", f"Не удалось подключиться к PNA: {str(e)}")

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
                self.show_error_message("Ошибка отключения PSN", f"Не удалось отключить PSN: {str(e)}")
                return

        ip = self.device_settings.get('psn_ip', '')
        port = self.device_settings.get('psn_port', '')
        mode = self.device_settings.get('psn_mode', 0)

        try:
            self.psn = PSN(ip=ip, port=port, mode=mode)
            self.psn.connect()
            self.psn_connect_btn.setStyleSheet(self.btn_style_connected)
            logger.info(f'PSN успешно подключен {"" if mode == 0 else "(тестовый режим)"}')
        except Exception as e:
            self.psn = None
            self.psn_connect_btn.setStyleSheet(self.btn_style_disconnected)
            self.show_error_message("Ошибка подключения PSN", f"Не удалось подключиться к PSN: {str(e)}")

    def set_device_settings(self, settings: dict):
        """Сохраняет параметры устройств из настроек"""
        self.device_settings = settings or {} 

    def show_ppm_details_graphics(self, ppm_num, global_pos):
        if ppm_num not in self.ppm_data:
            menu = QtWidgets.QMenu()
            action = menu.addAction(f"ППМ {ppm_num} - данные не готовы")
            action.setEnabled(False)
            menu.exec_(global_pos)
            return
        
        data = self.ppm_data[ppm_num]
        menu = QtWidgets.QMenu()
        
        # Заголовок с номером ППМ и статусом
        status_text = "OK" if data['result'] else "FAIL"
        status_color = "🟢" if data['result'] else "🔴"
        header_action = menu.addAction(f"{status_color} ППМ {ppm_num} - {status_text}")
        header_action.setEnabled(False)
        menu.addSeparator()
        
        # Амплитуда
        if not np.isnan(data['amp']):
            amp_action = menu.addAction(f"Амплитуда: {data['amp']:.2f} дБ")
        else:
            amp_action = menu.addAction("Амплитуда: ---")
        amp_action.setEnabled(False)
        
        # Фаза
        if not np.isnan(data['phase']):
            phase_action = menu.addAction(f"Фаза: {data['phase']:.1f}°")
        else:
            phase_action = menu.addAction("Фаза: ---")
        phase_action.setEnabled(False)
        
        # Значения ФВ (если есть)
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
                        fv_action = menu.addAction(f"  ФВ {i+1}: {value:.1f}°")
                    else:
                        fv_action = menu.addAction(f"  ФВ {i+1}: ---")
                    fv_action.setEnabled(False)
        
        menu.exec_(global_pos) 

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