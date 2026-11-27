"""First-run window: shows the local onboarding page until the person finishes it.

Exit code 0 when setup is complete, 1 when the window is closed first."""
import argparse
import sys
from pathlib import Path

from PySide6.QtCore import QTimer, QUrl
from PySide6.QtGui import QIcon
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWidgets import QApplication

from desktop.compositor import APPLICATION_ID
from desktop.links import ExternalLinks

DONE_TITLE = 'chassie:onboarding-complete'


class OnboardingWindow(QWebEngineView):
    def __init__(self, url, app):
        super().__init__()
        self.app, self.finished = app, False
        self.setWindowTitle('Welcome to Chassie')
        self.resize(1080, 720)
        self.setMinimumSize(760, 560)
        self.setPage(ExternalLinks(self))
        self.titleChanged.connect(self.on_title)
        self.setUrl(QUrl(url))

    def on_title(self, title):
        if title == DONE_TITLE and not self.finished:
            self.finished = True
            QTimer.singleShot(500, lambda: self.app.exit(0))

    def closeEvent(self, event):
        if not self.finished:
            self.app.exit(1)
        super().closeEvent(event)


def main(argv=None):
    parser = argparse.ArgumentParser(description='Chassie first-run setup')
    parser.add_argument('--url', default='http://127.0.0.1:8000/onboarding')
    args = parser.parse_args(argv)
    app = QApplication([APPLICATION_ID])
    app.setApplicationName(APPLICATION_ID)
    app.setWindowIcon(QIcon(str(Path(__file__).resolve().parents[1] / 'ui/public/chassie-icon.png')))
    window = OnboardingWindow(args.url, app)
    screen = app.primaryScreen().availableGeometry()
    window.move(screen.center() - window.rect().center())
    window.show()
    return app.exec()


if __name__ == '__main__':
    sys.exit(main())
