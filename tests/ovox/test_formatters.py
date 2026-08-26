"""ovox table/CSV formatters — keep them aligned with the web export helpers."""
from __future__ import annotations

import importlib.util
from pathlib import Path

_PATH = (
    Path(__file__).resolve().parents[2] / "ovox" / "ovox" / "utils" / "formatters.py"
)
_spec = importlib.util.spec_from_file_location("ovox_formatters", _PATH)
assert _spec and _spec.loader
_fmt = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_fmt)

results_to_csv = _fmt.results_to_csv
results_to_markdown = _fmt.results_to_markdown


SAMPLE = [
    {"certname": "web01", "status": "changed"},
    {"certname": "db01", "status": "unchanged"},
]


def test_markdown_table_headers_and_rows():
    md = results_to_markdown(SAMPLE)
    assert md.startswith("| certname | status |")
    assert "| --- | --- |" in md
    assert "| web01 | changed |" in md
    assert "| db01 | unchanged |" in md


def test_markdown_empty():
    assert results_to_markdown([]) == "_No results_"


def test_markdown_escapes_pipes():
    md = results_to_markdown([{"note": "a|b"}])
    assert "a\\|b" in md


def test_csv_round_trip_shape():
    csv = results_to_csv(SAMPLE)
    lines = csv.splitlines()
    assert lines[0] == "certname,status"
    assert "web01,changed" in lines
    assert "db01,unchanged" in lines


def test_csv_quotes_commas():
    csv = results_to_csv([{"msg": "hello, world"}])
    assert '"hello, world"' in csv


def test_csv_empty():
    assert results_to_csv([]) == ""
