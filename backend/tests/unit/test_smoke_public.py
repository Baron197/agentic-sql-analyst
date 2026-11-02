"""The deploy smoke test's event-stream parser must read what api/streaming.py writes."""

from infra.smoke_public import parse_sse
from sql_analyst.api.streaming import sse


def test_parse_sse_reads_the_api_format():
    stream = sse("step", {"node": "write_sql", "ms": 12.5}) + sse("done", {"run_id": "r1"})
    events = parse_sse(stream.splitlines(keepends=True))
    assert events == [("step", {"node": "write_sql", "ms": 12.5}), ("done", {"run_id": "r1"})]


def test_parse_sse_keeps_a_final_event_without_a_blank_line():
    assert parse_sse(["event: answer\n", 'data: {"status":"answered"}\n']) == [
        ("answer", {"status": "answered"})
    ]
