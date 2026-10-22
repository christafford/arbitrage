"""Linux process lock shared by CLI writers. File existence alone is not a lock."""
from contextlib import contextmanager
import fcntl
import os
from pathlib import Path
import threading

_held = {}


@contextmanager
def writer_lock(database):
    path = str(Path(database).resolve())
    key = (os.getpid(), threading.get_ident(), path)
    if key in _held:
        yield
        return
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(path + '.writer.lock', os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    try:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise ValueError('another predarb writer holds this database lock') from exc
        _held[key] = fd
        os.ftruncate(fd, 0);os.write(fd, str(os.getpid()).encode())
        yield
    finally:
        if _held.pop(key, None) is not None:
            fcntl.flock(fd, fcntl.LOCK_UN)
        os.close(fd)
