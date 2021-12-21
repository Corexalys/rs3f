import sys
from PyQt5.QtWidgets import QApplication, QWidget

def main():
    app = QApplication(sys.argv)
    window = QWidget()
    window.show()
    sys.exit(app.exec_())

