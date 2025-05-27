import sys
import os
from pathlib import Path
from PyQt5 import QtWidgets
from utils.logger import setup_logging

src_path = str(Path(__file__).parent)
if src_path not in sys.path:
    sys.path.insert(0, src_path)

from ui.main_window import MainWindow

if __name__ == '__main__':
    setup_logging()
    app = QtWidgets.QApplication(sys.argv)
    win = MainWindow()
    win.show()
    sys.exit(app.exec_())
