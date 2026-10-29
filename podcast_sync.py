#!/usr/bin/env python3
"""Sync eight Tech & Life podcast shows to Spotify, with post-write verification.

Only explicitly known playback states are processed. Credentials are loaded
from the GitHub Actions secret; they are never written to source files or logs.
"""
from __future__ import annotations

import argparse
from collections import Counter
from dataclasses import dataclass
import json
import os
from pathlib import Path
import sys
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

CLIENT_ID = "863d034412554af6be0f88f51becfe89"
API_ROOT = "https://api.spotify.com/v1"
TOKEN_URL = "https://accounts.spotify.com/api/token"
_CONFIG = json.loads(Path(__file__).with_name("podcast_config.json").read_text(encoding="utf-8"))
PLAYLIST_ID = "0Hu69WnnxAgPP59X46XMQs"
if _CONFIG.get("playlist_id") != PLAYLIST_ID:
    raise RuntimeError("Unexpected playlist in podcast_config.json.")
INCLUDED_SHOWS = tuple(_CONFIG["shows"])
if len(INCLUDED_SHOWS) != 8:
    raise RuntimeError("Expected eight podcast shows in podcast_config.json.")
EXCLUDED_SHOW = "30CG2yb1mBN9ahkaZUKT69"


class SyncError(Exception):
    pass


class Spotify:
    def __init__(self, refresh_token: str):
        if not refresh_token:
            raise SyncError("SPOTIFY_REFRESH_TOKEN is missing")
        self.refresh_token = refresh_token
        self.token = ""
        self.expires_at = 0.0

    def _read_json(self, request: Request):
        with urlopen(request, timeout=45) as response:
            payload = response.read()
            return json.loads(payload.decode("utf-8")) if payload else {}

    def access_token(self) -> str:
        if self.token and time.time() < self.expires_at:
            return self.token
        body = urlencode({
            "grant_type": "refresh_token",
            "refresh_token": self.refresh_token,
            "client_id": CLIENT_ID,
        }).encode()
        try:
            result = self._read_json(Request(TOKEN_URL, data=body, method="POST"))
        except HTTPError as exc:
            raise SyncError(f"Spotify authorization failed (HTTP {exc.code}); check the repository secret") from None
        rotated = result.get("refresh_token")
        if rotated and rotated != self.refresh_token:
            raise SyncError("Spotify rotated the refresh token; update the GitHub Actions secret")
        self.token = result.get("access_token", "")
        if not self.token:
            raise SyncError("Spotify returned no access token")
        self.expires_at = time.time() + max(0, int(result.get("expires_in", 3600)) - 60)
        return self.token

    def request(self, method: str, path: str, *, params=None, data=None):
        url = API_ROOT + path
        if params:
            url += "?" + urlencode(params)
        body = json.dumps(data).encode() if data is not None else None
        for attempt in range(4):
            request = Request(url, data=body, method=method, headers={
                "Authorization": "Bearer " + self.access_token(),
                "Content-Type": "application/json",
            })
            try:
                return self._read_json(request)
            except HTTPError as exc:
                if exc.code == 429 and attempt < 3:
                    try:
                        detail = json.loads(exc.read().decode("utf-8"))
                    except (ValueError, UnicodeDecodeError):
                        detail = {}
                    error = detail.get("error") if isinstance(detail, dict) else None
                    if isinstance(error, dict) and error.get("reason") == "QUOTA_EXCEEDED":
                        raise SyncError("Spotify API quota exceeded; retry later") from None
                    wait = exc.headers.get("Retry-After", "3")
                    delay = int(wait) if wait.isdigit() else 3
                    if delay > 60:
                        raise SyncError("Spotify rate limited this run; retry later") from None
                    time.sleep(max(delay, 1))
                    continue
                raise SyncError(f"Spotify returned HTTP {exc.code} during {method} {path}") from None
            except (URLError, OSError, TimeoutError):
                # Never automatically repeat a write if its response was lost.
                raise SyncError(f"Network error during {method} {path}; retry on the next sync") from None
            except (ValueError, UnicodeDecodeError):
                raise SyncError(f"Invalid Spotify JSON during {method} {path}") from None
        raise SyncError("Spotify API rate-limit retries exhausted")

    def pages(self, path: str, **extra):
        offset = 0
        expected_total = None
        for _ in range(2000):
            page = self.request("GET", path, params={"limit": 50, "offset": offset, **extra})
            items = page.get("items")
            if not isinstance(items, list):
                raise SyncError(f"Invalid Spotify page for {path}")
            total = page.get("total")
            if isinstance(total, int):
                if expected_total is not None and expected_total != total:
                    raise SyncError(f"Spotify catalog changed while reading {path}; retry later")
                expected_total = total
            yield from items
            offset += len(items)
            if not page.get("next"):
                if expected_total is not None and expected_total != offset:
                    raise SyncError(f"Incomplete catalog for {path}; retry later")
                return
            if not items:
                raise SyncError(f"Empty page with a next link for {path}")
        raise SyncError(f"Too many catalog pages for {path}")


@dataclass
class Plan:
    add: list[str]
    remove: list[str]
    unknown: int
    known: int


def _entry_item(entry):
    if not isinstance(entry, dict):
        return {}
    item = entry.get("item") or entry.get("track") or {}
    return item if isinstance(item, dict) else {}


def make_plan(episodes, playlist_items, excluded_uris) -> Plan:
    """Reconcile managed shows only; preserve all other playlist items."""
    present = Counter()
    removal = set()
    for entry in playlist_items:
        item = _entry_item(entry)
        uri = item.get("uri")
        if not isinstance(uri, str):
            continue
        present[uri] += 1
        show = item.get("show") or {}
        if uri in excluded_uris or (isinstance(show, dict) and show.get("id") == EXCLUDED_SHOW):
            removal.add(uri)

    additions = []
    desired = set()
    added = set()
    unknown = known = 0
    for episode in episodes:
        if episode is None:
            # Removed catalog item: never add based on missing playback data.
            continue
        if not isinstance(episode, dict):
            raise SyncError("Unexpected episode record in Spotify catalog")
        uri = episode.get("uri")
        if not isinstance(uri, str) or not uri:
            eid = episode.get("id")
            if (episode.get("type") == "episode" and isinstance(eid, str)
                    and len(eid) == 22 and eid.isascii() and eid.isalnum()):
                uri = "spotify:episode:" + eid
            elif episode.get("is_playable") is False:
                continue
            else:
                raise SyncError("Unidentifiable playable episode in Spotify catalog")
        if uri in excluded_uris:
            continue
        point = episode.get("resume_point")
        if not isinstance(point, dict) or not isinstance(point.get("fully_played"), bool):
            unknown += 1
            continue
        known += 1
        if point["fully_played"]:
            if present[uri]:
                removal.add(uri)
        elif episode.get("is_playable") is not False:
            desired.add(uri)
            if not present[uri] and uri not in added:
                additions.append(uri)
                added.add(uri)

    for uri in sorted(desired):
        if present[uri] > 1:
            removal.add(uri)
            if uri not in added:
                additions.append(uri)
                added.add(uri)
    return Plan(add=additions, remove=sorted(removal), unknown=unknown, known=known)


def execute_plan(client: Spotify, plan: Plan, *, dry_run=False):
    print(f"Playback status known: {plan.known}; unknown: {plan.unknown}; "
          f"episodes to add: {len(plan.add)}; episodes to remove/repair: {len(plan.remove)}")
    if plan.known == 0:
        raise SyncError("No playback statuses returned; check Spotify authorization scopes")
    if plan.unknown:
        raise SyncError("Unknown playback status: refusing playlist changes")
    if dry_run:
        print("Preview only: playlist unchanged.")
        return
    path = f"/playlists/{PLAYLIST_ID}/items"
    for i in range(0, len(plan.remove), 100):
        client.request("DELETE", path, data={"items": [{"uri": u} for u in plan.remove[i:i + 100]]})
    for i in range(0, len(plan.add), 100):
        client.request("POST", path, data={"uris": plan.add[i:i + 100]})
    print("Playlist sync changes submitted.")


def sync(client: Spotify, *, dry_run=False):
    path = f"/playlists/{PLAYLIST_ID}/items"
    before = list(client.pages(path, additional_types="track,episode"))
    excluded = {e["uri"] for e in client.pages(f"/shows/{EXCLUDED_SHOW}/episodes")
                if isinstance(e, dict) and isinstance(e.get("uri"), str)}
    episodes = []
    for show_id in INCLUDED_SHOWS:
        batch = list(client.pages(f"/shows/{show_id}/episodes"))
        if not batch:
            raise SyncError(f"No episodes returned for {_CONFIG['shows'][show_id]}; no changes made")
        print(f"Scanned {len(batch)} catalog entries from {_CONFIG['shows'][show_id]}.")
        episodes.extend(batch)
    plan = make_plan(episodes, before, excluded)
    execute_plan(client, plan, dry_run=dry_run)
    if not dry_run:
        after = list(client.pages(path, additional_types="track,episode"))
        audit = make_plan(episodes, after, excluded)
        if audit.unknown or audit.add or audit.remove:
            raise SyncError(f"Verification failed: {len(audit.add)} missing items and "
                            f"{len(audit.remove)} removals/repairs still needed")
        print("VERIFIED: all eligible episodes present once and fully played episodes removed.")


def main():
    parser = argparse.ArgumentParser(description="Sync eight Tech & Life podcasts to Spotify")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    try:
        sync(Spotify(os.environ.get("SPOTIFY_REFRESH_TOKEN", "").strip()), dry_run=args.dry_run)
    except (SyncError, OSError, ValueError, TypeError) as exc:
        print(f"Sync failed: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
