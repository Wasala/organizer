# dummy lines removed by editor bug workaround
import os

from file_analysis_agent.agent_tools import tools

DATA_FILE = os.path.join(os.path.dirname(__file__), "data", "sample.txt")


def test_set_and_top():
    res = tools.set(DATA_FILE)
    assert res["status"] == "ok"
    top = tools.top(start_line=2, num_lines=2)
    assert top["start_line"] == 2
    assert "Second line" in top["text"]


def test_tail_and_find():
    tools.set(DATA_FILE)
    tail = tools.tail(num_lines=2)
    assert "Fifth line" in tail["text"]
    hits = tools.find_within_doc("keyword")
    assert hits["hits"][0]["line"] == 4


def test_read_full_file():
    tools.set(DATA_FILE)
    res = tools.read_full_file()
    assert "First line" in res["text"]
    assert res["token_count"] > 0
