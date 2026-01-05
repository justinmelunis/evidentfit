import os, socket, sys
from urllib.parse import urlparse, parse_qs, urlunparse

url = os.environ.get("DATABASE_URL", "")
print("Has DATABASE_URL:", bool(url))
if not url:
    sys.exit(1)

u = urlparse(url)
safe = u._replace(netloc=(u.username or "") + ":***@" + (u.hostname or "") + ((":" + str(u.port)) if u.port else ""))
print("Parsed:", urlunparse(safe))

host = u.hostname
port = u.port or 5432
print("Host:", host, "Port:", port, "Scheme:", u.scheme)

try:
    info = socket.getaddrinfo(host, port)
    print("DNS ok ->", info[0][4][0])
except Exception as e:
    print("DNS/Connect info error:", repr(e))
