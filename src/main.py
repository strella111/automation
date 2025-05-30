import sys
from PyQt5 import QtWidgets
from utils.logger import setup_logging
import os

from ui.main_window import MainWindow


if __name__ == '__main__':
    os.environ[
        "QT_QPA_PLATFORM_PLUGIN_PATH"] = "/Users/maksimkolesnikov/Desktop/CursorProjects/PULSAR/.venv/lib/python3.13/site-packages/PyQt5/Qt5/plugins"

    print("QT plugins path:", os.environ["QT_QPA_PLATFORM_PLUGIN_PATH"])
    setup_logging()
    app = QtWidgets.QApplication(sys.argv)
    win = MainWindow()
    win.show()
    sys.exit(app.exec_())
