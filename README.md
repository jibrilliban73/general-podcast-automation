# Tech and life pods sync

This repository has its own independent GitHub Actions workflow at `.github/workflows/sync.yml`, scheduled every 15 minutes. It uses this repository's own encrypted `SPOTIFY_REFRESH_TOKEN` and the dedicated Spotify client ID `863d034412554af6be0f88f51becfe89`. It does not call another playlist repository.

## What the workflow checks

Every run reads the full catalog of every configured show and every playlist page. It adds playable unplayed and in-progress episodes once, repairs managed duplicates, removes finished managed episodes, and preserves unrelated entries. Unknown playback status, incomplete pagination, expired credentials, failed additions, and failed verification make the run fail visibly.

A live sync rereads the saved playlist; a separate second step rescans all catalogs and audits the saved playlist without editing it. Both must pass before the workflow succeeds. Unit tests are code checks and do not establish that the live Spotify connection works.

## Authorization and running

The required `SPOTIFY_REFRESH_TOKEN` must be authorized for client ID `863d034412554af6be0f88f51becfe89`, with `playlist-read-private playlist-read-collaborative playlist-modify-private playlist-modify-public user-read-playback-position`. A public client ID alone is insufficient. Store the refresh token only as this repository's encrypted Actions secret, never in source code or chat.

Open this repository's Actions tab and select **Tech and life pods sync**. Use **Run workflow** with **dry_run** checked for a preview; uncheck it for a live sync. Use **verify_only** for a read-only full audit. Scheduled runs perform a live sync and independent audit.

## Email on pass or fail

In GitHub notification settings, enable **Actions → Email** and leave **Only notify for failed workflows** unchecked. Each repository produces its own workflow completion notification. The scheduled workflow's actor receives these notifications. Email delivery must be checked in the mailbox; a GitHub success status alone does not prove email arrival.

GitHub schedules may be delayed. Premium and Spotify authorization must remain valid. Renew expired or revoked authorization when a run reports it.

## Configured playlist and shows

```json
{
  "name": "Tech and life pods",
  "playlist_id": "0Hu69WnnxAgPP59X46XMQs",
  "shows": {
    "0sJAtVorz8TsYDzzyM04cq": "Office Drama",
    "2GWSGMFIZ0xiisnboVE2HS": "soju with sarah",
    "6j2yaoEEkEwM4uctt0tYSe": "Half Past Chai",
    "6C4beHQDYcZhTtPLRgp0pr": "Stronger, Together by Holly Brooks"
  },
  "excluded_shows": [
    "30CG2yb1mBN9ahkaZUKT69"
  ]
}
```

## Local validation

Run `python -m unittest -v`. Tests cover pagination, incomplete reads, duplicate repair, preservation of unrelated entries, missing additions, and idempotent reruns.
