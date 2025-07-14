import json
import os
from typing import Dict, Any, Optional
from PyQt5.QtWidgets import QApplication, QStyle
from PyQt5.QtGui import QIcon


class StyleManager:
    """
    Менеджер стилей для PyQt5 приложения.
    Позволяет загружать и применять CSS-подобные стили из JSON файлов.
    """
    
    def __init__(self):
        self.current_theme: Dict[str, Any] = {}
        self.styles_dir = os.path.dirname(os.path.abspath(__file__))
        self.icons_dir = os.path.join(self.styles_dir, 'icons')
    
    def load_theme(self, theme_name: str) -> bool:
        """
        Загружает тему из JSON файла.
        
        Args:
            theme_name: Имя темы (имя файла без расширения)
            
        Returns:
            True если тема успешно загружена, False иначе
        """
        theme_path = os.path.join(self.styles_dir, f"{theme_name}.json")
        
        try:
            with open(theme_path, 'r', encoding='utf-8') as f:
                self.current_theme = json.load(f)
            return True
        except (FileNotFoundError, json.JSONDecodeError) as e:
            print(f"Ошибка загрузки темы {theme_name}: {e}")
            return False
    
    def get_style(self, widget_type: str) -> str:
        """
        Получает CSS стиль для указанного типа виджета.
        
        Args:
            widget_type: Тип виджета (например, 'QPushButton', 'QMainWindow')
            
        Returns:
            CSS строка стиля
        """
        return self.current_theme.get(widget_type, "")
    
    def get_icon_path(self, icon_name: str) -> str:
        """
        Получает полный путь к иконке.
        
        Args:
            icon_name: Имя файла иконки
            
        Returns:
            Полный путь к иконке
        """
        return os.path.join(self.icons_dir, icon_name).replace('\\', '/')
    
    def apply_builtin_arrows(self, app: QApplication):
        """
        Применяет встроенные иконки Qt для стрелочек.
        """
        # Получаем встроенные иконки Qt
        style = app.style()
        if not style:
            return
        
        # Создаем иконки
        up_icon = style.standardIcon(QStyle.StandardPixmap.SP_ArrowUp)
        down_icon = style.standardIcon(QStyle.StandardPixmap.SP_ArrowDown)
        
        # Сохраняем иконки в папку для использования в CSS
        icons_dir = self.icons_dir
        os.makedirs(icons_dir, exist_ok=True)
        
        # Создаем pixmap больших размеров для лучшей видимости
        up_pixmap = up_icon.pixmap(20, 20)  # Увеличиваем размер для четкости
        down_pixmap = down_icon.pixmap(20, 20)
        
        up_path = os.path.join(icons_dir, 'qt_arrow_up.png')
        down_path = os.path.join(icons_dir, 'qt_arrow_down.png')
        
        up_pixmap.save(up_path)
        down_pixmap.save(down_path)
        
        up_relative = 'src/ui/styles/icons/qt_arrow_up.png'
        down_relative = 'src/ui/styles/icons/qt_arrow_down.png'
        
        self.current_theme['QComboBox::down-arrow'] = f"image: url({down_relative}); width: 16px; height: 16px; subcontrol-origin: padding; subcontrol-position: center;"
        self.current_theme['QSpinBox::up-arrow'] = f"image: url({up_relative}); width: 16px; height: 16px; subcontrol-origin: padding; subcontrol-position: center;"
        self.current_theme['QSpinBox::down-arrow'] = f"image: url({down_relative}); width: 16px; height: 16px; subcontrol-origin: padding; subcontrol-position: center;"
        self.current_theme['QDoubleSpinBox::up-arrow'] = f"image: url({up_relative}); width: 16px; height: 16px; subcontrol-origin: padding; subcontrol-position: center;"
        self.current_theme['QDoubleSpinBox::down-arrow'] = f"image: url({down_relative}); width: 16px; height: 16px; subcontrol-origin: padding; subcontrol-position: center;"
    
    def apply_to_application(self, app: QApplication):
        """
        Применяет глобальные стили ко всему приложению.
        
        Args:
            app: Объект QApplication
        """
        if not self.current_theme:
            return
            
        # Собираем все стили в одну CSS строку
        css_styles = []
        
        # Список селекторов Qt виджетов (игнорируем кастомные стили)
        qt_selectors = [
            'QMainWindow', 'QWidget', 'QPushButton', 'QPushButton:hover', 'QPushButton:pressed', 'QPushButton:disabled',
            'QPushButton[iconButton="true"]', 'QPushButton[iconButton="true"]:hover', 'QPushButton[iconButton="true"]:pressed',
            'QLineEdit', 'QLineEdit:focus', 'QLineEdit:hover', 'QLineEdit:disabled',
            'QComboBox', 'QComboBox:hover', 'QComboBox:focus', 'QComboBox::drop-down', 'QComboBox::drop-down:hover', 'QComboBox::down-arrow', 'QComboBox QAbstractItemView',
            'QSpinBox', 'QSpinBox:focus', 'QSpinBox:hover', 'QSpinBox::up-button', 'QSpinBox::down-button', 
            'QSpinBox::up-button:hover', 'QSpinBox::down-button:hover', 'QSpinBox::up-button:pressed', 'QSpinBox::down-button:pressed', 'QSpinBox::up-arrow', 'QSpinBox::down-arrow',
            'QDoubleSpinBox', 'QDoubleSpinBox:focus', 'QDoubleSpinBox:hover', 'QDoubleSpinBox::up-button', 'QDoubleSpinBox::down-button',
            'QDoubleSpinBox::up-button:hover', 'QDoubleSpinBox::down-button:hover', 'QDoubleSpinBox::up-button:pressed', 'QDoubleSpinBox::down-button:pressed', 'QDoubleSpinBox::up-arrow', 'QDoubleSpinBox::down-arrow',
            'QLabel', 'QGroupBox', 'QGroupBox::title', 'QTabWidget::pane',
            'QTabBar::tab', 'QTabBar::tab:selected', 'QTabBar::tab:hover', 
            'QTextEdit', 'QTextEdit:focus', 'QTableWidget', 'QTableWidget::item', 'QTableWidget::item:selected', 'QTableWidget::item:hover',
            'QHeaderView::section', 'QHeaderView::section:first', 'QHeaderView::section:last', 'QHeaderView::section:hover',
            'QGraphicsView', 'QGraphicsView:focus'
        ]
        
        for widget_type, style in self.current_theme.items():
            if isinstance(style, str) and style.strip() and widget_type in qt_selectors:
                css_styles.append(f"{widget_type} {{ {style} }}")
        
        full_stylesheet = "\n\n".join(css_styles)
        app.setStyleSheet(full_stylesheet)
        print(f"Применяются стили: {len(css_styles)} правил")
    
    def apply_to_widget(self, widget, widget_type: Optional[str] = None):
        """
        Применяет стиль к конкретному виджету.
        
        Args:
            widget: Виджет PyQt5
            widget_type: Тип виджета. Если не указан, определяется автоматически
        """
        actual_widget_type = widget_type if widget_type is not None else widget.__class__.__name__
        style = self.get_style(actual_widget_type)
        if style:
            widget.setStyleSheet(style)
    
    def get_available_themes(self) -> list:
        """
        Возвращает список доступных тем.
        
        Returns:
            Список имен тем
        """
        themes = []
        for file in os.listdir(self.styles_dir):
            if file.endswith('.json'):
                themes.append(file[:-5])  # убираем .json
        return themes


# Глобальный экземпляр менеджера стилей
style_manager = StyleManager() 