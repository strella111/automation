"""
Диалог выбора файлов настроек PNA
"""

from PyQt5 import QtWidgets, QtCore
from loguru import logger
from typing import Optional


class PnaFileDialog(QtWidgets.QDialog):
    """Диалог для выбора файлов настроек PNA"""
    
    def __init__(self, pna, files_path: str = "", parent=None):
        super().__init__(parent)
        self.pna = pna
        self.files_path = files_path or "C:\\Users\\Public\\Documents\\Network Analyzer\\"
        self.selected_file = None
        self.parsed_settings = {}
        
        self.setWindowTitle('Выбор файла настроек PNA')
        self.setModal(True)
        self.resize(600, 500)
        self.init_ui()
        self.load_files()
        
    def init_ui(self):
        """Инициализация интерфейса"""
        layout = QtWidgets.QVBoxLayout(self)
        layout.setSpacing(16)
        layout.setContentsMargins(16, 16, 16, 16)

        title = QtWidgets.QLabel('Выберите файл настроек PNA')
        title.setStyleSheet('font-size: 16px; font-weight: bold; margin-bottom: 8px;')
        layout.addWidget(title)

        path_layout = QtWidgets.QHBoxLayout()
        path_label = QtWidgets.QLabel('Путь:')
        self.path_edit = QtWidgets.QLineEdit(self.files_path)
        self.refresh_btn = QtWidgets.QPushButton('Обновить')
        self.refresh_btn.clicked.connect(self.load_files)
        
        path_layout.addWidget(path_label)
        path_layout.addWidget(self.path_edit)
        path_layout.addWidget(self.refresh_btn)
        layout.addLayout(path_layout)

        self.file_list = QtWidgets.QListWidget()
        self.file_list.itemDoubleClicked.connect(self.accept)
        layout.addWidget(self.file_list)

        self.status_label = QtWidgets.QLabel('Загрузка файлов...')
        self.status_label.setStyleSheet('color: #666; font-size: 12px;')
        layout.addWidget(self.status_label)

        button_layout = QtWidgets.QHBoxLayout()
        button_layout.addStretch()
        
        cancel_btn = QtWidgets.QPushButton('Отмена')
        cancel_btn.clicked.connect(self.reject)

        self.apply_btn = QtWidgets.QPushButton('Выбрать и применить')
        self.apply_btn.clicked.connect(self.select_and_apply)
        self.apply_btn.setEnabled(False)
        
        button_layout.addWidget(cancel_btn)
        button_layout.addWidget(self.apply_btn)
        
        layout.addLayout(button_layout)

        self.file_list.itemSelectionChanged.connect(self.on_selection_changed)
        
    def load_files(self):
        """Загрузка списка файлов из PNA"""
        try:
            self.status_label.setText('Загрузка файлов...')
            self.file_list.clear()

            self.files_path = self.path_edit.text().strip()
            if not self.files_path:
                self.files_path = "C:\\Users\\Public\\Documents\\Network Analyzer\\"
                self.path_edit.setText(self.files_path)
            
            if not self.pna or not self.pna.connection:
                self.status_label.setText('PNA не подключен')
                return

            files = self.pna.get_files_in_dir(self.files_path)
            
            if not files:
                self.status_label.setText('Файлы не найдены')
                return

            settings_files = []
            for file in files:
                file_clean = file.strip().strip('"').strip("'")
                if file_clean and any(file_clean.lower().endswith(ext) for ext in ['.csa']):
                    settings_files.append(file_clean)
            
            if not settings_files:
                self.status_label.setText('Файлы настроек не найдены')
                return

            for file in sorted(settings_files):
                item = QtWidgets.QListWidgetItem(file)
                item.setToolTip(f"Файл настроек: {file}")
                self.file_list.addItem(item)
                
            self.status_label.setText(f'Найдено файлов: {len(settings_files)}')
            logger.info(f'Загружено {len(settings_files)} файлов настроек PNA')
            
        except Exception as e:
            error_msg = f'Ошибка загрузки файлов: {e}'
            self.status_label.setText(error_msg)
            logger.error(error_msg)
            
    def on_selection_changed(self):
        """Обработчик изменения выбора файла"""
        has_selection = bool(self.file_list.currentItem())
        self.apply_btn.setEnabled(has_selection)

        
    def get_selected_file(self) -> Optional[str]:
        """Получение выбранного файла"""
        current_item = self.file_list.currentItem()
        if current_item:
            return current_item.text()
        return None
        
    def get_full_file_path(self) -> Optional[str]:
        """Получение полного пути к выбранному файлу"""
        selected_file = self.get_selected_file()
        if selected_file:
            # Убираем лишние слеши в конце пути
            path = self.files_path.rstrip('\\').rstrip('/')
            return f"{path}\\{selected_file}"
        return None
        
    def select_and_apply(self):
        """Выбор файла и его применение"""
        try:
            file_path = self.get_full_file_path()
            if not file_path:
                QtWidgets.QMessageBox.warning(self, 'Предупреждение', 'Выберите файл настроек')
                return
                
            if not self.pna or not self.pna.connection:
                QtWidgets.QMessageBox.warning(self, 'Ошибка', 'PNA не подключен')
                return

            self.pna.load_settings_file(file_path)
            
            QtWidgets.QMessageBox.information(
                self, 
                'Успех', 
                f'Файл настроек "{self.get_selected_file()}" успешно применен'
            )
            
            self.selected_file = self.get_selected_file()
            self.accept()
            
        except Exception as e:
            error_msg = f'Ошибка применения файла настроек: {e}'
            QtWidgets.QMessageBox.critical(self, 'Ошибка', error_msg)
            logger.error(error_msg)
