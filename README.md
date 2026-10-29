# Tech & Life Pods — 8 podcast sync

This repository runs `Podcast Playlist Sync` automatically using GitHub Actions.
The workflow is in `.github/workflows/sync.yml` and runs at minute
11, 26, 41, and 56 of every hour (approximately every 15 minutes;
GitHub scheduled jobs can run late).

## How it works

- Adds unplayed and partially played episodes from all eight configured shows.
- Removes managed episodes Spotify reports as fully played.
- Detects and repairs duplicate managed episodes.
- Leaves unrelated playlist content unchanged.
- Scans all catalog pages, fails safely when playback state is unknown,
  and rereads the saved playlist to verify the result.
- Uses the repository's encrypted `SPOTIFY_REFRESH_TOKEN` secret and
  the Spotify app Client ID in `podcast_sync.py`. No secret is stored in code.

## How to deploy

Upload `podcast_sync.py`, `podcast_config.json`, and `README.md` to the ROOT of
`jibrilliban73/general-podcast-automation` on the `main` branch, replacing
existing files. Do not upload the enclosing ZIP as a file.

Under Actions > Podcast Playlist Sync, choose Run workflow. Check `dry_run`
for a preview, or UNCHECK it to do the live sync. The scheduled run is live.

## Configured shows

1. Office Drama
2. soju with sarah
3. Half Past Chai
4. Stronger, Together by Holly Brooks
5. Killer Instinct
6. Clock In with Emily Durham
7. Seamossgirlies
8. The Health Cafe with Vanessa Tiiu

Existing GitHub Actions workflow remains unchanged.
