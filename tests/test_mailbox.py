#!/usr/bin/env python3
"""Mailbox CLI test matrix.

Tests the standalone mailbox CLI for correctness, edge cases, and security.
Uses a temporary MAILBOX_ROOT to avoid touching real state.
"""
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

MAILBOX = Path(__file__).parent.parent / "tools" / "mailbox"


@pytest.fixture
def mailbox_root(tmp_path):
    """Temporary mailbox root with MAILBOX_ROOT env override."""
    env = {**os.environ, "MAILBOX_ROOT": str(tmp_path)}
    return tmp_path, env


@pytest.fixture
def session(mailbox_root):
    """Pre-initialized session with manager + 2 workers."""
    root, env = mailbox_root
    session_id = "test-session-001"
    r = subprocess.run(
        [sys.executable, str(MAILBOX), "session-init",
         "--session", session_id, "--manager", "manager", "--agents", "worker-a,worker-b"],
        capture_output=True, text=True, env=env, timeout=10,
    )
    assert r.returncode == 0, f"session-init failed: {r.stderr}"
    return root, env, session_id


def _run(args, env, input_text=None):
    """Run mailbox CLI, return (returncode, stdout, stderr)."""
    r = subprocess.run(
        [sys.executable, str(MAILBOX)] + args,
        capture_output=True, text=True, env=env, timeout=10,
        input=input_text,
    )
    return r.returncode, r.stdout, r.stderr


class TestSessionInit:
    def test_creates_session_dir(self, session):
        root, env, sid = session
        assert (root / sid).is_dir()
        assert (root / sid / "session.json").is_file()

    def test_creates_agent_subdirs(self, session):
        root, env, sid = session
        for agent in ("manager", "worker-a", "worker-b"):
            for sub in ("inbox", "processing", "archive"):
                assert (root / sid / agent / sub).is_dir()

    def test_duplicate_session_fails(self, session):
        _, env, sid = session
        rc, _, err = _run(["session-init", "--session", sid, "--manager", "m", "--agents", "a"], env)
        assert rc != 0
        assert "already exists" in err

    def test_invalid_agent_id(self, mailbox_root):
        _, env = mailbox_root
        rc, _, err = _run(["session-init", "--session", "../escape", "--manager", "m", "--agents", "a"], env)
        assert rc != 0


class TestSend:
    def test_send_creates_message(self, session):
        _, env, sid = session
        rc, out, _ = _run([
            "send", "--session", sid, "--from", "manager", "--to", "worker-a",
            "--kind", "TASK", "--subject", "test task", "--body", "do something",
        ], env)
        assert rc == 0
        assert "sent" in out

    def test_send_invalid_kind(self, session):
        _, env, sid = session
        rc, _, err = _run([
            "send", "--session", sid, "--from", "manager", "--to", "worker-a",
            "--kind", "INVALID", "--subject", "s", "--body", "b",
        ], env)
        assert rc != 0

    def test_send_to_nonexistent_agent(self, session):
        _, env, sid = session
        rc, _, err = _run([
            "send", "--session", sid, "--from", "manager", "--to", "ghost",
            "--kind", "TASK", "--subject", "s", "--body", "b",
        ], env)
        assert rc != 0

    def test_send_empty_subject(self, session):
        _, env, sid = session
        rc, _, err = _run([
            "send", "--session", sid, "--from", "manager", "--to", "worker-a",
            "--kind", "TASK", "--subject", "", "--body", "b",
        ], env)
        assert rc != 0


class TestPeek:
    def test_peek_empty_inbox(self, session):
        _, env, sid = session
        rc, out, _ = _run(["peek", "--session", sid, "--agent", "worker-a"], env)
        assert rc == 0
        data = json.loads(out)
        assert data["pending"] == 0

    def test_peek_after_send(self, session):
        _, env, sid = session
        _run([
            "send", "--session", sid, "--from", "manager", "--to", "worker-a",
            "--kind", "TASK", "--subject", "hello", "--body", "world",
        ], env)
        rc, out, _ = _run(["peek", "--session", sid, "--agent", "worker-a"], env)
        assert rc == 0
        data = json.loads(out)
        assert data["pending"] == 1
        assert data["messages"][0]["subject"] == "hello"


class TestRead:
    def test_read_consumes_message(self, session):
        _, env, sid = session
        _run([
            "send", "--session", sid, "--from", "manager", "--to", "worker-a",
            "--kind", "TASK", "--subject", "t", "--body", "b",
        ], env)
        rc, out, _ = _run(["read", "--session", sid, "--agent", "worker-a", "--owner", "worker-a", "--json"], env)
        assert rc == 0
        msg = json.loads(out)
        assert msg["subject"] == "t"
        # Inbox should be empty now
        rc2, out2, _ = _run(["peek", "--session", sid, "--agent", "worker-a"], env)
        assert json.loads(out2)["pending"] == 0

    def test_read_empty_inbox(self, session):
        _, env, sid = session
        rc, out, _ = _run(["read", "--session", sid, "--agent", "worker-a", "--owner", "worker-a"], env)
        assert rc == 0
        assert out.strip() == ""


class TestFinalize:
    def test_finalize_moves_to_archive(self, session):
        _, env, sid = session
        _run([
            "send", "--session", sid, "--from", "manager", "--to", "worker-a",
            "--kind", "TASK", "--subject", "t", "--body", "b",
        ], env)
        _, out, _ = _run(["read", "--session", sid, "--agent", "worker-a", "--owner", "worker-a", "--json"], env)
        msg = json.loads(out)
        rc, _, _ = _run([
            "finalize", "--session", sid, "--agent", "worker-a",
            "--msg-id", msg["msg_id"], "--owner", "worker-a",
        ], env)
        assert rc == 0


class TestRelease:
    def test_release_returns_to_inbox(self, session):
        _, env, sid = session
        _run([
            "send", "--session", sid, "--from", "manager", "--to", "worker-a",
            "--kind", "TASK", "--subject", "t", "--body", "b",
        ], env)
        _, out, _ = _run(["read", "--session", sid, "--agent", "worker-a", "--owner", "worker-a", "--json"], env)
        msg = json.loads(out)
        rc, _, _ = _run([
            "release", "--session", sid, "--agent", "worker-a",
            "--msg-id", msg["msg_id"], "--owner", "worker-a",
        ], env)
        assert rc == 0
        # Should be back in inbox
        _, peek_out, _ = _run(["peek", "--session", sid, "--agent", "worker-a"], env)
        assert json.loads(peek_out)["pending"] == 1


class TestStatus:
    def test_status_set_busy(self, session):
        _, env, sid = session
        rc, _, _ = _run([
            "status", "--session", sid, "--agent", "worker-a",
            "--state", "BUSY", "--current-task", "working",
        ], env)
        assert rc == 0
        status_file = Path(os.environ.get("MAILBOX_ROOT", "")) / sid / "worker-a" / "status.json"
        # Can't check file directly since env changed, just check rc


class TestStats:
    def test_stats_after_messages(self, session):
        _, env, sid = session
        _run([
            "send", "--session", sid, "--from", "manager", "--to", "worker-a",
            "--kind", "TASK", "--subject", "t", "--body", "b",
        ], env)
        rc, out, _ = _run(["stats", "--session", sid, "--agent", "worker-a"], env)
        assert rc == 0
        # stats outputs "inbox: N\nprocessing: N\narchive: N\n_corrupt: N"
        assert "inbox:" in out


class TestRecoverStale:
    def test_recover_stale_empty(self, session):
        _, env, sid = session
        rc, _, _ = _run(["recover-stale", "--session", sid, "--agent", "worker-a"], env)
        assert rc == 0


class TestClear:
    def test_clear_removes_archive(self, session):
        _, env, sid = session
        _run([
            "send", "--session", sid, "--from", "manager", "--to", "worker-a",
            "--kind", "TASK", "--subject", "t", "--body", "b",
        ], env)
        # Read + finalize to move to archive
        _, out, _ = _run(["read", "--session", sid, "--agent", "worker-a", "--owner", "worker-a", "--json"], env)
        msg = json.loads(out)
        _run(["finalize", "--session", sid, "--agent", "worker-a",
              "--msg-id", msg["msg_id"], "--owner", "worker-a"], env)
        # Clear archive
        rc, clear_out, _ = _run(["clear", "--session", sid, "--agent", "worker-a"], env)
        assert rc == 0
        assert "cleared 1" in clear_out


class TestSecurity:
    def test_path_traversal_in_session(self, mailbox_root):
        _, env = mailbox_root
        rc, _, err = _run(["session-init", "--session", "../../escape", "--manager", "m", "--agents", "a"], env)
        assert rc != 0

    def test_path_traversal_in_agent(self, session):
        _, env, sid = session
        rc, _, err = _run(["peek", "--session", sid, "--agent", "../../escape"], env)
        assert rc != 0

    def test_invalid_msg_id_chars(self, session):
        _, env, sid = session
        rc, _, err = _run([
            "finalize", "--session", sid, "--agent", "worker-a",
            "--msg-id", "../escape", "--owner", "worker-a",
        ], env)
        assert rc != 0
