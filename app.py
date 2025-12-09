#!/usr/bin/env python3
"""
YouTube Downloader API (Minimal) — Full app.py

Provides:
 - GET  /online?url=<YOUTUBE_URL>
     -> returns JSON with:
        - muxed_formats: list of video+audio formats (direct urls + size)
        - video_formats: list of video-only formats (qualities + size)
        - audio_formats: list of audio-only formats (bitrates + size)
 - Existing helper functions included (InnerTube usage).
 - Runs on port 8080 by default.
"""

from flask import Flask, request, jsonify, abort
import innertube
import os
import tempfile
import re
import time

app = Flask(__name__)

# Config
TEMP_DIR = tempfile.mkdtemp(prefix='yt_merge_')
os.makedirs(TEMP_DIR, exist_ok=True)
REQUEST_DELAY = 1.0  # seconds between InnerTube calls to be gentle
INNER_CLIENT = None

def init_client():
    global INNER_CLIENT
    if INNER_CLIENT is None:
        INNER_CLIENT = innertube.InnerTube("WEB")
    return INNER_CLIENT

# Helpers
VIDEO_ID_PATTERNS = [
    r'(?:v=|\/)([0-9A-Za-z_-]{11})',
    r'youtu\.be\/([0-9A-Za-z_-]{11})'
]

def extract_video_id(url: str):
    if not url:
        return None
    for p in VIDEO_ID_PATTERNS:
        m = re.search(p, url)
        if m:
            return m.group(1)
    return None

def safe_int(v):
    try:
        if v is None:
            return None
        if isinstance(v, int):
            return v
        return int(v)
    except Exception:
        try:
            return int(float(v))
        except Exception:
            return None

def normalize_format_entry(f):
    """
    Normalize an InnerTube format entry into a predictable dict.
    """
    mime = f.get('mimeType', '') or ''
    ext = 'mp4'
    try:
        # mimeType can be like "video/webm; codecs=..."
        ext = mime.split('/')[1].split(';')[0] if '/' in mime else ext
    except Exception:
        ext = ext

    # contentLength sometimes present; sometimes not
    filesize = f.get('contentLength') or f.get('content_length') or f.get('clen') or None
    filesize = safe_int(filesize)

    # codec detection: simplified
    mime_lower = mime.lower()
    has_video = 'video' in mime_lower
    has_audio = 'audio' in mime_lower

    return {
        'itag': f.get('itag'),
        'url': f.get('url'),
        'mimeType': mime,
        'ext': ext,
        'qualityLabel': f.get('qualityLabel') or f.get('quality') or None,
        'height': safe_int(f.get('height')),
        'fps': safe_int(f.get('fps')),
        'abr': safe_int(f.get('audioBitrate')) or safe_int(f.get('abr')) or None,
        'filesize': filesize,
        'vcodec': f.get('vcodec') if f.get('vcodec') is not None else ('avc1' if has_video else 'none'),
        'acodec': f.get('acodec') if f.get('acodec') is not None else ('mp4a' if has_audio else 'none'),
    }

def get_yt_formats_and_meta(video_id: str):
    """
    Uses InnerTube to fetch player data and returns (title, list_of_normalized_formats).
    """
    client = init_client()
    time.sleep(REQUEST_DELAY)
    try:
        player_data = client.player(video_id=video_id)
    except Exception as e:
        app.logger.exception("InnerTube player error")
        return None, None

    # Extract title if available
    title = None
    try:
        vd = player_data.get('videoDetails') or player_data.get('microformat') or {}
        title = vd.get('title') or (player_data.get('microformat', {}) or {}).get('title', {}).get('simpleText')
    except Exception:
        title = None

    streaming_data = player_data.get('streamingData') or {}
    formats_raw = []
    for key in ('formats', 'adaptiveFormats'):
        for f in streaming_data.get(key, []) or []:
            formats_raw.append(f)

    # Normalize
    formats = []
    for f in formats_raw:
        norm = normalize_format_entry(f)
        # If url is missing, skip
        if not norm.get('url'):
            continue
        formats.append(norm)

    return title, formats

@app.route('/online', methods=['GET'])
def online_formats():
    """
    GET /online?url=<YOUTUBE_URL>&include_muxed=true

    Returns JSON listing:
    - muxed_formats: video+audio
    - video_formats: video-only (with quality)
    - audio_formats: audio-only (with abr)
    Each entry contains: itag, mimeType, ext, qualityLabel/height/fps, filesize (int bytes or null), url
    """
    youtube_url = request.args.get('url') or request.args.get('u')
    if not youtube_url:
        return jsonify({'error': 'missing "url" query parameter'}), 400

    # Basic validation for youtube domain
    if not any(domain in youtube_url for domain in ('youtube.com', 'youtu.be')):
        return jsonify({'error': 'url does not look like a YouTube URL'}), 400

    video_id = extract_video_id(youtube_url)
    if not video_id:
        return jsonify({'error': 'could not extract video id from url'}), 400

    title, formats = get_yt_formats_and_meta(video_id)
    if formats is None:
        return jsonify({'error': 'failed to fetch formats from InnerTube'}), 500

    muxed = []
    videos = []
    audios = []

    for f in formats:
        vcodec = f.get('vcodec') or 'none'
        acodec = f.get('acodec') or 'none'
        entry = {
            'itag': f.get('itag'),
            'mimeType': f.get('mimeType'),
            'ext': f.get('ext'),
            'qualityLabel': f.get('qualityLabel'),
            'height': f.get('height'),
            'fps': f.get('fps'),
            'abr': f.get('abr'),
            'filesize': f.get('filesize'),
            'url': f.get('url')
        }

        if (vcodec != 'none') and (acodec != 'none'):
            muxed.append(entry)
        elif (vcodec != 'none') and (acodec == 'none'):
            videos.append(entry)
        elif (acodec != 'none') and (vcodec == 'none'):
            audios.append(entry)
        else:
            # Unknown/skip
            continue

    # Sorting: prefer higher quality first for videos/muxed, higher abr for audios
    def height_key(e): return (e['height'] or 0, e.get('fps') or 0, e.get('filesize') or 0)
    muxed.sort(key=height_key, reverse=True)
    videos.sort(key=height_key, reverse=True)
    audios.sort(key=lambda e: (e.get('abr') or 0, e.get('filesize') or 0), reverse=True)

    response = {
        'status': 'ok',
        'video_id': video_id,
        'title': title,
        'requested_url': youtube_url,
        'muxed_formats': muxed,
        'video_formats': videos,
        'audio_formats': audios,
        'note': 'filesize may be null if not provided by source'
    }

    return jsonify(response)

if __name__ == '__main__':
    # Initialize InnerTube client before serving
    init_client()
    # Run on port 8080 as requested
    app.run(host='0.0.0.0', port=8080, debug=False)
