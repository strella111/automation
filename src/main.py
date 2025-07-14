import sys
from PyQt5 import QtWidgets
from utils.logger import setup_logging
from ui.styles.style_manager import style_manager

from ui.main_window import MainWindow


if __name__ == '__main__':

    setup_logging()
    app = QtWidgets.QApplication(sys.argv)
    
    if style_manager.load_theme('light_theme'):

        style_manager.apply_builtin_arrows(app)
        style_manager.apply_to_application(app)

    
    win = MainWindow()
    win.show()
    sys.exit(app.exec_())
