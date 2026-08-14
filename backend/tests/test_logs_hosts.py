"""Log Viewer host routing (no Bolt)."""

from app.routers import logs as logs_mod


def test_is_local_host_aliases():
    assert logs_mod._is_local_host("local")
    assert logs_mod._is_local_host("localhost")
    assert logs_mod._is_local_host("")
    assert logs_mod._is_local_host("127.0.0.1")


def test_filter_host_journal_lines():
    lines = [
        "something puppet-agent said",
        "kernel: unrelated",
        "openvox-agent applied",
    ]
    out = logs_mod._filter_host_journal_lines(
        lines, ("puppet-agent", "openvox-agent")
    )
    assert len(out) == 2
    assert "kernel" not in "".join(out)


def test_cache_key_includes_host_and_grep():
    a = logs_mod._cache_key("puppetserver", "ovcompiler1.example", 200, None, None)
    b = logs_mod._cache_key("puppetserver", "ovcompiler2.example", 200, None, None)
    c = logs_mod._cache_key("puppetserver", "ovcompiler1.example", 200, None, "error")
    assert a != b
    assert a != c


def test_parse_prefers_stdout_json_over_stderr_noise():
    payload = '{"source":"puppetserver","lines":["ok"],"count":1}'
    parsed = logs_mod._parse_remote_log_payload(
        {"stdout": "", "stderr": "Uploaded file"},
        {"value": {"stdout": payload, "stderr": "journalctl: Warning: ..."}},
    )
    assert parsed.get("lines") == ["ok"]


def test_remote_source_alias():
    assert logs_mod._REMOTE_SOURCE_ALIAS["openvox-ca"] == "puppetserver"
    assert logs_mod._REMOTE_SOURCE_ALIAS["openvox-compiler"] == "puppetserver"


def test_bolt_stdout_lines_from_command_run():
    item = {"value": {"stdout": "line1\n-- No entries --\nline2\n", "exit_code": 0}}
    assert logs_mod._bolt_stdout_lines({}, item) == ["line1", "line2"]


def test_first_bolt_item_from_wrapper():
    blob = '{"items":[{"target":"ovcompiler1.example","value":{"stdout":"ok"}}]}'
    item = logs_mod._first_bolt_item({"stdout": "warn\n" + blob})
    assert item.get("target") == "ovcompiler1.example"
