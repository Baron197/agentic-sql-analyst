"""`poe demo`: the launcher's checks and its process cleanup (no servers started)."""

import os
import subprocess
import sys

from sql_analyst import demo


def test_asks_for_web_install_first(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    assert demo.main() == 1
    assert "poe web-install" in capsys.readouterr().out


def test_stop_ends_a_running_process():
    group = {} if os.name == "nt" else {"start_new_session": True}
    proc = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"], **group)
    demo.stop(proc)
    assert proc.poll() is not None
