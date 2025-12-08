# YouTube Downloader API (InnerTube + Flask)

A minimal YouTube downloader API using the InnerTube WEB client. Supports muxed streaming and adaptive merging via ffmpeg.

## Endpoints

### POST /download
Returns available qualities with download URLs.
```json
{
  "url": "https://youtu.be/dQw4w9WgXcQ"
}
```

### GET /direct-download
Streams muxed (video+audio) formats with Range support.
```
/direct-download?url=...&quality=1080p
```

### GET /merge-download
Downloads adaptive video/audio, merges via ffmpeg, returns MP4.
```
/merge-download?url=...&quality=1080p
```

## Config
- `MAX_FILE_SIZE = 500MB`
- `REQUEST_DELAY = 1s`
- Supported qualities: `['720p', '1080p', '4k']`
- Temp files auto-clean after 5 minutes

## Run
```bash
python app.py
# or
gunicorn app:app
```

## Notes
- InnerTube reduces throttling + IP bans
- Add authentication + rate limiting for production

## License
MIT — use responsibly.
