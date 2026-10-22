"""In-memory signing for the fixed read-only WebSocket handshake only."""
import base64
import os
from pathlib import Path
import stat
import time
from uuid import UUID

from .validation import load_json

WS_URL = 'wss://external-api-ws.kalshi.com/trade-api/ws/v2'
WS_PATH = '/trade-api/ws/v2'


def private_file(path):
    path = Path(path).expanduser().absolute()
    # Credentials never belong inside a checkout, even if ignored by Git.
    if any((parent / '.git').exists() for parent in path.resolve().parents):
        raise ValueError('credentials must be stored outside Git checkouts')
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        with os.fdopen(fd, 'rb') as handle:
            info = os.fstat(handle.fileno())
            if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o077:
                raise ValueError('credential files must be owner-only regular files (0600)')
            body = handle.read(65537)
            if len(body) > 65536:
                raise ValueError('credential file exceeds size limit')
            return body
    except OSError:
        raise ValueError('credential file unavailable; use owner-only files outside Git') from None


class Credentials:
    def __init__(self, key_id, key):
        self._key_id, self._key = key_id, key

    @classmethod
    def load(cls, path):
        try:
            from cryptography.hazmat.primitives.serialization import load_pem_private_key
            from cryptography.hazmat.primitives.asymmetric import rsa, ed25519
            from cryptography.exceptions import UnsupportedAlgorithm
        except ImportError:
            raise ValueError('install the kalshi-ws optional dependencies') from None
        try:
            config = load_json(private_file(path))
            if set(config) != {'api_key_id', 'private_key_path'}:
                raise ValueError()
            key_id = str(UUID(config['api_key_id']))
            key_path = Path(config['private_key_path']).expanduser()
            if not key_path.is_absolute():
                key_path = Path(path).expanduser().parent / key_path
            key = load_pem_private_key(private_file(key_path), password=None)
            if not isinstance(key, (rsa.RSAPrivateKey, ed25519.Ed25519PrivateKey)):
                raise ValueError()
            if isinstance(key, rsa.RSAPrivateKey) and key.key_size < 2048:
                raise ValueError()
            return cls(key_id, key)
        except (ValueError, TypeError, KeyError, UnsupportedAlgorithm):
            raise ValueError('invalid credential configuration, permissions or unsupported private key') from None

    def headers(self, *, timestamp_ms=None):
        from cryptography.hazmat.primitives import hashes
        from cryptography.hazmat.primitives.asymmetric import padding, ed25519
        stamp = str(time.time_ns() // 1_000_000 if timestamp_ms is None else timestamp_ms)
        message = (stamp + 'GET' + WS_PATH).encode()
        if isinstance(self._key, ed25519.Ed25519PrivateKey):
            signature = self._key.sign(message)
        else:
            signature = self._key.sign(message, padding.PSS(mgf=padding.MGF1(hashes.SHA256()),
                                                         salt_length=32), hashes.SHA256())
        return {'KALSHI-ACCESS-KEY': self._key_id, 'KALSHI-ACCESS-TIMESTAMP': stamp,
                'KALSHI-ACCESS-SIGNATURE': base64.b64encode(signature).decode('ascii')}
