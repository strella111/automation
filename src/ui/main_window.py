from PyQt5 import QtWidgets, QtCore
from ui.widgets.phase_ma_widget import PhaseMaWidget
from ui.widgets.check_ma_widget import CheckMaWidget
from ui.widgets.check_stend_ma_widget import StendCheckMaWidget
from ui.widgets.manual_control_widget import ManualControlWindow
from ui.dialogs.settings_dialog import SettingsDialog
from loguru import logger

class MainWindow(QtWidgets.QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle('DEV')
        self.resize(1400, 800)

        self.settings = QtCore.QSettings('PULSAR', 'PhaseMA')

        self.menu_bar = QtWidgets.QMenuBar(self)
        self.setMenuBar(self.menu_bar)
        self.menu_mode = self.menu_bar.addMenu('Режим')
        self.menu_utils = self.menu_bar.addMenu('Утилиты')
        self.menu_params = self.menu_bar.addMenu('Параметры')

        # --- Центральная область (режимы) ---
        self.central_widget = QtWidgets.QStackedWidget()
        self.setCentralWidget(self.central_widget)

        # --- Виджеты режимов ---
        self.phase_ma_widget = PhaseMaWidget()
        self.check_ma_widget = CheckMaWidget()
        self.check_stend_ma_widget = StendCheckMaWidget()
        self.central_widget.addWidget(self.phase_ma_widget)
        self.central_widget.addWidget(self.check_ma_widget)
        self.central_widget.addWidget(self.check_stend_ma_widget)

        # --- Привязка меню ---
        self.phase_action = self.menu_mode.addAction('Фазировка МА в БЭК')
        self.phase_action.setCheckable(True)
        self.phase_action.triggered.connect(self.show_phase_ma)

        self.check_bek_action = self.menu_mode.addAction('Проверка МА в БЭК')
        self.check_bek_action.setCheckable(True)
        self.check_bek_action.triggered.connect(self.show_check_ma)

        self.check_stend_action = self.menu_mode.addAction('Проверка МА на стенде')
        self.check_stend_action.setCheckable(True)
        self.check_stend_action.triggered.connect(self.show_check_stend_ma)

        # Группа для взаимоисключающих действий
        mode_group = QtWidgets.QActionGroup(self)
        mode_group.addAction(self.phase_action)
        mode_group.addAction(self.check_bek_action)
        mode_group.addAction(self.check_stend_action)
        mode_group.setExclusive(True)
        
        self.menu_params.addAction('Настройки устройств', self.open_settings_dialog)
        # --- Утилиты ---
        self.action_manual_control = self.menu_utils.addAction('Ручное управление')
        self.action_manual_control.triggered.connect(self.open_manual_control)

        # Восстанавливаем состояние интерфейса
        self.restore_ui_state()
        
        # Загружаем настройки устройств
        self.load_settings()

        # Ссылка на окно ручного управления, чтобы не собирался GC
        self._manual_control_window = None

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
        else:
            self.settings.setValue('last_mode', 'check')
            
        self.settings.sync()
        super().closeEvent(event)
        
    def show_phase_ma(self):
        self.central_widget.setCurrentWidget(self.phase_ma_widget)
        self.phase_action.setChecked(True)

    def show_check_ma(self):
        self.central_widget.setCurrentWidget(self.check_ma_widget)
        self.check_bek_action.setChecked(True)

    def show_check_stend_ma(self):
        self.central_widget.setCurrentWidget(self.check_stend_ma_widget)
        self.check_stend_action.setChecked(True)

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
        
        if dlg.exec_() == QtWidgets.QDialog.Accepted:
            settings = dlg.get_settings()
            # Сохраняем все настройки
            for k, v in settings.items():
                self.settings.setValue(k, v)
            self.settings.sync()
            
            logger.info('Настройки сохранены')
            logger.debug(f'Сохраненные настройки: {settings}')
            
            # Передаём параметры в оба виджета
            self.phase_ma_widget.set_device_settings(settings)
            self.check_ma_widget.set_device_settings(settings)
            self.check_stend_ma_widget.set_device_settings(settings)
        else:
            # При отмене — не сохраняем, но всё равно пробросим актуальные настройки (на случай, если были активные)
            settings = self._collect_current_settings()
            settings['base_save_dir'] = self.settings.value('base_save_dir', '')
            self.phase_ma_widget.set_device_settings(settings)
            self.check_ma_widget.set_device_settings(settings)
            self.check_stend_ma_widget.set_device_settings(settings)

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
        return settings

    def open_manual_control(self):
        """Открывает окно ручного управления (утилиты)."""
        try:
            if self._manual_control_window is None or not self._manual_control_window.isVisible():
                self._manual_control_window = ManualControlWindow(self)
                # Передаём текущие настройки
                self._manual_control_window.set_device_settings(self._collect_current_settings())
            self._manual_control_window.show()
            self._manual_control_window.raise_()
            self._manual_control_window.activateWindow()
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
        
        logger.info('Настройки загружены из реестра')
        logger.debug(f'Загруженные настройки: {settings}')
        
        self.phase_ma_widget.set_device_settings(settings)
        self.check_ma_widget.set_device_settings(settings)
        self.check_stend_ma_widget.set_device_settings(settings)

if __name__ == '__main__':
    import sys
    app = QtWidgets.QApplication(sys.argv)
    win = MainWindow()
    win.show()
    sys.exit(app.exec_())
