#!/usr/bin/env python3
"""Sync four podcasts to a Spotify playlist using a PKCE refresh token."""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from dataclasses import dataclass
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


# The same Spotify app and scopes as the existing WTJ playlist sync.
CLIENT_ID = "863d034412554af6be0f88f51becfe89"
API_ROOT = "https://api.spotify.com/v1"
TOKEN_URL = "https://accounts.spotify.com/api/token"
PLAYLIST_ID = "0Hu69WnnxAgPP59X46XMQs"
INCLUDED_SHOWS = (
    "0sJAtVorz8TsYDzzyM04cq",  # Office Drama
    "2GWSGMFIZ0xiisnboVE2HS",  # soju with sarah
    "6j2yaoEEkEwM4uctt0tYSe",  # Half Past Chai
    "6C4beHQDYcZhTtPLRgp0pr",  # Stronger, Together by Holly Brooks
)
EXCLUDED_SHOW = "30CG2yb1mBN9ahkaZUKT69"  # Left In The Attic


class SyncError(Exception):
    """An expected Spotify or configuration error."""


class Spotify:
    def __init__(self, refresh_token: str):
        if not refresh_token:
            raise SyncError("SPOTIFY_REFRESH_TOKEN is missing")
        self.refresh_token = refresh_token
        self.token = ""
        self.expires_at = 0.0

    def _read_json(self, request: Request):
        with urlopen(request, timeout=40) as response:
            payload = response.read()
            return json.loads(payload.decode("utf-8")) if payload else {}

    def access_token(self) -> str:
        if time.time() < self.expires_at:
            return self.token
        body = urlencode({
            "grant_type": "refresh_token",
            "refresh_token": self.refresh_token,
            "client_id": CLIENT_ID,
        }).encode()
        try:
            result = self._read_json(Request(TOKEN_URL, data=body, method="POST"))
        except HTTPError as exc:
            raise SyncError(f"Spotify token refresh failed (HTTP {exc.code}); reauthorization may be needed") from exc
        new_refresh = result.get("refresh_token")
        if new_refresh and new_refresh != self.refresh_token:
            # A GitHub secret cannot update itself. Stop instead of silently losing the new token.
            raise SyncError("Spotify rotated the refresh token; reauthorize and update the GitHub secret")
        self.token = result.get("access_token", "")
        if not self.token:
            raise SyncError("Spotify returned no access token")
        self.expires_at = time.time() + max(0, int(result.get("expires_in", 3600)) - 60)
        return self.token

    def request(self, method: str, path: str, *, params=None, data=None):
        url = API_ROOT + path
        if params:
            url += "?" + urlencode(params)
        body = None if data is None else json.dumps(data).encode("utf-8")
        for attempt in range(4):
            request = Request(url, data=body, method=method, headers={
                "Authorization": "Bearer " + self.access_token(),
                "Content-Type": "application/json",
            })
            try:
                return self._read_json(request)
            except HTTPError as exc:
                if exc.code == 429 and attempt < 3:
                    # Account quota exhaustion is different from a temporary rate limit.
                    try:
                        detail = json.loads(exc.read().decode("utf-8"))
                    except (ValueError, UnicodeDecodeError):
                        detail = {}
                    if detail.get("error", {}).get("reason") == "QUOTA_EXCEEDED":
                        raise SyncError("Spotify development quota exceeded; retry on a later run") from exc
                    wait = exc.headers.get("Retry-After", "3")
                    delay = int(wait) if wait.isdigit() else 3
                    if delay > 60:
                        raise SyncError("Spotify rate limited this run; retry on a later run") from exc
                    time.sleep(max(delay, 1))
                    continue
                if exc.code == 403:
                    raise SyncError(
                        f"Spotify denied {method} {path} (HTTP 403). Development-mode "
                        "apps require Premium for the app owner; also check app access and playlist permissions."
                    ) from exc
                raise SyncError(f"Spotify API returned HTTP {exc.code} for {method} {path}") from exc
        raise SyncError("Spotify rate-limit retries exhausted")

    def pages(self, path: str, **extra):
        offset = 0
        while True:
            page = self.request("GET", path, params={"limit": 50, "offset": offset, **extra})
            items = page.get("items")
            if not isinstance(items, list):
                raise SyncError(f"Spotify returned an invalid page for {path}")
            yield from items
            if not page.get("next"):
                return
            if not items:
                raise SyncError(f"Spotify returned an empty page with a next link for {path}")
            offset += len(items)


@dataclass
class Plan:
    add: list[str]
    remove: list[str]
    unknown: int
    known: int


def make_plan(episodes, playlist_items, excluded_uris) -> Plan:
    """Keep unrelated items; act only on explicit playback states or the excluded show."""
    existing = set()
    remove = set()
    for entry in playlist_items:
        if not isinstance(entry, dict):
            continue
        item = entry.get("item") or entry.get("track") or {}
        if not isinstance(item, dict):
            continue
        uri = item.get("uri")
        if not uri:
            continue
        existing.add(uri)
        show = item.get("show") or {}
        if uri in excluded_uris or (isinstance(show, dict) and show.get("id") == EXCLUDED_SHOW):
            remove.add(uri)

    add = []
    added = set()
    known = unknown = 0
    for episode in episodes:
        if not isinstance(episode, dict) or not episode.get("uri"):
            continue
        uri = episode["uri"]
        if uri in excluded_uris:
            continue
        point = episode.get("resume_point")
        if not isinstance(point, dict) or not isinstance(point.get("fully_played"), bool):
            unknown += 1
            continue
        known += 1
        if point["fully_played"]:
            if uri in existing:
                remove.add(uri)
        elif episode.get("is_playable") is not False and uri not in existing and uri not in added:
            add.append(uri)
            added.add(uri)
    return Plan(add=add, remove=sorted(remove), unknown=unknown, known=known)


def execute_plan(client: Spotify, plan: Plan, *, dry_run=False):
    print(f"Playback status known: {plan.known}; unknown: {plan.unknown}; "
          f"episodes to add: {len(plan.add)}; episodes to remove: {len(plan.remove)}")
    if plan.known == 0:
        raise SyncError("No playback statuses returned. Check the user-read-playback-position scope.")
    if dry_run:
        print("Preview only: playlist unchanged.")
        return
    path = f"/playlists/{PLAYLIST_ID}/items"
    for i in range(0, len(plan.remove), 100):
        client.request("DELETE", path, data={"items": [{"uri": uri} for uri in plan.remove[i:i + 100]]})
    for i in range(0, len(plan.add), 100):
        client.request("POST", path, data={"uris": plan.add[i:i + 100]})
    print("Playlist sync completed.")


def sync(client: Spotify, *, dry_run=False):
    # Read everything before making any changes; a failed fetch must never lead to a partial plan.
    current = list(client.pages(f"/playlists/{PLAYLIST_ID}/items", additional_types="track,episode"))
    excluded = {e.get("uri") for e in client.pages(f"/shows/{EXCLUDED_SHOW}/episodes") if isinstance(e, dict) and e.get("uri")}
    episodes = []
    for show_id in INCLUDED_SHOWS:
        episodes.extend(client.pages(f"/shows/{show_id}/episodes"))
    execute_plan(client, make_plan(episodes, current, excluded), dry_run=dry_run)


def main():
    parser = argparse.ArgumentParser(description="Sync unfinished episodes to the queen shit playlist")
    parser.add_argument("--dry-run", action="store_true", help="Show counts without changing the playlist")
    args = parser.parse_args()
    try:
        sync(Spotify(os.environ.get("SPOTIFY_REFRESH_TOKEN", "").strip()), dry_run=args.dry_run)
    except (SyncError, URLError, OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"Sync failed: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())

