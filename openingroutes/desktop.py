import argparse
import os
import socket
import sys
import threading
import time
from pathlib import Path

import uvicorn

from .api import create_app


def main():
    args = argparse.ArgumentParser(description="OpeningRoutes local desktop and browser application")
    args.add_argument(
        "--browser", action="store_true", help="Serve the local browser edition without a native window"
    )
    args.add_argument("--port", type=int, default=8765)
    args.add_argument("--data", type=Path)
    options = args.parse_args()
    if options.data:
        root = options.data.resolve()
    elif getattr(sys, "frozen", False):
        root = Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "OpeningRoutes"
    else:
        root = Path(".local/data").resolve()
    bundle = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[1]))
    web = bundle / ("web" if getattr(sys, "frozen", False) else "web/dist")
    if not (web / "index.html").exists():
        raise SystemExit("Web assets are missing. Run npm ci and npm run build in web/ first.")
    app = create_app(root, web_root=web)
    if options.browser:
        uvicorn.run(app, host="127.0.0.1", port=options.port, log_level="warning")
        return
    import webview

    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    for _ in range(200):
        if server.started:
            break
        time.sleep(0.05)
    else:
        raise SystemExit("Local service did not start.")
    webview.create_window(
        "OpeningRoutes",
        f"http://127.0.0.1:{port}",
        width=1440,
        height=960,
        min_size=(900, 650),
        text_select=True,
    )
    try:
        webview.start(gui="edgechromium", debug=False)
    finally:
        server.should_exit = True
        thread.join(timeout=5)


if __name__ == "__main__":
    main()
