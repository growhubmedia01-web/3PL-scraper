"""Start the API on a port that actually works.

    py run.py              # uses API_PORT from .env, falls back if blocked
    py run.py --port 8123  # explicit port

Windows reserves large blocks of TCP ports for Hyper-V, WSL and Docker.
Binding one of those fails with WinError 10013 ("access permissions") rather
than the usual "address already in use", which is confusing because netstat
shows nothing listening. This picks the next usable port instead.
"""
from __future__ import annotations

import argparse
import socket
import sys

from app.config import settings

FALLBACK_PORTS = [8000, 8080, 8123, 8888, 9000, 9090, 3001, 4000, 5055]


def port_is_bindable(port: int, host: str = "127.0.0.1") -> tuple[bool, str]:
    """Can we actually listen here? Returns (ok, reason)."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        sock.bind((host, port))
        return True, ""
    except PermissionError:
        return False, "reserved by the OS (Hyper-V/WSL/Docker) or needs admin"
    except OSError as exc:
        if getattr(exc, "winerror", None) == 10013:
            return False, "reserved by the OS (Hyper-V/WSL/Docker)"
        if exc.errno in (98, 10048):
            return False, "already in use by another process"
        return False, str(exc)
    finally:
        sock.close()


def pick_port(preferred: int) -> int:
    ok, reason = port_is_bindable(preferred)
    if ok:
        return preferred

    print(f"  Port {preferred} unavailable: {reason}")
    for candidate in FALLBACK_PORTS:
        if candidate == preferred:
            continue
        ok, _ = port_is_bindable(candidate)
        if ok:
            print(f"  Falling back to port {candidate}")
            return candidate

    # Last resort: let the OS choose.
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    chosen = sock.getsockname()[1]
    sock.close()
    print(f"  No standard port available; using {chosen}")
    return chosen


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=settings.api_port)
    parser.add_argument("--host", default=settings.api_host)
    parser.add_argument("--no-reload", action="store_true")
    args = parser.parse_args()

    port = pick_port(args.port)

    print()
    print(f"  API      http://localhost:{port}")
    print(f"  Docs     http://localhost:{port}/docs")
    print(f"  Health   http://localhost:{port}/api/stats/health")
    if port != 8000:
        print()
        print("  The dashboard defaults to port 8000. Point it here:")
        print(f"    frontend/.env  ->  VITE_API_BASE_URL=http://localhost:{port}")
        print("  then restart `npm run dev`.")
    print()

    import uvicorn
    uvicorn.run("app.main:app", host=args.host, port=port,
                reload=not args.no_reload)
    return 0


if __name__ == "__main__":
    sys.exit(main())
