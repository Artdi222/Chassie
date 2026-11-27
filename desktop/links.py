"""Links that open a new tab (target=_blank: terms, release downloads) go to the person's own browser.

QWebEngineView ignores them by default; the panels only ever show Chassie's own local pages.
"""
from PySide6.QtGui import QDesktopServices
from PySide6.QtWebEngineCore import QWebEnginePage


class ExternalLinks(QWebEnginePage):
    def createWindow(self, _type):
        return _ToBrowser(self)  # A throwaway page whose first navigation is the clicked link.


class _ToBrowser(QWebEnginePage):
    def acceptNavigationRequest(self, url, _type, _main_frame):
        if url.scheme() in ('http', 'https'): QDesktopServices.openUrl(url)
        self.deleteLater()
        return False
