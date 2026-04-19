"""Unit tests for vad_dashboard module (queue-drop only;
networking smoke-tested manually)."""
import pytest

import vad_dashboard


def test_dashboard_push_does_not_block_when_queue_full():
    """Dashboard.push() must never raise or block, even with no consumer."""
    dash = vad_dashboard.Dashboard(host="127.0.0.1", port=0, queue_max=5)
    for i in range(100):
        dash.push({"type": "frame", "i": i})  # must not raise
    assert dash._queue.qsize() <= 5


def test_dashboard_push_accepts_dicts_only():
    """Dashboard.push() must surface a clear error on non-dict."""
    dash = vad_dashboard.Dashboard(host="127.0.0.1", port=0, queue_max=5)
    with pytest.raises(TypeError):
        dash.push("not a dict")
