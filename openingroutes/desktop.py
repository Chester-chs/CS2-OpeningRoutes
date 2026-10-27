import argparse
import json
import os
import socket
import sys
import threading
import time
from pathlib import Path

import uvicorn

from .api import create_app
from .store import Store


def main():
    args = argparse.ArgumentParser(description="OpeningRoutes local desktop and browser application")
    args.add_argument(
        "--browser", action="store_true", help="Serve the local browser edition without a native window"
    )
    args.add_argument("--port", type=int, default=8765)
    args.add_argument("--data", type=Path)
    args.add_argument(
        "--smoke-test", action="store_true", help="Verify the native WebView without showing a window"
    )
    options = args.parse_args()
    if not 1024 <= options.port <= 65535:
        args.error("Port must be between 1024 and 65535")
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
    seed = bundle / "seed"
    if not (root / "library.sqlite").exists() and (seed / "matches.json").exists():
        import shutil

        store = Store(root)
        for match in json.loads((seed / "matches.json").read_text(encoding="utf-8")):
            store.save_match(match)
        if (seed / "timelines").is_dir():
            shutil.copytree(seed / "timelines", root / "timelines", dirs_exist_ok=True)
    app = create_app(root, web_root=web)
    if options.browser:
        uvicorn.run(app, host="127.0.0.1", port=options.port, log_level="warning", use_colors=False)
        return
    import webview

    with socket.socket() as probe:
        try:
            probe.bind(("127.0.0.1", options.port))
        except OSError as error:
            raise SystemExit(
                "OpeningRoutes port is already in use. Close the other local instance."
            ) from error
        port = options.port
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    for _ in range(200):
        if server.started:
            break
        time.sleep(0.05)
    else:
        raise SystemExit("Local service did not start.")
    window = webview.create_window(
        "OpeningRoutes",
        f"http://127.0.0.1:{port}",
        width=1440,
        height=960,
        min_size=(900, 650),
        text_select=True,
        hidden=options.smoke_test,
    )
    if options.smoke_test:

        def verify_window():
            result = {"native_webview": False}
            try:
                for _ in range(100):
                    ready = window.evaluate_js("document.querySelector('[data-ready=\"true\"]') !== null")
                    if ready:
                        break
                    time.sleep(0.1)
                result = {
                    "native_webview": bool(ready),
                    "title": window.evaluate_js("document.title"),
                    "heading": window.evaluate_js("document.querySelector('h1')?.textContent"),
                }
            except Exception as error:
                result["error"] = str(error)
            (root / "desktop-smoke.json").write_text(json.dumps(result), encoding="utf-8")
            window.destroy()

        window.events.loaded += verify_window
    try:
        webview.start(gui="edgechromium", debug=False, private_mode=False, storage_path=str(root / "webview"))
    finally:
        server.should_exit = True
        thread.join(timeout=5)


if __name__ == "__main__":
    main()
