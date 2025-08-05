from PyQt5 import QtWidgets, QtCore, QtGui
from PyQt5.QtGui import QTextCursor
from PyQt5.QtWidgets import QMessageBox, QStyle
from PyQt5.QtCore import QSize
from loguru import logger
import threading
import numpy as np
from core.devices.ma import MA
from core.devices.pna import PNA
from core.devices.psn import PSN
from core.measurements.check.check_ma import CheckMA
from core.common.enums import Channel, Direction, PpmState
from core.common.coordinate_system import CoordinateSystemManager

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

class PpmRect(QtWidgets.QGraphicsRectItem):
    def __init__(self, ppm_num, parent_widget, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.ppm_num = ppm_num
        self.parent_widget = parent_widget
        self.setAcceptHoverEvents(True)
        self.setFlag(QtWidgets.QGraphicsItem.ItemIsSelectable, True)

        default_color = "#f8f9fa"
        border_color = "#dee2e6"
        
        self.setBrush(QtGui.QBrush(QtGui.QColor(default_color)))
        self.setPen(QtGui.QPen(QtGui.QColor(border_color), 1.5))
        self.text = None
        self.status = None

    def set_status(self, status):
        if status == "ok":
            color = "#28a745"  # зеленый
        elif status == "fail":
            color = "#dc3545"  # красный
        else:
            color = "#f8f9fa"  # серый по умолчанию
            
        self.setBrush(QtGui.QBrush(QtGui.QColor(color)))
        self.status = status

    def hoverEnterEvent(self, event):
        """Подсветка при наведении мыши"""
        hover_color = "#e9ecef"
        
        # Сохраняем текущий цвет если это статусный цвет
        if self.status == "ok":
            hover_color = "#28a745"  # зеленый
        elif self.status == "fail":
            hover_color = "#dc3545"  # красный
            
        # Делаем цвет немного ярче для эффекта hover
        color = QtGui.QColor(hover_color)
        color = color.lighter(110)
        self.setBrush(QtGui.QBrush(color))
        super().hoverEnterEvent(event)

    def hoverLeaveEvent(self, event):
        """Восстанавливаем цвет при уходе мыши"""
        self.set_status(self.status)
        super().hoverLeaveEvent(event)

    def mousePressEvent(self, event):
        if event.button() == QtCore.Qt.LeftButton:
            self.setSelected(True)
        super().mousePressEvent(event)


class BottomRect(QtWidgets.QGraphicsRectItem):
    def __init__(self, parent_widget, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.parent_widget = parent_widget
        self.setAcceptHoverEvents(True)
        self.setFlag(QtWidgets.QGraphicsItem.ItemIsSelectable, True)

        default_color = "#f8f9fa"
        border_color = "#dee2e6"
        
        self.setBrush(QtGui.QBrush(QtGui.QColor(default_color)))
        self.setPen(QtGui.QPen(QtGui.QColor(border_color), 1.5))
        self.status = None

    def set_status(self, status):
        if status == "ok":
            color = "#28a745"  # зеленый
        elif status == "fail":
            color = "#dc3545"  # красный
        else:
            color = "#f8f9fa"  # серый по умолчанию
            
        self.setBrush(QtGui.QBrush(QtGui.QColor(color)))
        self.status = status

    def hoverEnterEvent(self, event):
        """Подсветка при наведении мыши"""
        hover_color = "#e9ecef"
        
        # Сохраняем текущий цвет если это статусный цвет
        if self.status == "ok":
            hover_color = "#28a745"  # зеленый
        elif self.status == "fail":
            hover_color = "#dc3545"  # красный
            
        # Делаем цвет немного ярче для эффекта hover
        color = QtGui.QColor(hover_color)
        color = color.lighter(110)
        self.setBrush(QtGui.QBrush(color))
        super().hoverEnterEvent(event)

    def hoverLeaveEvent(self, event):
        """Восстанавливаем цвет при уходе мыши"""
        self.set_status(self.status)
        super().hoverLeaveEvent(event)

    def mousePressEvent(self, event):
        if event.button() == QtCore.Qt.LeftButton:
            self.setSelected(True)
        super().mousePressEvent(event)

class PpmFieldView(QtWidgets.QGraphicsView):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setScene(QtWidgets.QGraphicsScene(self))
        self.rects = {}
        self.texts = {}
        self.bottom_rect = None
        self.bottom_text = None
        self.bottom_rect_height = 60  # Высота нижнего прямоугольника
        self.setRenderHint(QtGui.QPainter.Antialiasing)
        self.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        self.parent_widget = parent
        self.create_rects()
        
        # Включаем контекстное меню
        self.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
        self.customContextMenuRequested.connect(self.show_context_menu)

    def create_rects(self):
        self.scene().clear()
        self.rects.clear()
        self.texts.clear()

        text_color = "#212529"
        font_size = 10
        
        # Создаем основные ППМ прямоугольники
        for col in range(4):
            for row in range(8):
                ppm_num = col * 8 + row + 1
                rect = PpmRect(ppm_num, self.parent_widget, 0, 0, 1, 1)
                self.scene().addItem(rect)
                self.rects[ppm_num] = rect

                font = QtGui.QFont("Segoe UI", font_size, QtGui.QFont.Weight.DemiBold)
                text = self.scene().addText(f"ППМ {ppm_num}", font)
                text.setDefaultTextColor(QtGui.QColor(text_color))
                self.texts[ppm_num] = text

        # Создаем нижний прямоугольник с интерактивностью
        self.bottom_rect = BottomRect(self.parent_widget, 0, 0, 1, 1)
        self.scene().addItem(self.bottom_rect)
        
        font = QtGui.QFont("Segoe UI", font_size, QtGui.QFont.Weight.DemiBold)
        self.bottom_text = self.scene().addText("Линии задержки", font)
        self.bottom_text.setDefaultTextColor(QtGui.QColor(text_color))
        
        self.update_layout()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.update_layout()
        self.fitInView(self.sceneRect(), QtCore.Qt.KeepAspectRatio)

    def update_layout(self):
        total_height = self.viewport().height()
        ppm_area_height = total_height - self.bottom_rect_height - 4  # 4 пикселя отступ
        
        w = self.viewport().width() / 4
        h = ppm_area_height / 8

        margin = 2
        cell_w = w - margin
        cell_h = h - margin
        
        # Размещаем основные ППМ прямоугольники
        for col in range(4):
            for row in range(8):
                ppm_num = col * 8 + row + 1
                rect = self.rects[ppm_num]

                x = col * w + margin / 2
                y = row * h + margin / 2
                rect.setRect(x, y, cell_w, cell_h)

                text = self.texts[ppm_num]
                text_rect = text.boundingRect()

                text_x = x + (cell_w - text_rect.width()) / 2
                text_y = y + (cell_h - text_rect.height()) / 2
                
                text.setPos(text_x, text_y)
        
        # Размещаем нижний прямоугольник
        if self.bottom_rect:
            bottom_y = 8 * h + 2  # 2 пикселя отступ сверху
            bottom_w = 4 * w - margin
            
            self.bottom_rect.setRect(margin / 2, bottom_y, bottom_w, self.bottom_rect_height - margin)
            
            if self.bottom_text:
                text_rect = self.bottom_text.boundingRect()
                text_x = margin / 2 + (bottom_w - text_rect.width()) / 2
                text_y = bottom_y + (self.bottom_rect_height - margin - text_rect.height()) / 2
                self.bottom_text.setPos(text_x, text_y)
                
        self.scene().setSceneRect(0, 0, 4*w, total_height)

    def update_ppm(self, ppm_num, status):
        if ppm_num in self.rects:
            self.rects[ppm_num].set_status(status)
    
    def update_bottom_rect_status(self, status):
        """Обновляет статус нижнего прямоугольника"""
        if self.bottom_rect:
            self.bottom_rect.set_status(status)
    
    def set_bottom_rect_text(self, text):
        """Изменяет текст нижнего прямоугольника"""
        if self.bottom_text:
            self.bottom_text.setPlainText(text)
            self.update_layout()  # Обновляем layout для правильного центрирования текста
    
    def get_ppm_at_position(self, pos):
        """Определяет номер ППМ или нижний прямоугольник по позиции клика"""
        # Учитываем высоту нижнего прямоугольника
        total_height = self.viewport().height()
        ppm_area_height = total_height - self.bottom_rect_height - 4  # 4 пикселя отступ
        
        w = self.viewport().width() / 4
        h = ppm_area_height / 8
        margin = 2
        
        # Сначала проверяем нижний прямоугольник
        bottom_y = 8 * h + 2  # 2 пикселя отступ сверху
        if pos.y() >= bottom_y and pos.y() <= (bottom_y + self.bottom_rect_height - margin):
            bottom_w = 4 * w - margin
            if pos.x() >= margin/2 and pos.x() <= (margin/2 + bottom_w):
                return "bottom_rect"  # Специальное значение для нижнего прямоугольника
        
        # Затем проверяем область ППМ
        col = int(pos.x() / w)
        row = int(pos.y() / h)
        
        # Проверяем границы и учитываем отступы
        if 0 <= col < 4 and 0 <= row < 8:
            # Проверяем, что клик попал именно в ячейку, а не в отступ
            x_in_cell = pos.x() - col * w
            y_in_cell = pos.y() - row * h
            
            if x_in_cell >= margin/2 and y_in_cell >= margin/2:
                ppm_num = col * 8 + row + 1
                return ppm_num
        return None
    
    def show_context_menu(self, pos):
        """Показывает контекстное меню для ППМ или нижнего прямоугольника в указанной позиции"""
        element = self.get_ppm_at_position(pos)
        if element is not None and self.parent_widget is not None:
            if element == "bottom_rect":
                # Выделяем нижний прямоугольник и показываем контекстное меню
                if self.bottom_rect:
                    self.bottom_rect.setSelected(True)
                self.parent_widget.show_bottom_rect_details(self.mapToGlobal(pos))
            else:
                # Обрабатываем как ППМ
                ppm_num = element
                if ppm_num in self.rects:
                    self.rects[ppm_num].setSelected(True)
                # Показываем информацию
                self.parent_widget.show_ppm_details_graphics(ppm_num, self.mapToGlobal(pos))

class CheckMaWidget(QtWidgets.QWidget):
    update_table_signal = QtCore.pyqtSignal(int, bool, float, float, list)
    error_signal = QtCore.pyqtSignal(str, str)  # title, message
    buttons_enabled_signal = QtCore.pyqtSignal(bool)  # enabled
    check_finished_signal = QtCore.pyqtSignal()  # когда проверка завершена
    
    def __init__(self):
        super().__init__()

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
        self.set_button_connection_state(self.pna_connect_btn, False)
        pna_layout.addWidget(self.pna_connect_btn)
        self.connect_layout.addWidget(pna_widget)

        psn_widget = QtWidgets.QWidget()
        psn_layout = QtWidgets.QHBoxLayout(psn_widget)
        psn_layout.setContentsMargins(0, 0, 0, 0)
        self.psn_connect_btn = QtWidgets.QPushButton('Сканер')
        self.psn_connect_btn.setMinimumHeight(40)
        self.set_button_connection_state(self.psn_connect_btn, False)
        psn_layout.addWidget(self.psn_connect_btn)
        self.connect_layout.addWidget(psn_widget)

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
        
        # Создаем горизонтальный layout для комбобокса и кнопок
        coord_selection_layout = QtWidgets.QHBoxLayout()
        coord_selection_layout.setSpacing(5)
        coord_selection_layout.setContentsMargins(0, 0, 0, 0)
        
        self.coord_system_combo = QtWidgets.QComboBox()
        self.coord_system_combo.addItems(self.coord_system_manager.get_system_names())
        self.coord_system_combo.setMinimumWidth(200)
        self.coord_system_combo.currentTextChanged.connect(self.update_coord_buttons_state)
        coord_selection_layout.addWidget(self.coord_system_combo, 1)
        
        # Кнопка добавления системы координат
        self.add_coord_system_btn = QtWidgets.QPushButton('+')
        self.add_coord_system_btn.setFixedSize(24, 22)
        self.add_coord_system_btn.setToolTip('Добавить новую систему координат')
        self.add_coord_system_btn.clicked.connect(self.add_coordinate_system)
        coord_selection_layout.addWidget(self.add_coord_system_btn, 0, QtCore.Qt.AlignVCenter)
        
        # Кнопка удаления системы координат
        self.remove_coord_system_btn = QtWidgets.QPushButton('−')
        self.remove_coord_system_btn.setFixedSize(24, 22)
        self.remove_coord_system_btn.setToolTip('Удалить выбранную систему координат')
        self.remove_coord_system_btn.clicked.connect(self.remove_coordinate_system)
        coord_selection_layout.addWidget(self.remove_coord_system_btn, 0, QtCore.Qt.AlignVCenter)
        
        coord_layout.addRow('Система координат:', coord_selection_layout)


        self.meas_tab_layout.addWidget(coord_group)

        criteria_group = QtWidgets.QGroupBox('Критерии проверки')
        criteria_layout = QtWidgets.QGridLayout(criteria_group)
        criteria_layout.setContentsMargins(15, 15, 15, 15)
        criteria_layout.setSpacing(10)

        criteria_layout.addWidget(QtWidgets.QLabel(""), 0, 0)  # Пустая ячейка
        rx_label = QtWidgets.QLabel("RX")
        rx_label.setAlignment(QtCore.Qt.AlignCenter)
        criteria_layout.addWidget(rx_label, 0, 1)
        
        tx_label = QtWidgets.QLabel("TX")
        tx_label.setAlignment(QtCore.Qt.AlignCenter)
        criteria_layout.addWidget(tx_label, 0, 2)

        amp_label = QtWidgets.QLabel("Допуск амплитуды:")
        criteria_layout.addWidget(amp_label, 1, 0)
        
        self.rx_amp_tolerance = QtWidgets.QDoubleSpinBox()
        self.rx_amp_tolerance.setRange(0.1, 10.0)
        self.rx_amp_tolerance.setSingleStep(0.1)
        self.rx_amp_tolerance.setDecimals(1)
        self.rx_amp_tolerance.setValue(4.5)
        self.rx_amp_tolerance.setSuffix(' дБ')
        self.rx_amp_tolerance.setMinimumWidth(80)
        criteria_layout.addWidget(self.rx_amp_tolerance, 1, 1)
        
        self.tx_amp_tolerance = QtWidgets.QDoubleSpinBox()
        self.tx_amp_tolerance.setRange(0.1, 10.0)
        self.tx_amp_tolerance.setSingleStep(0.1)
        self.tx_amp_tolerance.setDecimals(1)
        self.tx_amp_tolerance.setValue(2.5)
        self.tx_amp_tolerance.setSuffix(' дБ')
        self.tx_amp_tolerance.setMinimumWidth(80)
        criteria_layout.addWidget(self.tx_amp_tolerance, 1, 2)

        min_phase_label = QtWidgets.QLabel("Мин. фаза (все ФВ):")
        criteria_layout.addWidget(min_phase_label, 2, 0)
        
        self.rx_phase_min = QtWidgets.QDoubleSpinBox()
        self.rx_phase_min.setRange(0.1, 50.0)
        self.rx_phase_min.setSingleStep(0.1)
        self.rx_phase_min.setDecimals(1)
        self.rx_phase_min.setValue(2.0)
        self.rx_phase_min.setSuffix('°')
        self.rx_phase_min.setMinimumWidth(80)
        criteria_layout.addWidget(self.rx_phase_min, 2, 1)
        
        self.tx_phase_min = QtWidgets.QDoubleSpinBox()
        self.tx_phase_min.setRange(0.1, 50.0)
        self.tx_phase_min.setSingleStep(0.1)
        self.tx_phase_min.setDecimals(1)
        self.tx_phase_min.setValue(2.0)
        self.tx_phase_min.setSuffix('°')
        self.tx_phase_min.setMinimumWidth(80)
        criteria_layout.addWidget(self.tx_phase_min, 2, 2)

        max_phase_label = QtWidgets.QLabel("Макс. фаза (все ФВ):")
        criteria_layout.addWidget(max_phase_label, 3, 0)
        
        self.rx_phase_max = QtWidgets.QDoubleSpinBox()
        self.rx_phase_max.setRange(1.0, 100.0)
        self.rx_phase_max.setSingleStep(0.1)
        self.rx_phase_max.setDecimals(1)
        self.rx_phase_max.setValue(12.0)
        self.rx_phase_max.setSuffix('°')
        self.rx_phase_max.setMinimumWidth(80)
        criteria_layout.addWidget(self.rx_phase_max, 3, 1)
        
        self.tx_phase_max = QtWidgets.QDoubleSpinBox()
        self.tx_phase_max.setRange(1.0, 100.0)
        self.tx_phase_max.setSingleStep(0.1)
        self.tx_phase_max.setDecimals(1)
        self.tx_phase_max.setValue(20.0)
        self.tx_phase_max.setSuffix('°')
        self.tx_phase_max.setMinimumWidth(80)
        criteria_layout.addWidget(self.tx_phase_max, 3, 2)
        

        self.meas_tab_layout.addWidget(criteria_group)

        ps_group = QtWidgets.QGroupBox('Допуски фазовращателей')
        ps_main_layout = QtWidgets.QVBoxLayout(ps_group)
        ps_main_layout.setContentsMargins(15, 15, 15, 15)
        
        # Контейнер с прокруткой для фазовращателей
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
            scroll_layout.addWidget(min_spinbox, row, 1)

            max_spinbox = QtWidgets.QDoubleSpinBox()
            max_spinbox.setRange(-50.0, 50.0)
            max_spinbox.setSingleStep(0.1)
            max_spinbox.setDecimals(1)
            max_spinbox.setValue(2.0)
            max_spinbox.setSuffix('°')
            max_spinbox.setMinimumWidth(70)
            scroll_layout.addWidget(max_spinbox, row, 2)
            
            self.phase_shifter_tolerances[angle] = {
                'min': min_spinbox,
                'max': max_spinbox
            }
        
        scroll_area.setWidget(scroll_widget)
        ps_main_layout.addWidget(scroll_area)

        self.meas_tab_layout.addWidget(ps_group)

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

        self.results_table = QtWidgets.QTableWidget()
        self.results_table.setColumnCount(12)
        self.results_table.setHorizontalHeaderLabels([
            'ППМ', 'Амп.\n(дБ)', 'Фаза\n(°)', 'Ст.\nАмп.', 'Ст.\nФазы',
            'Δ ФВ', '5.625°', '11.25°', '22.5°', '45°', '90°', '180°'])
        self.results_table.setRowCount(32)

        header = self.results_table.horizontalHeader()
        header.setSectionResizeMode(0, QtWidgets.QHeaderView.Fixed)
        header.resizeSection(0, 50)
        
        for i in range(1, 12):
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
            for col in range(1, 12):
                item = QtWidgets.QTableWidgetItem("")
                item.setTextAlignment(QtCore.Qt.AlignCenter)
                self.results_table.setItem(row, col, item)

        self.ppm_field_view = PpmFieldView(self)

        self.view_tabs = QtWidgets.QTabWidget()
        self.view_tabs.addTab(self.results_table, "Таблица")
        self.view_tabs.addTab(self.ppm_field_view, "2D поле")
        self.right_layout.addWidget(self.view_tabs, stretch=2)

        self.console = QtWidgets.QTextEdit()
        self.console.setReadOnly(True)
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

        # Подключение сигналов к слотам
        self.update_table_signal.connect(self.update_table_row)
        self.error_signal.connect(self.show_error_message)
        self.buttons_enabled_signal.connect(self.set_buttons_enabled)
        self.check_finished_signal.connect(self.on_check_finished)

        self.set_buttons_enabled(True)
        self.device_settings = {}
        self.pna_settings = {}

        self.check_criteria = {
            'rx_amp_max': 4.5,
            'tx_amp_max': 2.5,
            'rx_phase_min': 2.0,
            'rx_phase_max': 12.0,
            'tx_phase_min': 2.0,
            'tx_phase_max': 20.0,
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
        self.bottom_rect_data = {}  # Данные для линий задержки
        
        # Обновляем состояние кнопок системы координат
        self.update_coord_buttons_state()
        
        # Устанавливаем начальные стили кнопок подключения (отключено)
        self.set_button_connection_state(self.pna_connect_btn, False)
        self.set_button_connection_state(self.psn_connect_btn, False)
        self.set_button_connection_state(self.ma_connect_btn, False)

    def show_ppm_details(self, button: QtWidgets.QPushButton, ppm_num: int):
        """Показывает детальную информацию о ППМ в контекстном меню"""
        if ppm_num in self.ppm_data:
            data = self.ppm_data[ppm_num]
            menu = QtWidgets.QMenu()

            details = f"ППМ {ppm_num}\n"
            details += f"Результат: {'OK' if data['result'] else 'FAIL'}\n"
            details += f"Амплитуда: {data['amp']:.2f} дБ\n"
            details += f"Фаза: {data['phase']:.1f}°\n"
            
            if data['fv_data'] and len(data['fv_data']) > 0:
                details += "\nЗначения ФВ:\n"
                for i, value in enumerate(data['fv_data']):
                    if not np.isnan(value):
                        details += f"  {value:.1f}°\n"

            action = menu.addAction(details)
            action.setEnabled(False)

            menu.exec_(button.mapToGlobal(QtCore.QPoint(0, 0)))
        else:
            menu = QtWidgets.QMenu()
            action = menu.addAction(f"ППМ {ppm_num} - данные не готовы")
            action.setEnabled(False)
            menu.exec_(button.mapToGlobal(QtCore.QPoint(0, 0)))

    @QtCore.pyqtSlot(int, bool, float, float, list)
    def update_table_row(self, ppm_num: int, result: bool, amp: float, phase: float, fv_data: list):
        """Обновляет строку таблицы и 2D вид с результатами измерения"""
        try:
            self.ppm_data[ppm_num] = {
                'result': result,
                'amp': amp,
                'phase': phase,
                'fv_data': fv_data
            }

            row = ppm_num - 1

            self.results_table.setItem(row, 0, self.create_centered_table_item(str(ppm_num)))

            if np.isnan(amp):
                self.results_table.setItem(row, 1, self.create_centered_table_item(""))
            else:
                self.results_table.setItem(row, 1, self.create_centered_table_item(f"{amp:.2f}"))
                
            if np.isnan(phase):
                self.results_table.setItem(row, 2, self.create_centered_table_item(""))
            else:
                self.results_table.setItem(row, 2, self.create_centered_table_item(f"{phase:.1f}"))

            if np.isnan(amp):
                amp_status_item = self.create_neutral_status_item("-")
            else:
                amp_max = self.rx_amp_tolerance.value() if self.channel_combo.currentText() == 'Приемник' else self.tx_amp_tolerance.value()
                amp_ok = -amp_max <= amp <= amp_max
                
                amp_status = "OK" if amp_ok else "FAIL"
                amp_status_item = self.create_status_table_item(amp_status, amp_ok)
            
            self.results_table.setItem(row, 3, amp_status_item)

            if np.isnan(phase):
                phase_status_item = self.create_neutral_status_item("-")
            else:
                if self.channel_combo.currentText() == 'Приемник':
                    phase_min = self.rx_phase_min.value()
                    phase_max = self.rx_phase_max.value()
                    phase_all_ok = phase_min <= phase <= phase_max
                else:
                    phase_min = self.tx_phase_min.value()
                    phase_max = self.tx_phase_max.value()
                    phase_all_ok = phase_min < phase < phase_max

                if phase_all_ok:
                    phase_final_ok = True
                else:
                    if fv_data and len(fv_data) > 6:
                        individual_fv_ok = []
                        fv_angles = [5.625, 11.25, 22.5, 45, 90, 180]
                        
                        for i, fv_angle in enumerate(fv_angles):
                            if i + 1 < len(fv_data) and not np.isnan(fv_data[i + 1]):
                                fv_diff = fv_data[i + 1]
                                if fv_angle in self.check_criteria['phase_shifter_tolerances']:
                                    min_tolerance = self.check_criteria['phase_shifter_tolerances'][fv_angle]['min']
                                    max_tolerance = self.check_criteria['phase_shifter_tolerances'][fv_angle]['max']
                                    fv_ok = min_tolerance <= fv_diff <= max_tolerance
                                else:
                                    fv_ok = -2.0 <= fv_diff <= 2.0
                                individual_fv_ok.append(fv_ok)

                        phase_final_ok = len(individual_fv_ok) > 0 and all(individual_fv_ok)
                    else:
                        phase_final_ok = False

                phase_status = "OK" if phase_final_ok else "FAIL"
                phase_status_item = self.create_status_table_item(phase_status, phase_final_ok)
            
            self.results_table.setItem(row, 4, phase_status_item)

            if fv_data and len(fv_data) > 0:
                try:
                    if not np.isnan(fv_data[0]):
                        self.results_table.setItem(row, 5, QtWidgets.QTableWidgetItem(f"{fv_data[0]:.1f}"))
                    else:
                        self.results_table.setItem(row, 5, QtWidgets.QTableWidgetItem(""))

                    if not result:
                        for i in range(1, len(fv_data)):
                            if not np.isnan(fv_data[i]):
                                self.results_table.setItem(row, i + 5, QtWidgets.QTableWidgetItem(f"{fv_data[i]:.1f}"))
                            else:
                                self.results_table.setItem(row, i + 5, QtWidgets.QTableWidgetItem(""))
                    else:
                        for i in range(1, 6):
                            self.results_table.setItem(row, i + 5, QtWidgets.QTableWidgetItem(""))
                            
                except Exception as e:
                    logger.error(f'Ошибка при обновлении значений ФВ для ППМ {ppm_num}: {e}')
                    for i in range(6):
                        self.results_table.setItem(row, i + 5, QtWidgets.QTableWidgetItem(""))
            else:
                for i in range(6):
                    self.results_table.setItem(row, i + 5, QtWidgets.QTableWidgetItem(""))

            if np.isnan(amp) or np.isnan(phase):
                overall_status = "fail"
            else:
                amp_max = self.rx_amp_tolerance.value() if self.channel_combo.currentText() == 'Приемник' else self.tx_amp_tolerance.value()
                amp_ok = -amp_max <= amp <= amp_max

                if self.channel_combo.currentText() == 'Приемник':
                    phase_min = self.rx_phase_min.value()
                    phase_max = self.rx_phase_max.value()
                    phase_all_ok = phase_min <= phase <= phase_max
                else:
                    phase_min = self.tx_phase_min.value()
                    phase_max = self.tx_phase_max.value()
                    phase_all_ok = phase_min < phase < phase_max

                if phase_all_ok:
                    phase_final_ok = True
                else:
                    if fv_data and len(fv_data) > 6:
                        individual_fv_ok = []
                        fv_angles = [5.625, 11.25, 22.5, 45, 90, 180]
                        
                        for i, fv_angle in enumerate(fv_angles):
                            if i + 1 < len(fv_data) and not np.isnan(fv_data[i + 1]):
                                fv_diff = fv_data[i + 1]
                                if fv_angle in self.check_criteria['phase_shifter_tolerances']:
                                    min_tolerance = self.check_criteria['phase_shifter_tolerances'][fv_angle]['min']
                                    max_tolerance = self.check_criteria['phase_shifter_tolerances'][fv_angle]['max']
                                    fv_ok = min_tolerance <= fv_diff <= max_tolerance
                                else:
                                    fv_ok = -2.0 <= fv_diff <= 2.0
                                individual_fv_ok.append(fv_ok)
                        
                        phase_final_ok = len(individual_fv_ok) > 0 and all(individual_fv_ok)
                    else:
                        phase_final_ok = False

                overall_status = "ok" if (amp_ok and phase_final_ok) else "fail"
            
            self.ppm_field_view.update_ppm(ppm_num, overall_status)

            self.results_table.viewport().update()
            # Убираем processEvents() - Qt сам обработает события GUI
        except Exception as e:
            self.show_error_message("Ошибка обновления таблицы", f"Ошибка при обновлении данных ППМ {ppm_num}: {str(e)}")
            logger.error(f'Ошибка при обновлении значений ФВ для ППМ {ppm_num}: {e}')
            for i in range(6):
                self.results_table.setItem(row, i + 5, QtWidgets.QTableWidgetItem(""))

    @QtCore.pyqtSlot()
    def on_check_finished(self):
        """Слот для завершения проверки - выполняется в главном потоке GUI"""
        self.set_buttons_enabled(True)
        self.pause_btn.setText('Пауза')
        logger.info('Проверка завершена, интерфейс восстановлен')

    @QtCore.pyqtSlot(bool)
    def set_buttons_enabled(self, enabled: bool):
        """Управляет доступностью кнопок"""
        self.ma_connect_btn.setEnabled(enabled)
        self.pna_connect_btn.setEnabled(enabled)
        self.psn_connect_btn.setEnabled(enabled)
        self.apply_btn.setEnabled(enabled)
        self.start_btn.setEnabled(enabled)
        self.stop_btn.setEnabled(not enabled)
        self.pause_btn.setEnabled(not enabled)

    def set_button_connection_state(self, button: QtWidgets.QPushButton, connected: bool):
        """Устанавливает состояние подключения кнопки"""
        if connected:
            # Зеленый фон для подключенного состояния
            button.setStyleSheet("QPushButton { background-color: #28a745; color: white; }")
        else:
            # Красный фон для отключенного состояния
            button.setStyleSheet("QPushButton { background-color: #dc3545; color: white; }")
    
    def create_status_table_item(self, text: str, is_success: bool) -> QtWidgets.QTableWidgetItem:
        item = QtWidgets.QTableWidgetItem(text)
        item.setTextAlignment(QtCore.Qt.AlignCenter)
        if is_success:
            item.setBackground(QtGui.QColor("#d4edda"))
            item.setForeground(QtGui.QColor("#155724"))
        else:
            item.setBackground(QtGui.QColor("#f8d7da"))
            item.setForeground(QtGui.QColor("#721c24"))


        item.setFlags(item.flags() & ~QtCore.Qt.ItemIsEditable)
        
        return item
    
    def create_centered_table_item(self, text: str) -> QtWidgets.QTableWidgetItem:
        """Создает центрированную ячейку таблицы"""
        item = QtWidgets.QTableWidgetItem(text)
        item.setTextAlignment(QtCore.Qt.AlignCenter)
        item.setFlags(item.flags() & ~QtCore.Qt.ItemIsEditable)
        return item
    
    def create_neutral_status_item(self, text: str = "-") -> QtWidgets.QTableWidgetItem:
        """Создает нейтральную ячейку статуса для случаев отсутствия данных"""
        item = QtWidgets.QTableWidgetItem(text)
        item.setTextAlignment(QtCore.Qt.AlignCenter)

        item.setBackground(QtGui.QColor("#f8f9fa"))
        item.setForeground(QtGui.QColor("#6c757d"))

        item.setFlags(item.flags() & ~QtCore.Qt.ItemIsEditable)
        
        return item

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
        
        # Meas - критерии проверки
        self.check_criteria = {
            'rx_amp_max': self.rx_amp_tolerance.value(),
            'tx_amp_max': self.tx_amp_tolerance.value(),
            'rx_phase_min': self.rx_phase_min.value(),
            'rx_phase_max': self.rx_phase_max.value(),
            'tx_phase_min': self.tx_phase_min.value(),
            'tx_phase_max': self.tx_phase_max.value(),
            'phase_shifter_tolerances': {}
        }
        
        # Сохраняем допуски для каждого фазовращателя
        for angle, controls in self.phase_shifter_tolerances.items():
            self.check_criteria['phase_shifter_tolerances'][angle] = {
                'min': controls['min'].value(),
                'max': controls['max'].value()
            }

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
        self.pause_btn.setText('Пауза')
        
        self.results_table.clearContents()
        for row in range(32):
            self.results_table.setItem(row, 0, self.create_centered_table_item(str(row+1)))
            for col in range(1, 12):
                self.results_table.setItem(row, col, QtWidgets.QTableWidgetItem(""))

        self.ppm_data.clear()
        self.bottom_rect_data.clear()
        for ppm_num, button in self.ppm_field_view.rects.items():
            button.set_status('')
        
        # Сбрасываем состояние нижнего прямоугольника
        self.ppm_field_view.update_bottom_rect_status('')

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
        self._pause_flag.clear() # Ensure pause is cleared for next run
        self.pause_btn.setText('Пауза') # Reset pause button text
        self.set_buttons_enabled(True)
        logger.info('Проверка остановлена.')

    def _run_check(self):
        logger.info("Начало выполнения проверки в отдельном потоке")
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

            class CheckMAWithCallback(CheckMA):
                def __init__(self, ma, psn, pna, stop_event, pause_event, callback, criteria=None):
                    super().__init__(ma, psn, pna, stop_event, pause_event)
                    self.callback = callback
                    
                    # Применяем новые критерии проверки если они переданы
                    if criteria:
                        self.rx_amp_max = criteria.get('rx_amp_max', self.rx_amp_max)
                        self.tx_amp_max = criteria.get('tx_amp_max', self.tx_amp_max)
                        self.rx_phase_diff_min = criteria.get('rx_phase_min', self.rx_phase_diff_min)
                        self.rx_phase_diff_max = criteria.get('rx_phase_max', self.rx_phase_diff_max)
                        self.tx_phase_diff_min = criteria.get('tx_phase_min', self.tx_phase_diff_min)
                        self.tx_phase_diff_max = criteria.get('tx_phase_max', self.tx_phase_diff_max)
                        self.phase_shifter_tolerances = criteria.get('phase_shifter_tolerances', None)
                
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
                callback=self.update_table_signal,
                criteria=self.check_criteria
            )

            check.start(channel=channel, direction=direction)

            if not self._stop_flag.is_set():
                logger.info('Проверка завершена успешно.')

        except Exception as e:
            # Используем сигнал для показа ошибки из потока
            self.error_signal.emit("Ошибка проверки", f"Произошла ошибка при выполнении проверки: {str(e)}")
            logger.error(f"Ошибка при выполнении проверки: {e}")
            try:
                if self.pna:
                    self.pna.power_off()
            except Exception as pna_error:
                logger.error(f"Ошибка при аварийном выключении PNA: {pna_error}")
        finally:
            # Используем сигнал для восстановления интерфейса из потока
            self.check_finished_signal.emit()

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
        """Подключает/отключает PNA"""
        if self.pna and self.pna.connection:
            try:
                self.pna.disconnect()
                self.pna = None
                self.set_button_connection_state(self.pna_connect_btn, False)
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
            self.set_button_connection_state(self.pna_connect_btn, True)
            logger.info(f'PNA успешно подключен {"" if mode == 0 else "(тестовый режим)"}')
        except Exception as e:
            self.pna = None
            self.set_button_connection_state(self.pna_connect_btn, False)
            self.show_error_message("Ошибка подключения PNA", f"Не удалось подключиться к PNA: {str(e)}")

    def connect_psn(self):
        """Подключает/отключает PSN"""
        if self.psn and self.psn.connection:
            try:
                self.psn.disconnect()
                self.psn = None
                self.set_button_connection_state(self.psn_connect_btn, False)
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
            self.set_button_connection_state(self.psn_connect_btn, True)
            logger.info(f'PSN успешно подключен {"" if mode == 0 else "(тестовый режим)"}')
        except Exception as e:
            self.psn = None
            self.set_button_connection_state(self.psn_connect_btn, False)
            self.show_error_message("Ошибка подключения PSN", f"Не удалось подключиться к PSN: {str(e)}")

    def set_device_settings(self, settings: dict):
        """Сохраняет параметры устройств из настроек для последующего применения."""
        self.device_settings = settings or {}
        logger.info('Настройки устройств обновлены в CheckMaWidget')
        logger.debug(f'Новые настройки: {self.device_settings}')

    def show_ppm_details_graphics(self, ppm_num, global_pos):
        if ppm_num not in self.ppm_data:
            menu = QtWidgets.QMenu()
            action = menu.addAction(f"ППМ {ppm_num} - данные не готовы")
            action.setEnabled(False)
            menu.exec_(global_pos)
            return
        
        data = self.ppm_data[ppm_num]
        menu = QtWidgets.QMenu()

        status_text = "OK" if data['result'] else "FAIL"
        status_color = "🟢" if data['result'] else "🔴"
        header_action = menu.addAction(f"{status_color} ППМ {ppm_num} - {status_text}")
        header_action.setEnabled(False)
        menu.addSeparator()

        if not np.isnan(data['amp']):
            amp_action = menu.addAction(f"Амплитуда: {data['amp']:.2f} дБ")
        else:
            amp_action = menu.addAction("Амплитуда: ---")
        amp_action.setEnabled(False)

        if not np.isnan(data['phase']):
            phase_action = menu.addAction(f"Фаза: {data['phase']:.1f}°")
        else:
            phase_action = menu.addAction("Фаза: ---")
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
                        fv_action = menu.addAction(f"  ФВ {i+1}: {value:.1f}°")
                    else:
                        fv_action = menu.addAction(f"  ФВ {i+1}: ---")
                    fv_action.setEnabled(False)
        
        menu.exec_(global_pos) 

    def show_bottom_rect_details(self, global_pos):
        """Показывает контекстное меню для нижнего прямоугольника (Линии задержки)"""
        menu = QtWidgets.QMenu()
        
        header_action = menu.addAction("Линии задержки")
        header_action.setEnabled(False)
        menu.addSeparator()
        
        if self.bottom_rect_data:
            # Если есть данные - отобразим их
            for key, value in self.bottom_rect_data.items():
                data_action = menu.addAction(f"{key}: {value}")
                data_action.setEnabled(False)
        else:
            # Если данных нет - показываем заглушку
            info_action = menu.addAction("Данные будут добавлены позже...")
            info_action.setEnabled(False)
        
        menu.exec_(global_pos)

    def update_bottom_rect_data(self, data: dict):
        """Обновляет данные для нижнего прямоугольника (Линии задержки)"""
        self.bottom_rect_data = data

        self.ppm_field_view.update_bottom_rect_status("ok" if data else "")

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

    @QtCore.pyqtSlot(str, str)
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

