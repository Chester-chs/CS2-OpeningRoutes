import sys
from unittest.mock import patch

from openingroutes import desktop


def test_packaged_browser_mode_starts_without_console_streams(tmp_path, monkeypatch):
    (tmp_path / "web/dist").mkdir(parents=True)
    (tmp_path / "web/dist/index.html").write_text("test")
    monkeypatch.setattr(desktop, "__file__", str(tmp_path / "openingroutes/desktop.py"))
    monkeypatch.setattr(sys, "argv", ["launch.py", "--browser", "--data", str(tmp_path / "data")])
    with (
        patch("uvicorn.Server.run", lambda server: setattr(server, "started", True)),
        patch.object(sys, "stdout", None),
        patch.object(sys, "stderr", None),
    ):
        desktop.main()
