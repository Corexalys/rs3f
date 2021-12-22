import os.path
import sys

from PyQt5.QtCore import QSettings
from PyQt5.QtGui import QIcon
from PyQt5.QtWidgets import *

from rs3f import connect, disconnect


class SettingsWindow(QMainWindow):
    """The settings window."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.setWindowTitle("RS3F − Settings")
        self.setMinimumSize(240, 320)
        window = QWidget(self)
        self.setCentralWidget(window)
        main_box = QHBoxLayout(window)

        left_box = QVBoxLayout()
        left_box.addWidget(QLabel("Volumes"))
        left_box.addWidget(QListView())
        add_volume_row = QHBoxLayout()
        add_volume_row.addWidget(QLineEdit())
        add_volume_row.addWidget(QPushButton("Add Volume"))
        left_box.addLayout(add_volume_row)
        main_box.addLayout(left_box)

        right_box = QVBoxLayout()
        right_box.addWidget(QLabel("Autostart"))
        right_box.addWidget(QPushButton("Enable Autostart"))
        right_box.addWidget(QPushButton("Disable Autostart"))
        right_box.addStretch(1)
        main_box.addLayout(right_box)

        window.setLayout(main_box)


class TrayMenu(QMenu):
    """The tray menu."""

    def __init__(self, app: QApplication) -> None:
        super().__init__()

        settings = QSettings("corexalys", "rs3ftray", parent=self)
        volumes = settings.value("volumes", [], type=str)

        ICON_MOUNTED = QIcon(
            os.path.join(os.path.dirname(__file__), "menu_mounted.png")
        )
        ICON_UNMOUNTED = QIcon(
            os.path.join(os.path.dirname(__file__), "menu_unmounted.png")
        )
        settings_window = SettingsWindow(parent=self)

        self.addSection("Volumes")
        if volumes:
            for volume in volumes:
                action = QAction(volume, parent=self)
                action.setCheckable(True)
        else:
            action = QAction("No volumes configured", parent=self)
            action.setEnabled(False)
            self.addAction(action)

        self.addSeparator()
        self.addAction("Open all")
        self.addAction("Close all")
        settings_action = QAction("Settings", parent=self)
        settings_action.triggered.connect(settings_window.show)
        self.addAction(settings_action)

        self.addSeparator()
        quit_action = QAction("Quit", parent=self)
        quit_action.triggered.connect(app.quit)
        self.addAction(quit_action)


class TrayIcon(QSystemTrayIcon):
    """The tray icon."""

    def __init__(self, app: QApplication):
        super().__init__()
        ICON_NORMAL = QIcon(os.path.join(os.path.dirname(__file__), "icon_normal.png"))
        ICON_ERROR = QIcon(os.path.join(os.path.dirname(__file__), "icon_error.png"))

        self.setIcon(ICON_NORMAL)
        self.setContextMenu(TrayMenu(app))


def main():
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    tray = TrayIcon(app)
    tray.setVisible(True)
    sys.exit(app.exec_())
