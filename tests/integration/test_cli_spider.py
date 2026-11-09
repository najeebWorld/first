import asyncio
import json
import subprocess
import sys
from pathlib import Path

import pytest

import spider_v2


def test_cli_runs_demo_without_credentials(monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["spider_v2.py", "--demo-elapsed", "120", "--query", "יונדאי", "--filters", '{"km_max":80000}'])
    asyncio.run(spider_v2.main())
    records = [json.loads(line) for line in capsys.readouterr().out.splitlines()]
    assert [record["listing"]["external_id"] for record in records] == ["demo-001", "demo-003", "demo-004"]
    assert [record["rule_result"]["status"] for record in records] == ["passed", "passed", "deferred"]


def test_cli_named_source_neutral_task(tmp_path, monkeypatch, capsys):
    path = tmp_path / "tasks.json"
    path.write_text(json.dumps([
        {"task_name": "selected", "source": "demo", "category": "vehicles", "text": "יונדאי"},
        {"task_name": "other", "source": "demo", "category": "vehicles"},
    ]), encoding="utf-8")
    monkeypatch.setattr(sys, "argv", ["spider_v2.py", "--config", str(path), "--task-name", "selected", "--demo-elapsed", "0"])
    asyncio.run(spider_v2.main())
    records = [json.loads(line) for line in capsys.readouterr().out.splitlines()]
    assert [record["listing"]["external_id"] for record in records] == ["demo-001"]


@pytest.mark.parametrize("arguments", [
    ["--task-name", "legacy"], ["--source", "xianyu"], ["--source", "yad2"],
    ["--demo-elapsed", "nan"], ["--demo-elapsed", "-1"], ["--debug-limit", "-1"],
])
def test_cli_rejects_unsafe_or_invalid_options(arguments, monkeypatch):
    monkeypatch.setattr(sys, "argv", ["spider_v2.py", *arguments])
    with pytest.raises(SystemExit) as error:
        asyncio.run(spider_v2.main())
    assert error.value.code == 2


def test_cli_import_does_not_load_legacy_network_stack():
    result = subprocess.run(
        [sys.executable, "-c", "import spider_v2, sys; assert not any(name in sys.modules for name in ('src.scraper', 'src.config', 'src.ai_handler', 'playwright', 'openai'))"],
        cwd=Path(__file__).resolve().parents[2], capture_output=True, text=True, timeout=15,
    )
    assert result.returncode == 0, result.stderr