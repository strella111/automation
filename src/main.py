import sys
import os
from pathlib import Path
from PyQt5 import QtWidgets
from utils.logger import setup_logging

from ui.main_window import MainWindow

if __name__ == '__main__':
    setup_logging()
    
    # Set Qt plugin path for macOS
    if sys.platform == 'darwin':
        qt_plugin_path = os.path.join(os.path.dirname(QtWidgets.__file__), "Qt5", "plugins")
        os.environ['QT_QPA_PLATFORM_PLUGIN_PATH'] = os.path.join(qt_plugin_path, "platforms")
    
    app = QtWidgets.QApplication(sys.argv)
    win = MainWindow()
    win.show()
    sys.exit(app.exec_())
