# Podcast playlist automation

The [Tech and Life pods](https://open.spotify.com/playlist/0Hu69WnnxAgPP59X46XMQs) contains eligible episodes from these four shows:

- [Office Drama](https://open.spotify.com/show/0sJAtVorz8TsYDzzyM04cq)
- [soju with sarah](https://open.spotify.com/show/2GWSGMFIZ0xiisnboVE2HS)
- [Half Past Chai](https://open.spotify.com/show/6j2yaoEEkEwM4uctt0tYSe)
- [Stronger, Together by Holly Brooks](https://open.spotify.com/show/6C4beHQDYcZhTtPLRgp0pr)

The initial playlist was populated on October 27, 2026. 

## Current status

**The scheduled sync is not connected to Spotify yet.** This repository has a 15-minute GitHub Actions schedule, but it skips playlist changes until the `SPOTIFY_REFRESH_TOKEN` Actions secret is configured in this repository. A workflow that ran without this secret has not updated the playlist.

The Spotify developer app also requires the app owner's account to have Premium. Its authorization must include `user-read-playback-position`, `playlist-read-private`, `playlist-modify-private`, and `playlist-modify-public`. A Spotify 403 means the sync has not succeeded; check the Actions log. Scheduled jobs may be delayed.

Once authorized, the sync adds episodes Spotify marks unplayed or in progress, removes episodes marked finished, and removes episodes from the excluded show. Other playlist items are preserved. Unknown playback status is skipped; the script reads all pages before making changes, avoids duplicates, and batches writes.

Spotify refresh tokens can expire after 180 days or rotate, requiring reauthorization and an updated GitHub secret. GitHub may disable scheduled workflows in a public repository after 60 days without repository activity. Never commit tokens or share them in chat.

## Preview and tests

After authorization, use **Run workflow** in GitHub Actions with `dry_run` enabled to preview changes. The schedule applies them. The computer does not need to stay on.

The test suite needs Python 3.10 or later:

```sh
python -m unittest -v
```
