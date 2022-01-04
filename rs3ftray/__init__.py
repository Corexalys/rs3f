import os.path
import subprocess
import sys
from typing import Dict, Optional, Set

from PyQt5.QtCore import QSettings
from PyQt5.QtGui import QIcon
from PyQt5.QtWidgets import *
import secretstorage

from rs3f import connect, disconnect, RE_VOLUME

DEFAULT_MOUNT_PATH = os.getenv("HOME")
MOUNTED_VOLUMES: Dict[str, os.PathLike] = {}


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
        left_box.addWidget(QLabel("Volumes:"))
        self.list_widget = QListWidget()
        self.list_widget.setSelectionMode(QListWidget.MultiSelection)
        for volume in self.settings.value("volumes") or []:
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
        right_box.addWidget(QLabel("Mount path:"))
        mount_path_row = QHBoxLayout()
        self.mount_path_edit = QLineEdit(
            self.settings.value("mount_path") or DEFAULT_MOUNT_PATH
        )
        mount_path_row.addWidget(self.mount_path_edit)
        browse_button = QPushButton("…")
        browse_button.clicked.connect(self.browse_mount_path)
        browse_button.setFixedSize(22, 22)
        mount_path_row.addWidget(browse_button)
        right_box.addLayout(mount_path_row)
        save_mount_path_button = QPushButton("Save mount path")
        save_mount_path_button.clicked.connect(self.save_mount_path)
        right_box.addWidget(save_mount_path_button)
        right_box.addSpacing(10)

        right_box.addWidget(QLabel("Default server:"))
        right_box.addWidget(QLabel("SSH hostname/IP:"))
        self.default_server_edit = QLineEdit(self.settings.value("server"))
        right_box.addWidget(self.default_server_edit)
        right_box.addWidget(QLabel("SSH port:"))
        self.default_server_port_spin = QSpinBox()
        self.default_server_port_spin.setRange(0, 65535)
        self.default_server_port_spin.setValue(int(self.settings.value("port") or 0))
        right_box.addWidget(self.default_server_port_spin)
        save_default_server_button = QPushButton("Save default server")
        save_default_server_button.clicked.connect(self.save_default_server)
        right_box.addWidget(save_default_server_button)
        right_box.addStretch(1)
        main_box.addLayout(right_box)

        window.setLayout(main_box)

    def browse_mount_path(self, _checked: bool) -> None:
        """Open the directory browser to select a mountpath."""
        directory = QFileDialog.getExistingDirectory(self)

        # Cancelled
        if not directory:
            return

        self.mount_path_edit.setText(directory)

    def save_mount_path(self, _checked: bool) -> None:
        """Save the mount path."""
        self.settings.setValue("mount_path", self.mount_path_edit.text())

    def save_default_server(self, _checked: bool) -> None:
        """Save the default server."""
        self.settings.setValue("server", self.default_server_edit.text())
        self.settings.setValue("port", self.default_server_port_spin.value())

    def delete_selected(self, _checked: bool) -> None:
        """Delete the selected volumes."""
        volumes = self.settings.value("volumes") or []

        for index in self.list_widget.selectedIndexes()[::-1]:
            row = self.list_widget.item(index.row())
            self.list_widget.takeItem(index.row())
            volumes.remove(row.text())
            # Disconnect the volume if it was mounted
            if row.text() in MOUNTED_VOLUMES:
                disconnect(MOUNTED_VOLUMES.pop(row.text()))

        self.settings.setValue("volumes", volumes)
        self.parent().reload_volumes()

    def add_volume(self, volume_name: str) -> None:
        """Add a volume to the saved volume list."""
        stripped = volume_name.strip()

        error_message: Optional[str] = None

        # Check the volume name is valid
        if not stripped:
            error_message = "Empty volume name."
        elif not RE_VOLUME.match(stripped):
            error_message = "Invalid volume format, expected 'volume[@server[:port]]'."
        elif stripped in (self.settings.value("volumes") or []):
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
        volumes = self.settings.value("volumes") or []
        volumes.append(stripped)
        self.settings.setValue("volumes", volumes)
        self.parent().reload_volumes()

    def new_volume_return_pressed(self):
        """Add the volume."""
        self.add_volume(self.new_volume_name.text())

    def add_volume_clicked(self, _checked: bool):
        """Add the volume."""
        self.add_volume(self.new_volume_name.text())


class TrayMenu(QMenu):
    """The tray menu."""

    def __init__(self, app: QApplication) -> None:
        super().__init__()
        self.settings = QSettings("corexalys", "rs3ftray", parent=self)

        self.volume_actions: Set[QAction] = set()
        self.volume_action_map: Dict[str, QAction] = {}

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

    def toggle_mount(self, volume: str, mount: bool):
        """Mount or unmount the given volume."""
        # Should never happen
        if volume in MOUNTED_VOLUMES and mount:
            raise RuntimeError("Volume is already mounted")
        # Happens when manually disabling a volume after an error during mount
        if volume not in MOUNTED_VOLUMES and not mount:
            return

        if mount:
            # Extract arguments for connection
            match = RE_VOLUME.match(volume)

            server = match["server"] or self.settings.value("server")
            if server is None:
                message_box = QMessageBox(self)
                message_box.setIcon(QMessageBox.Critical)
                message_box.setWindowTitle(f"Cannot mount volume: {volume}")
                message_box.setText(
                    "No server name is in the volume name, and no default server is configured."
                )
                message_box.show()
                self.volume_action_map[volume].setChecked(False)
                return

            port = match["port"] or self.settings.value("port")
            if port:
                port = int(port)
            else:
                port = None
            mountpoint = os.path.join(
                os.path.expanduser(self.settings.value("mountpoint") or "~"),
                match["volume"],
            )

            # Mount the volume
            connect(
                match["volume"],
                server,
                mountpoint,
                lambda: self.fetch_password(volume),
                port=port,
                allow_init=False,
            )
            MOUNTED_VOLUMES[volume] = mountpoint

            # Open the mounted volume in the file explorer
            subprocess.run(["xdg-open", mountpoint], check=True)

        else:
            disconnect(MOUNTED_VOLUMES.pop(volume))

    def fetch_password(self, volume_name: str) -> Optional[str]:
        """Fetch the password for a given volume name."""
        # Fetch password from the org.freedeskstop.secret dbus interface
        connection = secretstorage.dbus_init()
        collection = secretstorage.collection.get_default_collection(connection)
        if collection.is_locked():
            collection.unlock()
        items = collection.search_items({"Title": volume_name})  # Keepass
        for item in items:
            return item.get_secret().decode()

        # Password not found in the keyring, prompt it
        result, ok_pressed = QInputDialog.getText(
            self,
            f"Password for {volume_name} not found",
            "Please specify the password manually:",
            QLineEdit.Password,
        )
        if not ok_pressed:
            return None

        # Save the password in the keyring if the user agrees
        message_box = QMessageBox(self)
        message_box.setIcon(QMessageBox.Question)
        message_box.setWindowTitle(f"Save the password for {volume_name}?")
        message_box.setText(
            f"Do you want to save the password for {volume_name} in the keyring?"
        )
        return_code = message_box.exec()
        if return_code == QMessageBox.Ok:
            collection.create_item(volume_name, {"Title": volume_name}, result.encode())

        return result

    def reload_volumes(self):
        """Remove the volumes from the tray menu and re-add them."""
        volumes = self.settings.value("volumes") or []

        for action in self.volume_actions:
            self.removeAction(action)

        self.volume_actions.clear()

        if volumes:
            for volume in list(volumes):
                # Needed since otherwise '_' are special characters
                action = QAction(volume.replace("_", "__"), parent=self)
                action.toggled.connect(
                    lambda checked, volume=volume: self.toggle_mount(volume, checked)
                )
                action.setCheckable(True)
                self.insertAction(self.volumes_end, action)
                self.volume_actions.add(action)
                self.volume_action_map[volume] = action
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
    """The main function."""
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    tray = TrayIcon(app)
    tray.setVisible(True)
    sys.exit(app.exec_())
