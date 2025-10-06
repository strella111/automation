"""
Компоненты для отображения 2D поля ППМ
"""
from PyQt5 import QtWidgets, QtCore, QtGui


class PpmRect(QtWidgets.QGraphicsRectItem):
    """Прямоугольник для отображения ППМ"""
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
        self._hover_prev_color = QtGui.QColor(245, 248, 252)

    def set_status(self, status):
        # Нормализация входного статуса: поддержка bool и строк в любом регистре
        if isinstance(status, bool):
            norm = 'ok' if status else 'fail'
        elif isinstance(status, str):
            norm = status.strip().lower()
        else:
            norm = 'fail' if not status else 'ok'

        if norm == "ok":
            color = "#28a745"  # зеленый
        elif norm == "fail":
            color = "#dc3545"  # красный
        else:
            color = "#f8f9fa"  # серый по умолчанию
        
        self.setBrush(QtGui.QBrush(QtGui.QColor(color)))
        self.status = norm

    def hoverEnterEvent(self, event):
        """Подсветка при наведении мыши"""
        hover_color = "#e9ecef"

        if self.status == "ok":
            hover_color = "#28a745"  # зеленый
        elif self.status == "fail":
            hover_color = "#dc3545"  # красный

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
    """Прямоугольник для отображения линий задержки"""
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
            
        qcolor = QtGui.QColor(color)
        self.setBrush(QtGui.QBrush(qcolor))
        self.status = status
        self._hover_prev_color = qcolor

    def hoverEnterEvent(self, event):
        """Подсветка при наведении мыши"""
        self._hover_prev_color = self.brush().color()
        lighter = QtGui.QColor(self._hover_prev_color)
        lighter = lighter.lighter(110)
        self.setBrush(QtGui.QBrush(lighter))
        super().hoverEnterEvent(event)

    def hoverLeaveEvent(self, event):
        """Восстанавливаем цвет при уходе мыши"""
        if self._hover_prev_color is not None:
            self.setBrush(QtGui.QBrush(self._hover_prev_color))
        super().hoverLeaveEvent(event)

    def mousePressEvent(self, event):
        if event.button() == QtCore.Qt.LeftButton:
            self.setSelected(True)
        super().mousePressEvent(event)


class PpmFieldView(QtWidgets.QGraphicsView):
    """Вид для отображения 2D поля ППМ"""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setScene(QtWidgets.QGraphicsScene(self))
        self.rects = {}
        self.texts = {}
        self.bottom_rect = None
        self.bottom_text = None
        self.bottom_rect_height = 70
        self.setRenderHint(QtGui.QPainter.Antialiasing)
        self.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        self.parent_widget = parent
        self.create_rects()

        self.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
        self.customContextMenuRequested.connect(self.show_context_menu)

    def create_rects(self):
        self.scene().clear()
        self.rects.clear()
        self.texts.clear()

        text_color = "#212529"
        font_size = 10

        for col in range(4):
            for row in range(8):
                ppm_num = col * 8 + row + 1
                rect = PpmRect(ppm_num, self.parent_widget, 0, 0, 1, 1)
                self.scene().addItem(rect)
                self.rects[ppm_num] = rect
                # Явно устанавливаем нейтральный статус до старта измерений
                rect.set_status("")

                font = QtGui.QFont("Segoe UI", font_size, QtGui.QFont.Weight.DemiBold)
                text = self.scene().addText(f"ППМ {ppm_num}", font)
                text.setDefaultTextColor(QtGui.QColor(text_color))
                self.texts[ppm_num] = text

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

        if self.bottom_rect:
            bottom_y = 8 * h + 2
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
        total_height = self.viewport().height()
        ppm_area_height = total_height - self.bottom_rect_height - 4  # 4 пикселя отступ
        
        w = self.viewport().width() / 4
        h = ppm_area_height / 8
        margin = 2

        bottom_y = 8 * h + 2  # 2 пикселя отступ сверху
        if pos.y() >= bottom_y and pos.y() <= (bottom_y + self.bottom_rect_height - margin):
            bottom_w = 4 * w - margin
            if pos.x() >= margin/2 and pos.x() <= (margin/2 + bottom_w):
                return "bottom_rect"  # Специальное значение для нижнего прямоугольника

        col = int(pos.x() / w)
        row = int(pos.y() / h)

        if 0 <= col < 4 and 0 <= row < 8:
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
                if self.bottom_rect:
                    self.bottom_rect.setSelected(True)
                self.parent_widget.show_bottom_rect_details(self.mapToGlobal(pos))
            else:
                ppm_num = element
                if ppm_num in self.rects:
                    self.rects[ppm_num].setSelected(True)
                self.parent_widget.show_ppm_details_graphics(ppm_num, self.mapToGlobal(pos))
