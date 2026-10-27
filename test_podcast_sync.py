import contextlib
import io
import unittest

import podcast_sync as sync


def episode(uri, status, **extra):
    result = {"uri": uri, **extra}
    if status is not None:
        result["resume_point"] = {"fully_played": status}
    return result


class PlannerTests(unittest.TestCase):
    def test_only_removes_finished_or_explicitly_excluded_episodes(self):
        playlist = [
            {"item": {"uri": "already-unplayed"}},
            {"track": {"uri": "finished"}},
            {"item": {"uri": "unknown"}},
            {"item": {"uri": "other-podcast", "show": {"id": "different"}}},
            {"item": {"uri": "excluded-catalog"}},
            {"item": {"uri": "excluded-show", "show": {"id": sync.EXCLUDED_SHOW}}},
            {"item": {"uri": "music"}},
        ]
        eps = [
            episode("already-unplayed", False),
            episode("new-unplayed", False),
            episode("new-in-progress", False, resume_position_ms=12345),
            episode("new-unplayed", False),
            episode("finished", True),
            episode("unknown", None),
            episode("unavailable", False, is_playable=False),
        ]
        plan = sync.make_plan(eps, playlist, {"excluded-catalog"})
        self.assertEqual(plan.add, ["new-unplayed", "new-in-progress"])
        self.assertEqual(set(plan.remove), {"finished", "excluded-catalog", "excluded-show"})
        self.assertEqual(plan.unknown, 1)
        self.assertEqual(plan.known, 6)

    def test_absent_or_invalid_playback_status_never_adds_or_removes(self):
        eps = [episode("unknown1", None), {"uri": "unknown2", "resume_point": {"fully_played": "false"}}]
        plan = sync.make_plan(eps, [{"item": {"uri": "unknown1"}}], set())
        self.assertEqual(plan.add, [])
        self.assertEqual(plan.remove, [])
        self.assertEqual(plan.unknown, 2)

    def test_no_statuses_fails_before_mutating(self):
        class Client:
            def request(self, *args, **kwargs):
                self.fail("must not mutate")
        with contextlib.redirect_stdout(io.StringIO()), self.assertRaises(sync.SyncError):
            sync.execute_plan(Client(), sync.Plan([], ["excluded"], 1, 0))

    def test_actions_are_batched_and_dry_run_does_nothing(self):
        class Client:
            def __init__(self): self.calls = []
            def request(self, method, path, **kwargs): self.calls.append((method, path, kwargs))
        client = Client()
        plan = sync.Plan([f"episode-{i}" for i in range(101)], [f"old-{i}" for i in range(101)], 0, 202)
        with contextlib.redirect_stdout(io.StringIO()):
            sync.execute_plan(client, plan, dry_run=True)
            self.assertEqual(client.calls, [])
            sync.execute_plan(client, plan)
        self.assertEqual([call[0] for call in client.calls], ["DELETE", "DELETE", "POST", "POST"])
        self.assertEqual(len(client.calls[0][2]["data"]["items"]), 100)
        self.assertEqual(len(client.calls[1][2]["data"]["items"]), 1)
        self.assertEqual(len(client.calls[2][2]["data"]["uris"]), 100)
        self.assertEqual(len(client.calls[3][2]["data"]["uris"]), 1)


class FetchTests(unittest.TestCase):
    def test_pagination_uses_offsets_and_all_pages(self):
        class Client(sync.Spotify):
            def __init__(self): self.offsets = []
            def request(self, method, path, params=None, data=None):
                self.offsets.append(params["offset"])
                return {"items": [1, 2], "next": "yes"} if params["offset"] == 0 else {"items": [3], "next": None}
        client = Client()
        self.assertEqual(list(client.pages("/test")), [1, 2, 3])
        self.assertEqual(client.offsets, [0, 2])

    def test_failed_show_fetch_does_not_mutate_playlist(self):
        class Client:
            def __init__(self): self.writes = []
            def pages(self, path, **kwargs):
                if path.startswith("/playlists/"): return iter([])
                if sync.INCLUDED_SHOWS[0] in path: raise sync.SyncError("show failed")
                return iter([])
            def request(self, method, path, **kwargs): self.writes.append(method)
        client = Client()
        with self.assertRaises(sync.SyncError): sync.sync(client)
        self.assertEqual(client.writes, [])


if __name__ == "__main__":
    unittest.main()
