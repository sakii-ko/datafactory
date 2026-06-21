import json
from pathlib import Path

from datafarm.cli import main


def test_cli_run_mock(tmp_path, capsys):
    rc = main(["run", "--backend", "mock", "--name", "cli0", "--episodes", "2",
               "--steps", "10", "--res", "32x32", "--out", str(tmp_path)])
    assert rc == 0
    rep = json.loads(capsys.readouterr().out)
    assert rep["kept"] == 2
    assert (Path(tmp_path) / "cli0" / "index.jsonl").exists()


def test_cli_healthcheck_stub_backend(capsys):
    rc = main(["healthcheck", "--backend", "video"])
    out = json.loads(capsys.readouterr().out)
    assert rc == 1 and out["ok"] is False


def test_cli_run_multi_viewpoint(tmp_path, capsys):
    rc = main(["run", "--backend", "mock", "--name", "cli1", "--episodes", "2",
               "--steps", "10", "--res", "32x32", "--viewpoints", "fpv,tpv", "--out", str(tmp_path)])
    assert rc == 0
    rep = json.loads(capsys.readouterr().out)
    assert rep["buckets"]["fpv/precise_action"] == 1
