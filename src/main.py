import sys
from PyQt5 import QtWidgets
from utils.logger import setup_logging
import os

from ui.main_window import MainWindow


if __name__ == '__main__':

    setup_logging()
    app = QtWidgets.QApplication(sys.argv)
    win = MainWindow()
    win.show()
    sys.exit(app.exec_())
