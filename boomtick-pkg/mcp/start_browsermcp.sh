#!/bin/bash
# Start a dummy listener on port 9009 so that lsof -ti:9009 doesn't return empty and crash the server
python3 -c "
import socket, time
try:
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(('127.0.0.1', 9009))
    s.listen(1)
    time.sleep(2)
except Exception:
    pass
" &
sleep 0.2
exec npx @browsermcp/mcp@latest "$@"
