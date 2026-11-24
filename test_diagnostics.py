import contextlib
import io
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import verified_sync as sync
from test_verified_sync import Client, CONFIG, episode


class SnapshotClient(Client):
    def __init__(self, snapshots, **kwargs):
        super().__init__(**kwargs)
        self.snapshots = iter(snapshots)

    def request(self, method, path, **kwargs):
        if method == "GET" and path == "/playlists/target":
            return {"snapshot_id": next(self.snapshots)}
        return super().request(method, path, **kwargs)


class DiagnosticTests(unittest.TestCase):
    def test_cli_diagnostic_selects_read_only_mode_even_with_sort(self):
        client = SnapshotClient(["a", "a"])
        output = io.StringIO()
        with patch.object(sys, "argv", ["verified_sync.py", "--diagnostic", "--sort"]), patch.object(sync, "Spotify", return_value=client), patch.object(Path, "read_text", return_value=json.dumps(CONFIG)), patch.dict(os.environ, {}, clear=True), contextlib.redirect_stdout(output):
            status = sync.main()
        self.assertEqual(status, 0)
        self.assertEqual(client.writes, [])
        self.assertIn('"snapshot_stable": true', output.getvalue())

    def test_stable_missing_twenty_is_read_only_and_reports_by_show(self):
        client = SnapshotClient(["a", "a"], episodes=[episode(str(i)) for i in range(20)])
        result = sync.diagnose(client, CONFIG)
        self.assertEqual(result["audit"]["missing"], 20)
        self.assertEqual(result["shows"][0]["missing"], 20)
        self.assertEqual(result["diagnostic"], {"read_only": True, "snapshot_stable": True, "attempts": 1})
        self.assertEqual(client.writes, [])

    def test_changed_snapshot_discards_first_result_and_retries(self):
        client = SnapshotClient(["a", "b", "b", "b"])
        with contextlib.redirect_stdout(io.StringIO()):
            result = sync.diagnose(client, CONFIG)
        self.assertEqual(result["diagnostic"]["attempts"], 2)
        self.assertEqual(client.writes, [])

    def test_changing_or_missing_snapshot_fails_without_writes(self):
        for snapshots in (["a", "b", "c", "d", "e", "f"], [None], [""]):
            client = SnapshotClient(snapshots)
            with contextlib.redirect_stdout(io.StringIO()), self.assertRaises(sync.SyncError):
                sync.diagnose(client, CONFIG)
            self.assertEqual(client.writes, [])

    def test_guard_blocks_unexpected_mutation(self):
        client = SnapshotClient(["a"])
        def unsafe(reader, *args, **kwargs):
            reader.request("POST", "/playlists/target/items", body={"uris": []})
        with patch.object(sync, "reconcile", side_effect=unsafe), self.assertRaisesRegex(sync.SyncError, "blocked"):
            sync.diagnose(client, CONFIG)
        self.assertEqual(client.writes, [])

    def test_silently_lost_additions_emit_failure_report_and_request_evidence(self):
        client = Client(episodes=[episode(str(i)) for i in range(20)])
        client.drop_add = True
        output = io.StringIO()
        with tempfile.TemporaryDirectory() as directory:
            summary = Path(directory) / "summary.txt"
            with patch.dict(os.environ, {"GITHUB_STEP_SUMMARY": str(summary)}), contextlib.redirect_stdout(output):
                with self.assertRaisesRegex(sync.SyncError, '"missing": 20'):
                    sync.reconcile(client, CONFIG)
            self.assertIn("FAILED: membership verification", summary.read_text())
        events = [json.loads(line) for line in output.getvalue().splitlines() if line.startswith('{"event"') or line.startswith('{"add"') or line.startswith('{"batch"')]
        self.assertEqual([e["event"] for e in events], ["membership_plan", "membership_write_attempt", "membership_write_response"])
        self.assertIn('"missing": 20', output.getvalue())
        self.assertIn('"responses"', output.getvalue())
        self.assertNotIn("spotify:episode:", output.getvalue())
        self.assertEqual(len(client.writes), 1)

    def test_uncertain_write_is_logged_once_and_never_retried(self):
        client = Client()
        output = io.StringIO()
        with patch.object(client, "request", side_effect=sync.SyncError("Network error")) as request:
            with contextlib.redirect_stdout(output), self.assertRaises(sync.SyncError):
                sync.reconcile(client, CONFIG)
        self.assertEqual(request.call_count, 1)
        self.assertIn("membership_write_attempt", output.getvalue())
        self.assertNotIn("membership_write_response", output.getvalue())

    def test_verify_only_failure_also_preserves_report_without_writes(self):
        client = Client()
        output = io.StringIO()
        with contextlib.redirect_stdout(output), patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(sync.SyncError):
                sync.reconcile(client, CONFIG, verify_only=True)
        self.assertIn('"missing": 1', output.getvalue())
        self.assertEqual(client.writes, [])


if __name__ == "__main__":
    unittest.main()
