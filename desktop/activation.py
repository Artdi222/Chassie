"""Local desktop activation shared by the launcher and the running Qt process."""
from pathlib import Path
import socket
import time


def activation_path(root):
    return Path(root) / '.chassie' / 'desktop-activation.sock'


def request_activation(path, timeout=5.0):
    """Allow a second click during startup to wait for the desktop listener."""
    deadline=time.monotonic()+timeout
    while True:
        try:
            with socket.socket(socket.AF_UNIX,socket.SOCK_STREAM) as client:
                client.settimeout(.2)
                client.connect(str(path))
            return True
        except OSError:
            if time.monotonic()>=deadline:return False
            time.sleep(.1)


def listen_for_activation(path, callback, parent):
    # Import Qt only inside the desktop process, preserving its native import order.
    from PySide6.QtNetwork import QLocalServer
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    server=QLocalServer(parent)
    server.setSocketOptions(QLocalServer.SocketOption.UserAccessOption)
    if not server.listen(str(path)):
        if request_activation(path,timeout=0):
            raise RuntimeError('The Chassie desktop is already running.')
        QLocalServer.removeServer(str(path))
        if not server.listen(str(path)):
            raise RuntimeError('Could not start desktop activation listener.')
    def activate():
        while server.hasPendingConnections():
            connection=server.nextPendingConnection()
            connection.close();connection.deleteLater()
        callback()
    server.newConnection.connect(activate)
    return server
