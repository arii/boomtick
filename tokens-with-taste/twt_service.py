'''Serve the tokens-with-taste gateway on TCP and a Unix socket.'''

import argparse
import os
import socket
import stat
from pathlib import Path

import uvicorn

from twt.gateway import create_app
from twt.store import Store


def bind_uds(path):
    path = Path(path)
    if not path.is_absolute():
        raise ValueError('TWT socket path must be absolute')
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    if path.parent.stat().st_mode & 0o777 != 0o700:
        raise ValueError('TWT socket directory must be private (0700)')
    if path.exists() or path.is_symlink():
        if not stat.S_ISSOCK(path.lstat().st_mode):
            raise ValueError('Refusing to replace a non-socket path')
        with socket.socket(socket.AF_UNIX) as probe:
            try:
                probe.connect(str(path))
            except ConnectionRefusedError:
                path.unlink()
            else:
                raise ValueError('TWT socket is already active')
    sock = socket.socket(socket.AF_UNIX)
    try:
        sock.bind(str(path))
        os.chmod(path, 0o600)
        return sock
    except BaseException:
        sock.close()
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', type=int, default=8000)
    parser.add_argument('--uds', default=os.environ.get('TWT_UDS', '/run/twt/gateway.sock'))
    args = parser.parse_args()
    app = create_app(store=Store())
    if not args.uds:
        uvicorn.run(app, host='127.0.0.1', port=args.port)
        return
    config = uvicorn.Config(app, host='127.0.0.1', port=args.port)
    with bind_uds(args.uds) as local, config.bind_socket() as tcp:
        try:
            uvicorn.Server(config).run(sockets=[tcp, local])
        finally:
            Path(args.uds).unlink(missing_ok=True)


if __name__ == '__main__':
    main()
