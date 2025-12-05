from PyQt5 import QtWidgets, QtCore, QtGui
from loguru import logger
from core.devices.psn import PSN
from core.devices.ma import MA
from core.common.coordinate_system import CoordinateSystemManager
from core.common.exceptions import WrongInstrumentError, PlanarScannerError
from core.common.enums import Channel, Direction, PpmState
import time


class ManualControlWindow(QtWidgets.QMainWindow):
    """Окно ручного управления для выбора ППМ и перемещения к нему"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Ручное управление")
        self.resize(1100, 720)
        
        self.device_settings = None
        self.psn = None
        self.ma = None
        self.coord_system = None
        self.coord_manager = CoordinateSystemManager()

        # Координаты ППМ (такие же как в PhaseMaMeas)
        self.x_cords = [-42, -14, 14, 42]
        self.y_cords = [7.7, 5.5, 3.3, 1.1, -1.1, -3.3, -5.5, -7.7]
        
        self.setup_ui()
        
    def setup_ui(self):
        """Настройка интерфейса"""
        central_widget = QtWidgets.QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QtWidgets.QVBoxLayout(central_widget)
        
        # Заголовок
        title_label = QtWidgets.QLabel("Ручное управление")
        title_label.setAlignment(QtCore.Qt.AlignCenter)
        title_label.setStyleSheet("font-size: 18px; font-weight: bold; margin: 10px;")
        main_layout.addWidget(title_label)
        
        # Группа настроек
        settings_group = QtWidgets.QGroupBox("Настройки")
        settings_layout = QtWidgets.QFormLayout(settings_group)
        
        # Выбор системы координат
        self.coord_system_combo = QtWidgets.QComboBox()
        self.update_coordinate_systems()
        self.coord_system_combo.currentTextChanged.connect(self.on_coord_system_changed)
        settings_layout.addRow("Система координат:", self.coord_system_combo)

        # Выбор канала и поляризации для команд МА
        ch_dir_layout = QtWidgets.QHBoxLayout()
        self.channel_combo = QtWidgets.QComboBox()
        self.channel_combo.addItems(["Приемник", "Передатчик"])  # Receiver / Transmitter
        self.direction_combo = QtWidgets.QComboBox()
        self.direction_combo.addItems(["Горизонтальная", "Вертикальная"])  # Horizontal / Vertical
        ch_dir_layout.addWidget(QtWidgets.QLabel("Канал:"))
        ch_dir_layout.addWidget(self.channel_combo)
        ch_dir_layout.addSpacing(12)
        ch_dir_layout.addWidget(QtWidgets.QLabel("Поляризация:"))
        ch_dir_layout.addWidget(self.direction_combo)
        settings_layout.addRow("Команды МА:", ch_dir_layout)
        
        main_layout.addWidget(settings_group)
        
        # Группа выбора ППМ
        ppm_group = QtWidgets.QGroupBox("Выбор ППМ")
        ppm_layout = QtWidgets.QVBoxLayout(ppm_group)
        
        # Способ выбора ППМ
        selection_layout = QtWidgets.QHBoxLayout()
        
        # Выбор по номеру
        number_layout = QtWidgets.QHBoxLayout()
        number_layout.addWidget(QtWidgets.QLabel("Номер ППМ:"))
        self.ppm_number_spin = QtWidgets.QSpinBox()
        self.ppm_number_spin.setRange(1, 32)
        self.ppm_number_spin.setValue(12)
        self.ppm_number_spin.valueChanged.connect(self.on_ppm_number_changed)
        number_layout.addWidget(self.ppm_number_spin)
        
        # Выбор по координатам
        coord_layout = QtWidgets.QHBoxLayout()
        coord_layout.addWidget(QtWidgets.QLabel("Координаты:"))
        coord_layout.addWidget(QtWidgets.QLabel("X:"))
        self.coord_x_spin = QtWidgets.QDoubleSpinBox()
        self.coord_x_spin.setRange(-100, 100)
        self.coord_x_spin.setSingleStep(0.1)
        self.coord_x_spin.setDecimals(1)
        self.coord_x_spin.valueChanged.connect(self.on_coord_changed)
        coord_layout.addWidget(self.coord_x_spin)
        
        coord_layout.addWidget(QtWidgets.QLabel("Y:"))
        self.coord_y_spin = QtWidgets.QDoubleSpinBox()
        self.coord_y_spin.setRange(-100, 100)
        self.coord_y_spin.setSingleStep(0.1)
        self.coord_y_spin.setDecimals(1)
        self.coord_y_spin.valueChanged.connect(self.on_coord_changed)
        coord_layout.addWidget(self.coord_y_spin)
        
        selection_layout.addLayout(number_layout)
        selection_layout.addStretch()
        selection_layout.addLayout(coord_layout)
        
        ppm_layout.addLayout(selection_layout)
        
        # Визуальный выбор ППМ — компактная карточка по центру
        ppm_card = QtWidgets.QFrame()
        ppm_card.setObjectName("ppmCard")
        ppm_card.setStyleSheet(
            "#ppmCard{background:#f7f9fc;border:1px solid #dfe3e8;border-radius:10px;}"
        )
        ppm_card_layout = QtWidgets.QVBoxLayout(ppm_card)
        ppm_card_layout.setContentsMargins(12, 12, 12, 12)
        ppm_card_layout.setSpacing(8)

        self.ppm_field_view = PpmFieldView()
        self.ppm_field_view.ppm_selected.connect(self.on_ppm_selected_visual)
        self.ppm_field_view.setStyleSheet(
            "QGraphicsView{background:#ffffff;border:1px solid #e3e7ee;border-radius:8px;}"
        )
        # Размеры под содержимое сцены без полос прокрутки
        self.ppm_field_view.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        self.ppm_field_view.setVerticalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        ppm_card_layout.addWidget(self.ppm_field_view)

        # Тень под карточкой для глубины
        shadow = QtWidgets.QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(14)
        shadow.setOffset(0, 4)
        shadow.setColor(QtGui.QColor(0, 0, 0, 40))
        ppm_card.setGraphicsEffect(shadow)

        center_row = QtWidgets.QHBoxLayout()
        center_row.addStretch()
        center_row.addWidget(ppm_card)
        center_row.addStretch()
        ppm_layout.addLayout(center_row)
        
        main_layout.addWidget(ppm_group)
        
        # Группа управления
        control_group = QtWidgets.QGroupBox("Управление")
        control_layout = QtWidgets.QVBoxLayout(control_group)
        
        # Статус подключения
        status_layout = QtWidgets.QHBoxLayout()
        status_layout.addWidget(QtWidgets.QLabel("Статус PSN:"))
        self.psn_status_label = QtWidgets.QLabel("Не подключен")
        self.psn_status_label.setStyleSheet("color: red;")
        status_layout.addWidget(self.psn_status_label)
        status_layout.addSpacing(24)
        status_layout.addWidget(QtWidgets.QLabel("Статус МА:"))
        self.ma_status_label = QtWidgets.QLabel("Не подключен")
        self.ma_status_label.setStyleSheet("color: red;")
        status_layout.addWidget(self.ma_status_label)
        status_layout.addStretch()
        
        control_layout.addLayout(status_layout)
        
        # Кнопки подключения
        button_layout = QtWidgets.QHBoxLayout()
        
        self.connect_btn = QtWidgets.QPushButton("Подключиться к PSN")
        self.connect_btn.clicked.connect(self.connect_devices)
        button_layout.addWidget(self.connect_btn)
        
        self.move_btn = QtWidgets.QPushButton("Переместиться к ППМ")
        self.move_btn.clicked.connect(self.move_to_ppm)
        self.move_btn.setEnabled(False)
        button_layout.addWidget(self.move_btn)
        
        self.disconnect_btn = QtWidgets.QPushButton("Отключиться от PSN")
        self.disconnect_btn.clicked.connect(self.disconnect_devices)
        self.disconnect_btn.setEnabled(False)
        button_layout.addWidget(self.disconnect_btn)

        # Подключение МА
        self.connect_ma_btn = QtWidgets.QPushButton("Подключиться к МА")
        self.connect_ma_btn.clicked.connect(self.connect_ma)
        button_layout.addWidget(self.connect_ma_btn)

        self.disconnect_ma_btn = QtWidgets.QPushButton("Отключиться от МА")
        self.disconnect_ma_btn.clicked.connect(self.disconnect_ma)
        self.disconnect_ma_btn.setEnabled(False)
        button_layout.addWidget(self.disconnect_ma_btn)
        
        control_layout.addLayout(button_layout)
        
        # Команды МА
        ma_cmds_layout = QtWidgets.QGridLayout()
        row = 0

        # Включить / Отключить ППМ
        self.ppm_on_btn = QtWidgets.QPushButton("Включить ППМ")
        self.ppm_on_btn.clicked.connect(self.turn_on_ppm)
        self.ppm_on_btn.setEnabled(False)
        ma_cmds_layout.addWidget(self.ppm_on_btn, row, 0)

        self.ppm_off_btn = QtWidgets.QPushButton("Отключить ППМ")
        self.ppm_off_btn.clicked.connect(self.turn_off_ppm)
        self.ppm_off_btn.setEnabled(False)
        ma_cmds_layout.addWidget(self.ppm_off_btn, row, 1)
        row += 1

        # ФВ дискрет
        self.fv_spin = QtWidgets.QSpinBox()
        self.fv_spin.setRange(0, 63)
        self.fv_spin.setValue(0)
        self.set_fv_btn = QtWidgets.QPushButton("Установить ФВ")
        self.set_fv_btn.clicked.connect(self.set_phase_shifter)
        self.set_fv_btn.setEnabled(False)
        ma_cmds_layout.addWidget(QtWidgets.QLabel("ФВ дискрет:"), row, 0)
        hl1 = QtWidgets.QHBoxLayout()
        w1 = QtWidgets.QWidget(); w1.setLayout(hl1)
        hl1.addWidget(self.fv_spin)
        hl1.addWidget(self.set_fv_btn)
        ma_cmds_layout.addWidget(w1, row, 1)
        row += 1

        # ЛЗ дискрет
        self.lz_spin = QtWidgets.QSpinBox()
        self.lz_spin.setRange(0, 31)
        self.lz_spin.setValue(0)
        self.set_lz_btn = QtWidgets.QPushButton("Установить ЛЗ")
        self.set_lz_btn.clicked.connect(self.set_delay)
        self.set_lz_btn.setEnabled(False)
        ma_cmds_layout.addWidget(QtWidgets.QLabel("ЛЗ дискрет:"), row, 0)
        hl2 = QtWidgets.QHBoxLayout()
        w2 = QtWidgets.QWidget(); w2.setLayout(hl2)
        hl2.addWidget(self.lz_spin)
        hl2.addWidget(self.set_lz_btn)
        ma_cmds_layout.addWidget(w2, row, 1)

        control_layout.addLayout(ma_cmds_layout)

        main_layout.addWidget(control_group)
        
        # Инициализируем координаты для ППМ 12
        self.update_coordinates_from_ppm(12)
        
    def update_coordinate_systems(self):
        """Обновляет список систем координат"""
        self.coord_system_combo.clear()
        for system in self.coord_manager.systems:
            self.coord_system_combo.addItem(system.name)
            
    def get_ppm_coordinates(self, ppm_num):
        """Получает координаты ППМ по его номеру"""
        if not (1 <= ppm_num <= 32):
            return None, None
            
        # ППМ нумеруются по столбцам, сверху вниз
        # Столбец 1: ППМ 1-8 (x_cords[0])
        # Столбец 2: ППМ 9-16 (x_cords[1])
        # Столбец 3: ППМ 17-24 (x_cords[2])
        # Столбец 4: ППМ 25-32 (x_cords[3])
        col = (ppm_num - 1) // 8
        row = (ppm_num - 1) % 8
        
        if row < len(self.y_cords) and col < len(self.x_cords):
            return self.x_cords[col], self.y_cords[row]
        return None, None
        
    def get_ppm_from_coordinates(self, x, y):
        """Получает номер ППМ по координатам (приближенно)"""
        min_distance = float('inf')
        closest_ppm = 1
        
        for ppm_num in range(1, 33):
            ppm_x, ppm_y = self.get_ppm_coordinates(ppm_num)
            if ppm_x is not None and ppm_y is not None:
                distance = ((x - ppm_x) ** 2 + (y - ppm_y) ** 2) ** 0.5
                if distance < min_distance:
                    min_distance = distance
                    closest_ppm = ppm_num
                    
        return closest_ppm
        
    def update_coordinates_from_ppm(self, ppm_num):
        """Обновляет координаты при изменении номера ППМ"""
        x, y = self.get_ppm_coordinates(ppm_num)
        if x is not None and y is not None:
            self.coord_x_spin.blockSignals(True)
            self.coord_y_spin.blockSignals(True)
            self.coord_x_spin.setValue(x)
            self.coord_y_spin.setValue(y)
            self.coord_x_spin.blockSignals(False)
            self.coord_y_spin.blockSignals(False)
            self.ppm_field_view.highlight_ppm(ppm_num)
            
    def on_ppm_number_changed(self):
        """Обработчик изменения номера ППМ"""
        ppm_num = self.ppm_number_spin.value()
        self.update_coordinates_from_ppm(ppm_num)
        
    def on_coord_changed(self):
        """Обработчик изменения координат"""
        x = self.coord_x_spin.value()
        y = self.coord_y_spin.value()
        closest_ppm = self.get_ppm_from_coordinates(x, y)
        
        self.ppm_number_spin.blockSignals(True)
        self.ppm_number_spin.setValue(closest_ppm)
        self.ppm_number_spin.blockSignals(False)
        self.ppm_field_view.highlight_ppm(closest_ppm)
        
    def on_ppm_selected_visual(self, ppm_num):
        """Обработчик визуального выбора ППМ"""
        self.ppm_number_spin.blockSignals(True)
        self.ppm_number_spin.setValue(ppm_num)
        self.ppm_number_spin.blockSignals(False)
        self.update_coordinates_from_ppm(ppm_num)
        

        
    def set_device_settings(self, settings):
        """Устанавливает настройки устройств"""
        self.device_settings = settings
        # Обновляем систему координат
        if settings:
            coord_system_name = settings.get('coordinate_system', 'MA_BZ')
            index = self.coord_system_combo.findText(coord_system_name)
            if index >= 0:
                self.coord_system_combo.setCurrentIndex(index)
        self._update_controls_enabled()
                
    def connect_devices(self):
        """Подключение к PSN"""
        if not self.device_settings:
            QtWidgets.QMessageBox.warning(self, "Ошибка", "Настройки устройств не заданы")
            return
            
        try:
            # Подключение к PSN
            psn_ip = self.device_settings.get('psn_ip', '')
            psn_port = self.device_settings.get('psn_port', '')
            psn_mode = self.device_settings.get('psn_mode', 0)
            
            if not psn_ip or not psn_port:
                QtWidgets.QMessageBox.warning(self, "Ошибка", "Не указаны IP или порт для PSN")
                return
                
            self.psn = PSN(psn_ip, int(psn_port), psn_mode)
            self.psn.connect()
            
            # Настройка системы координат
            coord_system_name = self.coord_system_combo.currentText()
            self.coord_system = None
            for system in self.coord_manager.systems:
                if system.name == coord_system_name:
                    self.coord_system = system
                    break
                    
            if self.coord_system:
                self.psn.set_offset(self.coord_system.x_offset, self.coord_system.y_offset)
                
            # Настройка параметров PSN
            speed_x = int(self.device_settings.get('psn_speed_x', 10))
            speed_y = int(self.device_settings.get('psn_speed_y', 10))
            acc_x = int(self.device_settings.get('psn_acc_x', 5))
            acc_y = int(self.device_settings.get('psn_acc_y', 5))
            
            self.psn.set_speed(0, speed_x)
            self.psn.set_speed(1, speed_y)
            self.psn.set_acc(0, acc_x)
            self.psn.set_acc(1, acc_y)
            
            self.psn_status_label.setText("Подключен")
            self.psn_status_label.setStyleSheet("color: green;")
            
            # Активируем кнопки
            self.connect_btn.setEnabled(False)
            self.move_btn.setEnabled(True)
            self.disconnect_btn.setEnabled(True)
            
            QtWidgets.QMessageBox.information(self, "Успех", "Подключение к PSN завершено успешно")
            
        except Exception as e:
            QtWidgets.QMessageBox.critical(self, "Ошибка подключения", str(e))
            logger.error(f"Ошибка подключения PSN в ручном управлении: {e}")
            self.disconnect_devices()
        finally:
            self._update_controls_enabled()
            
    def move_to_ppm(self):
        """Перемещение к выбранному ППМ"""
        if not self.psn:
            QtWidgets.QMessageBox.warning(self, "Ошибка", "PSN не подключен")
            return
            
        ppm_num = self.ppm_number_spin.value()
        x = self.coord_x_spin.value()
        y = self.coord_y_spin.value()
        
        try:
            self.move_btn.setEnabled(False)
            self.move_btn.setText("Перемещение...")
            
            QtWidgets.QApplication.processEvents()  # Обновляем интерфейс
            
            self.psn.move(x, y)
            
        except Exception as e:
            QtWidgets.QMessageBox.critical(self, "Ошибка перемещения", str(e))
            logger.error(f"Ошибка перемещения в ручном управлении: {e}")
            
        finally:
            self.move_btn.setEnabled(True)
            self.move_btn.setText("Переместиться к ППМ")
            self._update_controls_enabled()
            
    def disconnect_devices(self):
        """Отключение от PSN"""
        try:
            if self.psn:
                self.psn.disconnect()
                self.psn = None
                self.psn_status_label.setText("Не подключен")
                self.psn_status_label.setStyleSheet("color: red;")
                
            self.connect_btn.setEnabled(True)
            self.move_btn.setEnabled(False)
            self.disconnect_btn.setEnabled(False)
            
        except Exception as e:
            QtWidgets.QMessageBox.critical(self, "Ошибка отключения", str(e))
            logger.error(f"Ошибка отключения PSN в ручном управлении: {e}")
        finally:
            self._update_controls_enabled()

    # --- Работа с МА ---
    def connect_ma(self):
        if not self.device_settings:
            QtWidgets.QMessageBox.warning(self, "Ошибка", "Настройки устройств не заданы")
            return
        try:
            com_port = self.device_settings.get('ma_com_port', '')
            mode = int(self.device_settings.get('ma_mode', 0))
            if mode == 0 and (not com_port or com_port == 'Тестовый'):
                QtWidgets.QMessageBox.warning(self, "Ошибка", "COM-порт для МА не выбран")
                return
            self.ma = MA(com_port=com_port, mode=mode)
            self.ma.connect()
            self.ma_status_label.setText("Подключен")
            self.ma_status_label.setStyleSheet("color: green;")
            self.connect_ma_btn.setEnabled(False)
            self.disconnect_ma_btn.setEnabled(True)
        except Exception as e:
            self.ma = None
            QtWidgets.QMessageBox.critical(self, "Ошибка подключения МА", str(e))
            logger.error(f"Ошибка подключения МА: {e}")
        finally:
            self._update_controls_enabled()

    def disconnect_ma(self):
        try:
            if self.ma:
                self.ma.disconnect()
                self.ma = None
            self.ma_status_label.setText("Не подключен")
            self.ma_status_label.setStyleSheet("color: red;")
            self.connect_ma_btn.setEnabled(True)
            self.disconnect_ma_btn.setEnabled(False)
        except Exception as e:
            QtWidgets.QMessageBox.critical(self, "Ошибка отключения МА", str(e))
            logger.error(f"Ошибка отключения МА: {e}")
        finally:
            self._update_controls_enabled()

    def _get_selected_channel(self) -> Channel:
        return Channel.Receiver if self.channel_combo.currentText() == 'Приемник' else Channel.Transmitter

    def _get_selected_direction(self) -> Direction:
        return Direction.Horizontal if self.direction_combo.currentText() == 'Горизонтальная' else Direction.Vertical

    def turn_on_ppm(self):
        if not self.ma:
            QtWidgets.QMessageBox.warning(self, "Ошибка", "МА не подключен")
            return
        ppm_num = self.ppm_number_spin.value()
        try:
            self.ma.switch_ppm(ppm_num, chanel=self._get_selected_channel(), direction=self._get_selected_direction(), state=PpmState.ON)
        except Exception as e:
            QtWidgets.QMessageBox.critical(self, "Ошибка включения ППМ", str(e))
            logger.error(f"Ошибка включения ППМ: {e}")

    def turn_off_ppm(self):
        if not self.ma:
            QtWidgets.QMessageBox.warning(self, "Ошибка", "МА не подключен")
            return
        ppm_num = self.ppm_number_spin.value()
        try:
            self.ma.switch_ppm(ppm_num, chanel=self._get_selected_channel(), direction=self._get_selected_direction(), state=PpmState.OFF)
        except Exception as e:
            QtWidgets.QMessageBox.critical(self, "Ошибка отключения ППМ", str(e))
            logger.error(f"Ошибка отключения ППМ: {e}")

    def set_phase_shifter(self):
        if not self.ma:
            QtWidgets.QMessageBox.warning(self, "Ошибка", "МА не подключен")
            return
        ppm_num = self.ppm_number_spin.value()
        value = int(self.fv_spin.value())
        try:
            self.ma.set_phase_shifter(ppm_num=ppm_num, chanel=self._get_selected_channel(), direction=self._get_selected_direction(), value=value)
        except Exception as e:
            QtWidgets.QMessageBox.critical(self, "Ошибка установки ФВ", str(e))
            logger.error(f"Ошибка установки ФВ: {e}")

    def set_delay(self):
        if not self.ma:
            QtWidgets.QMessageBox.warning(self, "Ошибка", "МА не подключен")
            return
        value = int(self.lz_spin.value())
        try:
            self.ma.set_delay(chanel=self._get_selected_channel(), direction=self._get_selected_direction(), value=value)
        except Exception as e:
            QtWidgets.QMessageBox.critical(self, "Ошибка установки ЛЗ", str(e))
            logger.error(f"Ошибка установки ЛЗ: {e}")

    def _update_controls_enabled(self):
        """Управляет доступностью кнопок в зависимости от подключений."""
        psn_connected = self.psn is not None
        ma_connected = self.ma is not None
        self.move_btn.setEnabled(psn_connected)
        self.disconnect_btn.setEnabled(psn_connected)
        # Команды МА доступны только при подключенном МА
        for btn in [self.ppm_on_btn, self.ppm_off_btn, self.set_fv_btn, self.set_lz_btn]:
            btn.setEnabled(ma_connected)

    def on_coord_system_changed(self, text):
        self.coord_system = None
        for system in self.coord_manager.systems:
            if system.name == text:
                self.coord_system = system
                break

        if self.coord_system:
            if self.psn:
                self.psn.set_offset(self.coord_system.x_offset, self.coord_system.y_offset)
            else:
                logger.warning('Нет активного подключения сканера. Система координат не применена.')


class PpmFieldView(QtWidgets.QGraphicsView):
    """Визуальное представление поля ППМ для ручного выбора"""
    
    ppm_selected = QtCore.pyqtSignal(int)
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.scene = QtWidgets.QGraphicsScene()
        self.setScene(self.scene)
        self.setRenderHint(QtGui.QPainter.Antialiasing)
        
        self.rects = {}  # Словарь прямоугольников ППМ
        self.highlighted_ppm = None
        
        self.setup_scene()
        
    def setup_scene(self):
        """Настройка сцены с ППМ"""
        self.scene.clear()
        self.rects.clear()
        
        # Размеры и стили сетки
        rect_width = 120
        rect_height = 48
        spacing_x = 132
        spacing_y = 60
        margin = 20
        
        # Создаем сетку 4x8 (32 ППМ)
        for col in range(4):
            for row in range(8):
                ppm_num = col * 8 + row + 1
                
                x = margin + col * spacing_x
                y = margin + row * spacing_y
                
                # Создаем прямоугольник
                rect = QtWidgets.QGraphicsRectItem(x, y, rect_width, rect_height)
                rect.setBrush(QtGui.QBrush(QtGui.QColor(245, 248, 252)))
                rect.setPen(QtGui.QPen(QtGui.QColor(180, 190, 200), 1))
                
                # Создаем текст с номером ППМ
                text = QtWidgets.QGraphicsTextItem(f"ППМ {ppm_num}")
                font = text.font()
                font.setPointSize(10)
                font.setBold(True)
                text.setFont(font)
                text.setDefaultTextColor(QtGui.QColor(40, 50, 60))
                
                # Центрируем текст
                text_rect = text.boundingRect()
                text.setPos(x + (rect_width - text_rect.width()) / 2, 
                           y + (rect_height - text_rect.height()) / 2)
                
                self.scene.addItem(rect)
                self.scene.addItem(text)
                
                # Сохраняем ссылку
                self.rects[ppm_num] = (rect, text)
                
        # Устанавливаем размер сцены с отступами
        scene_width = 2 * margin + 4 * spacing_x
        scene_height = 2 * margin + 8 * spacing_y
        self.scene.setSceneRect(0, 0, scene_width, scene_height)
        # Подогнать размер вида под сцену, чтобы всё влезало
        self.setMinimumSize(int(scene_width + 24), int(scene_height + 24))
        
    def highlight_ppm(self, ppm_num):
        """Выделяет выбранный ППМ"""
        # Сбрасываем предыдущее выделение
        if self.highlighted_ppm and self.highlighted_ppm in self.rects:
            rect, _ = self.rects[self.highlighted_ppm]
            rect.setBrush(QtGui.QBrush(QtGui.QColor(245, 248, 252)))
            
        # Выделяем новый ППМ
        if ppm_num in self.rects:
            rect, _ = self.rects[ppm_num]
            rect.setBrush(QtGui.QBrush(QtGui.QColor(99, 132, 255)))
            self.highlighted_ppm = ppm_num
            
    def mousePressEvent(self, event):
        """Обработчик клика мыши"""
        scene_pos = self.mapToScene(event.pos())
        items = self.scene.items(scene_pos)
        
        for item in items:
            if isinstance(item, QtWidgets.QGraphicsRectItem):
                # Находим соответствующий ППМ
                for ppm_num, (rect, _) in self.rects.items():
                    if rect == item:
                        self.ppm_selected.emit(ppm_num)
                        return
                        
        super().mousePressEvent(event)

