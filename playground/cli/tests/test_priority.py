"""Tests for the priority module — helpers, formatters, and CLI commands."""

import json
from unittest.mock import patch, MagicMock

import pytest
from click.testing import CliRunner

from slurm_playground.priority import (
    _safe_float,
    _safe_int,
    _bar,
    _fairshare_style,
    _state_style,
    _compact_num,
    _build_watch_line,
    _format_watch_line,
    _format_tmux_status,
    priority,
)


# ── Pure helper tests (no I/O) ──────────────────────────────────────


class TestSafeFloat:
    def test_valid(self):
        assert _safe_float("3.14") == pytest.approx(3.14)

    def test_integer_string(self):
        assert _safe_float("42") == 42.0

    def test_whitespace(self):
        assert _safe_float("  1.5  ") == pytest.approx(1.5)

    def test_empty(self):
        assert _safe_float("") == 0.0

    def test_garbage(self):
        assert _safe_float("abc") == 0.0

    def test_none(self):
        assert _safe_float(None) == 0.0


class TestSafeInt:
    def test_valid(self):
        assert _safe_int("42") == 42

    def test_whitespace(self):
        assert _safe_int("  7  ") == 7

    def test_empty(self):
        assert _safe_int("") == 0

    def test_float_string(self):
        assert _safe_int("3.14") == 0  # int() can't parse floats

    def test_none(self):
        assert _safe_int(None) == 0


class TestBar:
    def test_full(self):
        bar = _bar(1.0, 1.0, width=10)
        assert bar == "█" * 10

    def test_empty(self):
        bar = _bar(0.0, 1.0, width=10)
        assert bar == "░" * 10

    def test_half(self):
        bar = _bar(0.5, 1.0, width=10)
        assert bar == "█" * 5 + "░" * 5

    def test_over_max(self):
        bar = _bar(2.0, 1.0, width=10)
        assert bar == "█" * 10  # capped at max

    def test_zero_max(self):
        bar = _bar(0.5, 0.0, width=10)
        assert bar == "░" * 10

    def test_default_width(self):
        bar = _bar(1.0, 1.0)
        assert len(bar) == 15


class TestFairshareStyle:
    def test_high(self):
        assert _fairshare_style(0.9) == "bold green"

    def test_good(self):
        assert _fairshare_style(0.6) == "green"

    def test_moderate(self):
        assert _fairshare_style(0.4) == "yellow"

    def test_low(self):
        assert _fairshare_style(0.15) == "rgb(255,165,0)"

    def test_depleted(self):
        assert _fairshare_style(0.05) == "red"

    def test_boundary_08(self):
        assert _fairshare_style(0.8) == "bold green"

    def test_boundary_05(self):
        assert _fairshare_style(0.5) == "green"

    def test_boundary_03(self):
        assert _fairshare_style(0.3) == "yellow"

    def test_boundary_01(self):
        assert _fairshare_style(0.1) == "rgb(255,165,0)"


class TestStateStyle:
    def test_running(self):
        assert _state_style("RUNNING") == "green"
        assert _state_style("R") == "green"

    def test_pending(self):
        assert _state_style("PENDING") == "yellow"
        assert _state_style("PD") == "yellow"

    def test_completing(self):
        assert _state_style("COMPLETING") == "cyan"
        assert _state_style("CG") == "cyan"

    def test_other(self):
        assert _state_style("FAILED") == "dim"
        assert _state_style("UNKNOWN") == "dim"


class TestCompactNum:
    def test_small(self):
        assert _compact_num(42) == "42"
        assert _compact_num(999) == "999"

    def test_thousands(self):
        assert _compact_num(1234) == "1.2k"
        assert _compact_num(5024) == "5.0k"

    def test_ten_thousands(self):
        assert _compact_num(25000) == "25k"
        assert _compact_num(99999) == "100k"

    def test_millions(self):
        assert _compact_num(1500000) == "1.5M"
        assert _compact_num(10000000) == "10.0M"

    def test_zero(self):
        assert _compact_num(0) == "0"


# ── Format function tests ──────────────────────────────────────────


def _make_data(**overrides):
    """Build a standard test data dict."""
    data = {
        "timestamp": "12:00:00",
        "running": 5024,
        "pending": 24976,
        "total": 30000,
        "top_fs": {"user": "user44", "account": "linguistics", "fairshare": 0.98},
        "low_fs": {"user": "user13", "account": "cs", "fairshare": 0.12},
    }
    data.update(overrides)
    return data


class TestFormatWatchLine:
    def test_basic(self):
        line = _format_watch_line(_make_data())
        assert "R:5.0k" in line
        assert "P:25k" in line
        assert "user44" in line
        assert "user13" in line

    def test_with_user(self):
        data = _make_data(user={
            "name": "user01", "account": "physics", "fairshare": 0.82,
            "rank": 3, "total_pending": 24976,
            "running": 10, "pending": 50,
        })
        line = _format_watch_line(data)
        assert "user01" in line
        assert "fs:0.82" in line
        assert "#3/" in line
        assert "r:10" in line
        assert "p:50" in line

    def test_with_account(self):
        data = _make_data(account={
            "name": "physics", "fairshare": 0.65,
            "running": 100, "pending": 500,
        })
        line = _format_watch_line(data)
        assert "physics" in line
        assert "fs:0.65" in line

    def test_no_fairshare_extremes(self):
        data = {"timestamp": "12:00:00", "running": 0, "pending": 0, "total": 0}
        line = _format_watch_line(data)
        assert "R:0" in line
        assert "P:0" in line

    def test_pipe_separators(self):
        line = _format_watch_line(_make_data())
        assert " | " in line


class TestFormatTmuxStatus:
    def test_plain(self):
        out = _format_tmux_status(_make_data())
        assert "R:" in out
        assert "P:" in out
        assert "#[" not in out  # no color codes

    def test_color(self):
        out = _format_tmux_status(_make_data(), color=True)
        assert "#[fg=green]" in out
        assert "#[default]" in out

    def test_max_width(self):
        out = _format_tmux_status(_make_data(), max_width=20)
        assert len(out) <= 20

    def test_with_user(self):
        data = _make_data(user={
            "name": "user01", "fairshare": 0.82,
            "rank": 3,
        })
        out = _format_tmux_status(data)
        assert "fs:0.82" in out
        assert "#3" in out

    def test_with_user_color_styles(self):
        # High fairshare → green
        data = _make_data(user={"name": "u1", "fairshare": 0.9, "rank": 1})
        out = _format_tmux_status(data, color=True)
        assert "#[fg=green]" in out

        # Low fairshare → red
        data["user"]["fairshare"] = 0.1
        out = _format_tmux_status(data, color=True)
        assert "#[fg=red]" in out

    def test_default_under_50_chars(self):
        out = _format_tmux_status(_make_data())
        assert len(out) <= 50


# ── CLI command tests (mocked I/O) ──────────────────────────────────


@pytest.fixture
def runner():
    return CliRunner()


@pytest.fixture
def mock_cluster_running():
    with patch("slurm_playground.priority.is_cluster_running", return_value=True):
        yield


@pytest.fixture
def mock_cluster_stopped():
    with patch("slurm_playground.priority.is_cluster_running", return_value=False):
        yield


@pytest.fixture
def mock_watch_data():
    data = _make_data(
        user={"name": "user01", "fairshare": 0.82, "rank": 3,
              "total_pending": 24976, "running": 10, "pending": 50,
              "account": "physics"},
        next_job={"user": "user44", "job_id": "84523", "priority": 15000},
    )
    with patch("slurm_playground.priority._build_watch_line", return_value=data):
        yield data


class TestWatchCommand:
    def test_cluster_not_running(self, runner, mock_cluster_stopped):
        result = runner.invoke(priority, ["watch", "--no-loop"])
        assert result.exit_code == 0
        assert "not running" in result.output

    def test_no_loop_short(self, runner, mock_cluster_running, mock_watch_data):
        result = runner.invoke(priority, ["watch", "--no-loop"])
        assert result.exit_code == 0
        assert "R:5.0k" in result.output
        assert "P:25k" in result.output

    def test_no_loop_json(self, runner, mock_cluster_running, mock_watch_data):
        result = runner.invoke(priority, ["watch", "--no-loop", "--format", "json"])
        assert result.exit_code == 0
        parsed = json.loads(result.output)
        assert parsed["running"] == 5024
        assert parsed["pending"] == 24976

    def test_no_loop_json_cluster_down(self, runner, mock_cluster_stopped):
        result = runner.invoke(priority, ["watch", "--no-loop", "--format", "json"])
        assert result.exit_code == 0
        parsed = json.loads(result.output)
        assert "error" in parsed


class TestTmuxStatusCommand:
    def test_cluster_not_running(self, runner, mock_cluster_stopped):
        result = runner.invoke(priority, ["tmux-status"])
        assert result.exit_code == 0
        assert "slurm:down" in result.output

    def test_plain(self, runner, mock_cluster_running, mock_watch_data):
        result = runner.invoke(priority, ["tmux-status"])
        assert result.exit_code == 0
        assert "R:" in result.output
        assert "#[" not in result.output  # no tmux color codes

    def test_with_user(self, runner, mock_cluster_running, mock_watch_data):
        result = runner.invoke(priority, ["tmux-status", "-u", "user01"])
        assert result.exit_code == 0
        assert "fs:" in result.output

    def test_with_color(self, runner, mock_cluster_running, mock_watch_data):
        result = runner.invoke(priority, ["tmux-status", "--color"])
        assert result.exit_code == 0
        assert "#[fg=" in result.output


class TestShowCommand:
    def test_cluster_not_running(self, runner, mock_cluster_stopped):
        result = runner.invoke(priority, ["show"])
        assert result.exit_code == 0
        assert "not running" in result.output


class TestFairshareCommand:
    def test_cluster_not_running(self, runner, mock_cluster_stopped):
        result = runner.invoke(priority, ["fairshare"])
        assert result.exit_code == 0
        assert "not running" in result.output

    def test_no_data(self, runner, mock_cluster_running):
        with patch("slurm_playground.priority.get_fairshare_data", return_value=[]):
            result = runner.invoke(priority, ["fairshare"])
            assert result.exit_code == 0
            assert "No fairshare data" in result.output


class TestFactorsCommand:
    def test_cluster_not_running(self, runner, mock_cluster_stopped):
        result = runner.invoke(priority, ["factors"])
        assert result.exit_code == 0
        assert "not running" in result.output

    def test_no_data(self, runner, mock_cluster_running):
        with patch("slurm_playground.priority.get_priority_factors", return_value=[]):
            result = runner.invoke(priority, ["factors"])
            assert result.exit_code == 0
            assert "No pending jobs" in result.output

    def test_user_filter_no_match(self, runner, mock_cluster_running):
        mock_factors = [
            {"job_id": "100", "user": "alice", "priority": 1000,
             "age": 100, "fairshare": 500, "jobsize": 200, "partition": 100, "qos": 100},
        ]
        with patch("slurm_playground.priority.get_priority_factors", return_value=mock_factors):
            result = runner.invoke(priority, ["factors", "-u", "bob"])
            assert result.exit_code == 0
            assert "No pending jobs for user" in result.output


class TestExplainCommand:
    def test_cluster_not_running(self, runner, mock_cluster_stopped):
        result = runner.invoke(priority, ["explain", "12345"])
        assert result.exit_code == 0
        assert "not running" in result.output
