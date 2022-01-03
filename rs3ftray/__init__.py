import os.path
import sys
from typing import Optional, Set

from PyQt5.QtCore import QSettings
from PyQt5.QtGui import QIcon
from PyQt5.QtWidgets import *

from rs3f import connect, disconnect, RE_VOLUME


class SettingsWindow(QMainWindow):
    """The settings window."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.settings = QSettings("corexalys", "rs3ftray", parent=self)
        self.setWindowTitle("RS3F − Settings")
        self.setMinimumSize(240, 320)
        window = QWidget(self)
        self.setCentralWidget(window)
        main_box = QHBoxLayout(window)

        left_box = QVBoxLayout()
        left_box.addWidget(QLabel("Volumes"))
        self.list_widget = QListWidget()
        self.list_widget.setSelectionMode(QListWidget.MultiSelection)
        for volume in self.settings.value("volumes", [], type=str):
            self.list_widget.addItem(volume)

        left_box.addWidget(self.list_widget)
        delete_button = QPushButton("Delete selected volumes")
        delete_button.clicked.connect(self.delete_selected)
        left_box.addWidget(delete_button)
        add_volume_row = QHBoxLayout()
        self.new_volume_name = QLineEdit()
        self.new_volume_name.returnPressed.connect(self.new_volume_return_pressed)
        add_volume_row.addWidget(self.new_volume_name)
        add_volume_button = QPushButton("Add Volume")
        add_volume_button.clicked.connect(self.add_volume_clicked)
        add_volume_row.addWidget(add_volume_button)
        left_box.addLayout(add_volume_row)
        main_box.addLayout(left_box)

        right_box = QVBoxLayout()
        right_box.addWidget(QLabel("Autostart"))
        right_box.addWidget(QPushButton("Enable Autostart"))
        right_box.addWidget(QPushButton("Disable Autostart"))
        right_box.addStretch(1)
        main_box.addLayout(right_box)

        window.setLayout(main_box)

    def delete_selected(self, _checked: bool) -> None:
        volumes = self.settings.value("volumes", [], type=str)

        for index in self.list_widget.selectedIndexes()[::-1]:
            row = self.list_widget.item(index.row())
            self.list_widget.takeItem(index.row())
            volumes.remove(row.text())

        # TODO Unmount deleted volumes if already mounted?

        self.settings.setValue("volumes", volumes)
        self.parent().reload_volumes()

    def add_volume(self, volume_name: str) -> None:
        stripped = volume_name.strip()

        error_message: Optional[str] = None

        # Check the volume name is valid
        if not stripped:
            error_message = "Empty volume name."
        elif not RE_VOLUME.match(stripped):
            error_message = "Invalid volume format, expected 'volume[@server[:port]]'."
        elif stripped in self.settings.value("volumes", [], type=str):
            error_message = "Volume already present."

        # Show an error message and exit if the volume name is invalid
        if error_message is not None:
            message_box = QMessageBox(self)
            message_box.setIcon(QMessageBox.Critical)
            message_box.setWindowTitle("Invalid volume name")
            message_box.setText(error_message)
            message_box.show()
            return

        # Append to the list
        self.list_widget.addItem(stripped)
        volumes = self.settings.value("volumes", [], type=str)
        if not volumes:  # volumes is a string if empty ???
            volumes = []
        volumes.append(stripped)
        self.settings.setValue("volumes", volumes)
        self.parent().reload_volumes()

    def new_volume_return_pressed(self):
        self.add_volume(self.new_volume_name.text())

    def add_volume_clicked(self, _checked: bool):
        self.add_volume(self.new_volume_name.text())


class TrayMenu(QMenu):
    """The tray menu."""

    def __init__(self, app: QApplication) -> None:
        super().__init__()

        self.volume_actions: Set[QAction] = set()

        settings_window = SettingsWindow(parent=self)

        self.addSection("Volumes")
        self.volumes_end = self.addSeparator()
        self.reload_volumes()

        self.addAction("Open all")
        self.addAction("Close all")
        settings_action = QAction("Settings", parent=self)
        settings_action.triggered.connect(settings_window.show)
        self.addAction(settings_action)

        self.addSeparator()
        quit_action = QAction("Quit", parent=self)
        quit_action.triggered.connect(app.quit)
        self.addAction(quit_action)

    def reload_volumes(self):
        settings = QSettings("corexalys", "rs3ftray", parent=self)
        volumes = settings.value("volumes", [], type=str)

        for action in self.volume_actions:
            self.removeAction(action)

        self.volume_actions.clear()

        if volumes:
            for volume in volumes:
                action = QAction(volume.replace("_", "__"), parent=self)
                action.setCheckable(True)
                self.insertAction(self.volumes_end, action)
                self.volume_actions.add(action)
        else:
            action = QAction("No volumes configured", parent=self)
            action.setEnabled(False)
            self.insertAction(self.volumes_end, action)
            self.volume_actions.add(action)


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
