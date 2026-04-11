---
name: youtube
description: >
  YouTube integration via jtube local service (port 2222).
  Use when user wants to search, download, or get info about YouTube videos.
---

# jtube (YouTube via nc)

Local service at `localhost:2222`. All commands: `echo "<command>" | nc localhost 2222`

## Video Commands

| Command | Description |
|---------|-------------|
| `<video_id>` | Best stream (video+audio) |
| `<video_id> --m3u8` | HLS stream URL (live streams) |
| `<video_id> --audio` | Audio only stream |
| `<video_id> --info` | Full metadata (title, views, likes, description, related) |
| `<video_id> --comments` | Get 20 comments |
| `<video_id> --comments=N` | Get N comments |
| `<video_id> --channel` | Channel info for this video |
| `<video_id> --playlists` | Channel playlists |
| `<video_id> --check` | Status: 0=available, 1=login-required, 2=unavailable, 3=upcoming |
| `<video_id> --chapters` | Video chapters/music marks (timestamp | title) |
| `<video_id> --subtitles-fetch` | Fetch subtitle text directly |

## Channel Commands

| Command | Description |
|---------|-------------|
| `UC<channel_id>` | Channel videos |
| `@<handle>` | Channel videos by handle |
| `UC<id>#mr=N` | Limit to N results |
| `UC<id>#md=N` | Videos from last N days |
| `LIVE_UC<id>` | Channel livestreams |
| `LIVE_UC<id>#mr=N` | Limit livestreams |
| `LIVE_UC<id>#md=N` | Livestreams from last N days |
| `RSS_UC<id>` | Channel videos in RSS format |
| `RSS@<handle>` | Channel videos in RSS format (handle) |

## Playlist Commands

| Command | Description |
|---------|-------------|
| `PL<playlist_id>` | Playlist videos |

## Search Commands

| Command | Description |
|---------|-------------|
| `yt_search_query:<terms>` | Search (24 results, use + for spaces) |
| `yt_search_query10:<terms>` | Search (10 results) |
| `yt_search_queryN:<terms>` | Search (N results) |

## Examples

# Refresh Command Reference

To update knowledge of jtube commands:
```bash
echo "help" | nc localhost 2222
```

## Examples

```bash
# Get video stream
echo "dQw4w9WgXcQ" | nc localhost 2222

# Get video info
echo "dQw4w9WgXcQ --info" | nc localhost 2222

# Get comments
echo "dQw4w9WgXcQ --comments=50" | nc localhost 2222

# Search
echo "yt_search_query:linux+tutorial" | nc localhost 2222

# Channel videos
echo "UCxxxxxxx" | nc localhost 2222
```
