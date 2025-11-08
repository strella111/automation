from PyQt5 import QtWidgets, QtCore
from ui.widgets.phase_ma_widget import PhaseMaWidget
from ui.widgets.check_ma_widget import CheckMaWidget
from ui.widgets.check_stend_ma_widget import StendCheckMaWidget
from ui.widgets.phase_afar_widget import PhaseAfarWidget
from ui.widgets.beam_pattern_widget import BeamPatternWidget
from ui.widgets.check_stend_afar_widget import StendCheckAfarWidget
from ui.widgets.manual_control_widget import ManualControlWindow
from ui.widgets.manual_control_afar_widget import ManualControlAfarWindow
from ui.dialogs.settings_dialog import SettingsDialog
from config.settings_manager import get_main_settings
from loguru import logger

class MainWindow(QtWidgets.QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle('Automation Tool')
        
        # Инициализируем настройки сразу
        self.settings = get_main_settings()
        
        # Восстанавливаем размер и положение окна
        geometry = self.settings.value('window_geometry')
        if geometry:
            self.restoreGeometry(geometry)
        else:
            self.resize(1400, 800)
        
        # Восстанавливаем состояние окна (сплиттеры, toolbar и т.д.)
        state = self.settings.value('window_state')
        if state:
            self.restoreState(state)
        
        # Устанавливаем иконку приложения
        from PyQt5.QtGui import QIcon
        import sys
        import os
        if getattr(sys, 'frozen', False):
            # Если запущено из EXE
            base_path = sys._MEIPASS
        else:
            # Если запущено из исходников
            base_path = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        
        # Пробуем загрузить PNG, если нет - ICO
        icon_path_png = os.path.join(base_path, 'icon', 'Logo.png')
        icon_path_ico = os.path.join(base_path, 'icon', 'Logo.ico')
        
        if os.path.exists(icon_path_png):
            self.setWindowIcon(QIcon(icon_path_png))
        elif os.path.exists(icon_path_ico):
            self.setWindowIcon(QIcon(icon_path_ico))

        self.menu_bar = QtWidgets.QMenuBar(self)
        self.setMenuBar(self.menu_bar)
        self.menu_mode = self.menu_bar.addMenu('Режим')
        self.menu_utils = self.menu_bar.addMenu('Утилиты')
        self.menu_params = self.menu_bar.addMenu('Параметры')
        
        # Индикатор текущего режима в правом углу меню
        self.mode_indicator = QtWidgets.QLabel('Проверка МА (БЭК)')
        self.mode_indicator.setStyleSheet("""
            QLabel {
                background-color: #4CAF50;
                color: white;
                padding: 6px 15px;
                border-radius: 4px;
                font-weight: bold;
                font-size: 13px;
                margin-right: 5px;
            }
        """)
        self.mode_indicator.setMinimumWidth(160)
        self.mode_indicator.setMaximumWidth(280)
        self.mode_indicator.setAlignment(QtCore.Qt.AlignCenter)
        self.menu_bar.setCornerWidget(self.mode_indicator, QtCore.Qt.TopRightCorner)

        # --- Центральная область (режимы) ---
        self.central_widget = QtWidgets.QStackedWidget()
        self.setCentralWidget(self.central_widget)

        # --- Виджеты режимов ---
        self.phase_ma_widget = PhaseMaWidget()
        self.check_ma_widget = CheckMaWidget()
        self.check_stend_ma_widget = StendCheckMaWidget()
        self.phase_afar_widget = PhaseAfarWidget()
        self.beam_pattern_widget = BeamPatternWidget()
        self.check_stend_afar_widget = StendCheckAfarWidget()
        self.central_widget.addWidget(self.phase_ma_widget)
        self.central_widget.addWidget(self.check_ma_widget)
        self.central_widget.addWidget(self.check_stend_ma_widget)
        self.central_widget.addWidget(self.phase_afar_widget)
        self.central_widget.addWidget(self.beam_pattern_widget)
        self.central_widget.addWidget(self.check_stend_afar_widget)

        # --- Привязка меню ---
        # Создаем подменю для МА
        self.ma_submenu = self.menu_mode.addMenu('МА')
        
        self.phase_action = self.ma_submenu.addAction('Фазировка МА в БЭК')
        self.phase_action.setCheckable(True)
        self.phase_action.triggered.connect(self.show_phase_ma)

        self.check_bek_action = self.ma_submenu.addAction('Проверка МА в БЭК')
        self.check_bek_action.setCheckable(True)
        self.check_bek_action.triggered.connect(self.show_check_ma)

        self.check_stend_action = self.ma_submenu.addAction('Проверка МА на стенде')
        self.check_stend_action.setCheckable(True)
        self.check_stend_action.triggered.connect(self.show_check_stend_ma)

        # Создаем подменю для АФАР
        self.afar_submenu = self.menu_mode.addMenu('АФАР')
        
        self.phase_afar_action = self.afar_submenu.addAction('Фазировка АФАР')
        self.phase_afar_action.setCheckable(True)
        self.phase_afar_action.triggered.connect(self.show_phase_afar)
        
        self.beam_pattern_action = self.afar_submenu.addAction('Измерение лучей АФАР')
        self.beam_pattern_action.setCheckable(True)
        self.beam_pattern_action.triggered.connect(self.show_beam_pattern)
        
        self.check_stend_afar_action = self.afar_submenu.addAction('Измерение через калибровку')
        self.check_stend_afar_action.setCheckable(True)
        self.check_stend_afar_action.triggered.connect(self.show_check_stend_afar)

        # Группа для взаимоисключающих действий
        mode_group = QtWidgets.QActionGroup(self)
        mode_group.addAction(self.phase_action)
        mode_group.addAction(self.check_bek_action)
        mode_group.addAction(self.check_stend_action)
        mode_group.addAction(self.phase_afar_action)
        mode_group.addAction(self.beam_pattern_action)
        mode_group.addAction(self.check_stend_afar_action)
        mode_group.setExclusive(True)
        
        self.menu_params.addAction('Настройки устройств', self.open_settings_dialog)
        # --- Утилиты ---
        self.action_manual_control = self.menu_utils.addAction('Ручное управление')
        self.action_manual_control.triggered.connect(self.open_manual_control)

        # Восстанавливаем состояние интерфейса
        self.restore_ui_state()
        
        # Загружаем настройки устройств
        self.load_settings()

        # Ссылки на окна ручного управления, чтобы не собирались GC
        self._manual_control_ma_window = None
        self._manual_control_afar_window = None

    def restore_ui_state(self):
        """Восстанавливает состояние интерфейса"""
        # Восстанавливаем размер и позицию окна
        self.restoreGeometry(self.settings.value('window_geometry', b''))
        self.restoreState(self.settings.value('window_state', b''))
        
        # Восстанавливаем выбранную вкладку
        last_mode = self.settings.value('last_mode', 'check')  # По умолчанию - проверка в БЭК
        if last_mode == 'phase':
            self.show_phase_ma()
        elif last_mode == 'check_stend':
            self.show_check_stend_ma()
        elif last_mode == 'phase_afar':
            self.show_phase_afar()
        elif last_mode == 'beam_pattern':
            self.show_beam_pattern()
        elif last_mode == 'check_stend_afar':
            self.show_check_stend_afar()
        else:
            self.show_check_ma()

    def closeEvent(self, event):
        """Сохраняет состояние при закрытии окна"""
        self.settings.setValue('window_geometry', self.saveGeometry())
        self.settings.setValue('window_state', self.saveState())
        
        # Сохраняем текущую вкладку
        if self.central_widget.currentWidget() == self.phase_ma_widget:
            self.settings.setValue('last_mode', 'phase')
        elif self.central_widget.currentWidget() == self.check_stend_ma_widget:
            self.settings.setValue('last_mode', 'check_stend')
        elif self.central_widget.currentWidget() == self.phase_afar_widget:
            self.settings.setValue('last_mode', 'phase_afar')
        elif self.central_widget.currentWidget() == self.beam_pattern_widget:
            self.settings.setValue('last_mode', 'beam_pattern')
        elif self.central_widget.currentWidget() == self.check_stend_afar_widget:
            self.settings.setValue('last_mode', 'check_stend_afar')
        else:
            self.settings.setValue('last_mode', 'check')
            
        self.settings.sync()
        super().closeEvent(event)
        
    def _disconnect_current_widget_devices(self):
        """Отключает все устройства у текущего активного виджета"""
        current_widget = self.central_widget.currentWidget()
        if current_widget and hasattr(current_widget, 'disconnect_all_devices'):
            try:
                current_widget.disconnect_all_devices()
            except Exception as e:
                logger.error(f"Ошибка при отключении устройств: {e}")

    def show_phase_ma(self):
        self._disconnect_current_widget_devices()
        self.central_widget.setCurrentWidget(self.phase_ma_widget)
        self.phase_action.setChecked(True)
        self.mode_indicator.setText('Фазировка МА (БЭК)')
        self.mode_indicator.setStyleSheet("""
            QLabel {
                background-color: #2196F3;
                color: white;
                padding: 6px 15px;
                border-radius: 4px;
                font-weight: bold;
                font-size: 13px;
                margin-right: 5px;
            }
        """)

    def show_check_ma(self):
        self._disconnect_current_widget_devices()
        self.central_widget.setCurrentWidget(self.check_ma_widget)
        self.check_bek_action.setChecked(True)
        self.mode_indicator.setText('Проверка МА (БЭК)')
        self.mode_indicator.setStyleSheet("""
            QLabel {
                background-color: #4CAF50;
                color: white;
                padding: 6px 15px;
                border-radius: 4px;
                font-weight: bold;
                font-size: 13px;
                margin-right: 5px;
            }
        """)

    def show_check_stend_ma(self):
        self._disconnect_current_widget_devices()
        self.central_widget.setCurrentWidget(self.check_stend_ma_widget)
        self.check_stend_action.setChecked(True)
        self.mode_indicator.setText('Проверка МА (Стенд)')
        self.mode_indicator.setStyleSheet("""
            QLabel {
                background-color: #FF9800;
                color: white;
                padding: 6px 15px;
                border-radius: 4px;
                font-weight: bold;
                font-size: 13px;
                margin-right: 5px;
            }
        """)

    def show_phase_afar(self):
        self._disconnect_current_widget_devices()
        self.central_widget.setCurrentWidget(self.phase_afar_widget)
        self.phase_afar_action.setChecked(True)
        self.mode_indicator.setText('Фазировка АФАР')
        self.mode_indicator.setStyleSheet("""
            QLabel {
                background-color: #9C27B0;
                color: white;
                padding: 6px 15px;
                border-radius: 4px;
                font-weight: bold;
                font-size: 13px;
                margin-right: 5px;
            }
        """)
    
    def show_beam_pattern(self):
        self._disconnect_current_widget_devices()
        self.central_widget.setCurrentWidget(self.beam_pattern_widget)
        self.beam_pattern_action.setChecked(True)
        self.mode_indicator.setText('Измерение лучей')
        self.mode_indicator.setStyleSheet("""
            QLabel {
                background-color: #E91E63;
                color: white;
                padding: 6px 15px;
                border-radius: 4px;
                font-weight: bold;
                font-size: 13px;
                margin-right: 5px;
            }
        """)

    def show_check_stend_afar(self):
        self._disconnect_current_widget_devices()
        self.central_widget.setCurrentWidget(self.check_stend_afar_widget)
        self.check_stend_afar_action.setChecked(True)
        self.mode_indicator.setText('Измерение через калибровку')
        self.mode_indicator.setStyleSheet("""
            QLabel {
                background-color: #FF9800;
                color: white;
                padding: 6px 15px;
                border-radius: 4px;
                font-weight: bold;
                font-size: 13px;
                margin-right: 5px;
            }
        """)


    def open_settings_dialog(self):
        dlg = SettingsDialog(self)

        # Загружаем текущие настройки в диалог
        dlg.pna_ip_edit.setText(self.settings.value('pna_ip', ''))
        dlg.pna_port_edit.setText(self.settings.value('pna_port', ''))
        dlg.pna_mode_combo.setCurrentIndex(int(self.settings.value('pna_mode', 0)))
        dlg.pna_files_path.setText(self.settings.value('pna_files_path', 'C:\\Users\\Public\\Documents\\Network Analyzer\\'))
        dlg.base_save_dir_edit.setText(self.settings.value('base_save_dir', ''))
        
        dlg.psn_ip_edit.setText(self.settings.value('psn_ip', ''))
        dlg.psn_port_edit.setText(self.settings.value('psn_port', ''))
        dlg.psn_mode_combo.setCurrentIndex(int(self.settings.value('psn_mode', 0)))
        dlg.psn_speed_x.setValue(int(self.settings.value('psn_speed_x', 10)))
        dlg.psn_speed_y.setValue(int(self.settings.value('psn_speed_y', 10)))
        dlg.psn_acc_x.setValue(int(self.settings.value('psn_acc_x', 5)))
        dlg.psn_acc_y.setValue(int(self.settings.value('psn_acc_y', 5)))
        
        dlg.trigger_ip_edit.setText(self.settings.value('trigger_ip', ''))
        dlg.trigger_port_edit.setText(self.settings.value('trigger_port', ''))
        dlg.trigger_mode_combo.setCurrentIndex(int(self.settings.value('trigger_mode', 0)))
        
        dlg.ma_com_combo.setCurrentText(self.settings.value('ma_com_port', ''))
        dlg.ma_mode_combo.setCurrentIndex(int(self.settings.value('ma_mode', 0)))
        
        # Настройки АФАР
        afar_connection_type = self.settings.value('afar_connection_type', 'udp')
        if afar_connection_type == 'udp':
            dlg.afar_connection_type.setCurrentIndex(0)
        else:
            dlg.afar_connection_type.setCurrentIndex(1)
        dlg.afar_ip_edit.setText(self.settings.value('afar_ip', ''))
        dlg.afar_port_edit.setText(self.settings.value('afar_port', ''))
        dlg.afar_com_combo.setCurrentText(self.settings.value('afar_com_port', ''))
        dlg.afar_mode_combo.setCurrentIndex(int(self.settings.value('afar_mode', 0)))
        dlg.afar_write_delay.setValue(int(self.settings.value('afar_write_delay', 100)))  # По умолчанию 100 мс
        
        if dlg.exec_() == QtWidgets.QDialog.Accepted:
            settings = dlg.get_settings()
            # Сохраняем все настройки
            for k, v in settings.items():
                self.settings.setValue(k, v)
            self.settings.sync()
            
            logger.info('Настройки сохранены')
            logger.debug(f'Сохраненные настройки: {settings}')
            
            # Передаём параметры во все виджеты
            self.phase_ma_widget.set_device_settings(settings)
            self.check_ma_widget.set_device_settings(settings)
            self.check_stend_ma_widget.set_device_settings(settings)
            self.phase_afar_widget.set_device_settings(settings)
            self.beam_pattern_widget.set_device_settings(settings)
            self.check_stend_afar_widget.set_device_settings(settings)
        else:
            # При отмене — не сохраняем, но всё равно пробросим актуальные настройки (на случай, если были активные)
            settings = self._collect_current_settings()
            self.phase_ma_widget.set_device_settings(settings)
            self.check_ma_widget.set_device_settings(settings)
            self.check_stend_ma_widget.set_device_settings(settings)
            self.phase_afar_widget.set_device_settings(settings)
            self.beam_pattern_widget.set_device_settings(settings)
            self.check_stend_afar_widget.set_device_settings(settings)

    def _collect_current_settings(self):
        """Собирает текущие настройки из QSettings в dict, как в load_settings."""
        settings = {}
        settings['pna_ip'] = self.settings.value('pna_ip', '')
        settings['pna_port'] = self.settings.value('pna_port', '')
        settings['pna_mode'] = int(self.settings.value('pna_mode', 0))
        settings['pna_files_path'] = self.settings.value('pna_files_path', 'C:\\Users\\Public\\Documents\\Network Analyzer\\')
        settings['psn_ip'] = self.settings.value('psn_ip', '')
        settings['psn_port'] = self.settings.value('psn_port', '')
        settings['psn_mode'] = int(self.settings.value('psn_mode', 0))
        settings['psn_speed_x'] = int(self.settings.value('psn_speed_x', 10))
        settings['psn_speed_y'] = int(self.settings.value('psn_speed_y', 10))
        settings['psn_acc_x'] = int(self.settings.value('psn_acc_x', 5))
        settings['psn_acc_y'] = int(self.settings.value('psn_acc_y', 5))
        settings['trigger_ip'] = self.settings.value('trigger_ip', '')
        settings['trigger_port'] = self.settings.value('trigger_port', '')
        settings['trigger_mode'] = int(self.settings.value('trigger_mode', 0))
        settings['ma_com_port'] = self.settings.value('ma_com_port', '')
        settings['ma_mode'] = int(self.settings.value('ma_mode', 0))
        settings['afar_connection_type'] = self.settings.value('afar_connection_type', 'udp')
        settings['afar_ip'] = self.settings.value('afar_ip', '')
        settings['afar_port'] = self.settings.value('afar_port', '')
        settings['afar_com_port'] = self.settings.value('afar_com_port', '')
        settings['afar_mode'] = int(self.settings.value('afar_mode', 0))
        settings['afar_write_delay'] = int(self.settings.value('afar_write_delay', 100))  # По умолчанию 100 мс
        settings['base_save_dir'] = self.settings.value('base_save_dir', '')
        return settings

    def open_manual_control(self):
        """Открывает окно ручного управления в зависимости от текущего режима (МА или АФАР)."""
        try:
            current_widget = self.central_widget.currentWidget()
            
            # Определяем, какой режим активен
            is_afar_mode = (current_widget == self.phase_afar_widget)
            
            if is_afar_mode:
                # Открываем ручное управление АФАР
                if self._manual_control_afar_window is None or not self._manual_control_afar_window.isVisible():
                    self._manual_control_afar_window = ManualControlAfarWindow(self)
                    # Передаём текущие настройки
                    self._manual_control_afar_window.set_device_settings(self._collect_current_settings())
                self._manual_control_afar_window.show()
                self._manual_control_afar_window.raise_()
                self._manual_control_afar_window.activateWindow()
            else:
                # Открываем ручное управление МА
                if self._manual_control_ma_window is None or not self._manual_control_ma_window.isVisible():
                    self._manual_control_ma_window = ManualControlWindow(self)
                    # Передаём текущие настройки
                    self._manual_control_ma_window.set_device_settings(self._collect_current_settings())
                self._manual_control_ma_window.show()
                self._manual_control_ma_window.raise_()
                self._manual_control_ma_window.activateWindow()
        except Exception as e:
            logger.error(f'Не удалось открыть окно ручного управления: {e}')

    def load_settings(self):
        # При запуске приложения сразу применяем параметры к обоим виджетам
        settings = {}
        # Загружаем все сохраненные настройки с значениями по умолчанию
        settings['pna_ip'] = self.settings.value('pna_ip', '')
        settings['pna_port'] = self.settings.value('pna_port', '')
        settings['pna_mode'] = int(self.settings.value('pna_mode', 0))
        settings['pna_files_path'] = self.settings.value('pna_files_path', 'C:\\Users\\Public\\Documents\\Network Analyzer\\')
        
        settings['psn_ip'] = self.settings.value('psn_ip', '')
        settings['psn_port'] = self.settings.value('psn_port', '')
        settings['psn_mode'] = int(self.settings.value('psn_mode', 0))
        settings['psn_speed_x'] = int(self.settings.value('psn_speed_x', 10))
        settings['psn_speed_y'] = int(self.settings.value('psn_speed_y', 10))
        settings['psn_acc_x'] = int(self.settings.value('psn_acc_x', 5))
        settings['psn_acc_y'] = int(self.settings.value('psn_acc_y', 5))
        
        settings['trigger_ip'] = self.settings.value('trigger_ip', '')
        settings['trigger_port'] = self.settings.value('trigger_port', '')
        settings['trigger_mode'] = int(self.settings.value('trigger_mode', 0))
        
        settings['ma_com_port'] = self.settings.value('ma_com_port', '')
        settings['ma_mode'] = int(self.settings.value('ma_mode', 0))
        
        settings['afar_connection_type'] = self.settings.value('afar_connection_type', 'udp')
        settings['afar_ip'] = self.settings.value('afar_ip', '')
        settings['afar_port'] = self.settings.value('afar_port', '')
        settings['afar_com_port'] = self.settings.value('afar_com_port', '')
        settings['afar_mode'] = int(self.settings.value('afar_mode', 0))
        settings['afar_write_delay'] = int(self.settings.value('afar_write_delay', 100))  # По умолчанию 100 мс
        
        # Путь к файлам измерений
        settings['base_save_dir'] = self.settings.value('base_save_dir', '')
        
        logger.info('Настройки загружены из файла настроек')
        logger.debug(f'Загруженные настройки: {settings}')
        
        self.phase_ma_widget.set_device_settings(settings)
        self.check_ma_widget.set_device_settings(settings)
        self.check_stend_ma_widget.set_device_settings(settings)
        self.phase_afar_widget.set_device_settings(settings)
        self.beam_pattern_widget.set_device_settings(settings)
        self.check_stend_afar_widget.set_device_settings(settings)

if __name__ == '__main__':
    import sys
    app = QtWidgets.QApplication(sys.argv)
    win = MainWindow()
    win.show()
    sys.exit(app.exec_())
