# Podcast playlist automation

The [queen shit playlist](https://open.spotify.com/playlist/0Hu69WnnxAgPP59X46XMQs) is synced with these four Spotify shows:

- [Office Drama](https://open.spotify.com/show/0sJAtVorz8TsYDzzyM04cq)
- [soju with sarah](https://open.spotify.com/show/2GWSGMFIZ0xiisnboVE2HS)
- [Half Past Chai](https://open.spotify.com/show/6j2yaoEEkEwM4uctt0tYSe)
- [Stronger, Together by Holly Brooks](https://open.spotify.com/show/6C4beHQDYcZhTtPLRgp0pr)

Episodes Spotify marks unplayed or in progress are added. Episodes marked finished are removed. [Left In The Attic](https://open.spotify.com/show/30CG2yb1mBN9ahkaZUKT69) is excluded, and its episodes already in the playlist are removed. Other playlist items are left alone. Missing playback status is treated as unknown and is never guessed. The script reads all pages before changing the playlist, avoids duplicates, and batches writes.

## Running automatically

The scheduled workflow is stored in the existing `jibrilliban73/WTJplaylistsync` repository so it can use that repository's existing `SPOTIFY_REFRESH_TOKEN` secret without copying or exposing the token. The workflow checks out this repository and runs `podcast_sync.py` approximately every 15 minutes; GitHub may delay scheduled runs. The WTJ workflow remains independent.

Spotify's development-mode apps require the app owner's Spotify account to have Premium. A 403 means Spotify rejected the sync, so an Actions schedule alone does not guarantee the playlist was updated. The developer app also needs the `user-read-playback-position`, `playlist-read-private`, `playlist-modify-private`, and `playlist-modify-public` permissions. Check the workflow's Actions log for the actual result.

Spotify refresh tokens can expire after 180 days or rotate. Reauthorization and updating the existing GitHub secret may then be necessary. GitHub can disable scheduled workflows in public repositories after 60 days without repository activity. The schedule depends on the WTJ repository and its secret remaining available.

## Preview and tests

Use **Run workflow** in GitHub Actions with `dry_run` enabled to preview the change counts. The normal schedule applies changes. No computer needs to remain running. Never put tokens in source code or share them in chat.

The local test suite needs only Python 3.10 or later:

```sh
python -m unittest -v
```
