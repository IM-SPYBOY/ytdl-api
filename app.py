from flask import Flask, request, jsonify, redirect
import innertube
import os
import tempfile
import re
import time
from urllib.parse import urlencode

app = Flask(__name__)

# --- Config ---
TEMP_DIR = tempfile.mkdtemp(prefix='yt_merge_')
os.makedirs(TEMP_DIR, exist_ok=True)
REQUEST_DELAY = 0.5  # reduced delay
INNER_CLIENT = None

# --- Init InnerTube client ---
def init_client():
    global INNER_CLIENT
    if INNER_CLIENT is None:
        try:
            INNER_CLIENT = innertube.InnerTube("WEB")
            app.logger.info("InnerTube client initialized successfully")
        except Exception as e:
            app.logger.error(f"Failed to init InnerTube: {e}")
    return INNER_CLIENT

# --- Helpers ---
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
        if '/' in mime:
            ext = mime.split('/')[1].split(';')[0]
    except Exception:
        pass

    filesize = f.get('contentLength') or f.get('content_length') or f.get('clen')
    filesize = safe_int(filesize)

    mime_lower = mime.lower()
    has_video = 'video' in mime_lower
    has_audio = 'audio' in mime_lower

    # Extract codec info more carefully
    vcodec = f.get('vcodec')
    acodec = f.get('acodec')
    
    if vcodec is None:
        vcodec = 'avc1.4d401e' if has_video else 'none'
    if acodec is None:
        acodec = 'mp4a.40.2' if has_audio else 'none'

    return {
        'itag': f.get('itag'),
        'url': f.get('url'),
        'mimeType': mime,
        'ext': ext,
        'qualityLabel': f.get('qualityLabel') or f.get('quality'),
        'height': safe_int(f.get('height')),
        'width': safe_int(f.get('width')),
        'fps': safe_int(f.get('fps')),
        'abr': safe_int(f.get('audioBitrate')) or safe_int(f.get('abr')),
        'vbr': safe_int(f.get('bitrate')) or safe_int(f.get('vbr')),
        'filesize': filesize,
        'vcodec': vcodec,
        'acodec': acodec,
        'has_video': has_video,
        'has_audio': has_audio,
    }

def get_yt_formats_and_meta(video_id: str):
    """
    Uses InnerTube to fetch player data and returns (title, [normalized_formats]).
    """
    client = init_client()
    if client is None:
        app.logger.error("InnerTube client is None")
        return None, None
    
    try:
        time.sleep(REQUEST_DELAY)
        app.logger.info(f"Fetching formats for video_id: {video_id}")
        player_data = client.player(video_id=video_id)
        app.logger.info(f"Player data received: keys = {list(player_data.keys())}")
    except Exception as e:
        app.logger.exception(f"InnerTube player error for {video_id}: {e}")
        return None, None

    title = None
    try:
        vd = player_data.get('videoDetails') or {}
        title = vd.get('title')
        app.logger.info(f"Title: {title}")
    except Exception as e:
        app.logger.error(f"Error extracting title: {e}")
        title = None

    streaming_data = player_data.get('streamingData') or {}
    app.logger.info(f"StreamingData keys: {list(streaming_data.keys())}")
    
    formats_raw = []
    for key in ('formats', 'adaptiveFormats'):
        key_formats = streaming_data.get(key) or []
        app.logger.info(f"Found {len(key_formats)} formats in '{key}'")
        formats_raw.extend(key_formats)

    app.logger.info(f"Total raw formats: {len(formats_raw)}")
    
    formats = []
    for i, f in enumerate(formats_raw):
        norm = normalize_format_entry(f)
        if not norm.get('url'):
            app.logger.warning(f"Format {i} has no URL, skipping")
            continue
        app.logger.info(f"Format {i}: itag={norm.get('itag')}, vcodec={norm.get('vcodec')}, acodec={norm.get('acodec')}, url_exists={bool(norm.get('url'))}")
        formats.append(norm)

    app.logger.info(f"Total normalized formats with URLs: {len(formats)}")
    return title, formats

# --- Routes ---

@app.route('/', methods=['GET', 'HEAD'])
def root():
    """
    If URL param is provided, handle it. Otherwise return status.
    """
    youtube_url = request.args.get('url') or request.args.get('u')
    
    if youtube_url:
        # Handle the request directly
        if not any(domain in youtube_url for domain in ('youtube.com', 'youtu.be')):
            return jsonify({'error': 'url does not look like a YouTube URL'}), 400

        video_id = extract_video_id(youtube_url)
        if not video_id:
            return jsonify({'error': 'could not extract video id from url'}), 400

        title, formats = get_yt_formats_and_meta(video_id)
        if formats is None:
            return jsonify({'error': 'failed to fetch formats from InnerTube', 'video_id': video_id}), 500

        muxed = []
        videos = []
        audios = []

        for f in formats:
            vcodec = f.get('vcodec') or 'none'
            acodec = f.get('acodec') or 'none'
            has_video = f.get('has_video', vcodec != 'none')
            has_audio = f.get('has_audio', acodec != 'none')

            entry = {
                'itag': f.get('itag'),
                'mimeType': f.get('mimeType'),
                'ext': f.get('ext'),
                'qualityLabel': f.get('qualityLabel'),
                'height': f.get('height'),
                'width': f.get('width'),
                'fps': f.get('fps'),
                'abr': f.get('abr'),
                'vbr': f.get('vbr'),
                'filesize': f.get('filesize'),
                'vcodec': vcodec,
                'acodec': acodec,
                'url': f.get('url'),
            }

            if has_video and has_audio:
                muxed.append(entry)
            elif has_video and not has_audio:
                videos.append(entry)
            elif has_audio and not has_video:
                audios.append(entry)

        def height_key(e):
            return (e.get('height') or 0, e.get('fps') or 0, e.get('filesize') or 0)

        muxed.sort(key=height_key, reverse=True)
        videos.sort(key=height_key, reverse=True)
        audios.sort(key=lambda e: (e.get('abr') or 0, e.get('filesize') or 0), reverse=True)

        return jsonify({
            'status': 'ok',
            'video_id': video_id,
            'title': title,
            'requested_url': youtube_url,
            'muxed_formats': muxed,
            'video_formats': videos,
            'audio_formats': audios,
            'total_formats': len(formats),
            'note': 'filesize may be null if not provided by source'
        }), 200
    
    # No URL provided, return health check
    return jsonify({"status": "ok", "service": "yt-formats-api", "version": "1.0"}), 200


@app.route('/online', methods=['GET'])
def online_formats():
    """
    GET /online?url=<YOUTUBE_URL>
    """
    youtube_url = request.args.get('url') or request.args.get('u')
    if not youtube_url:
        return jsonify({'error': 'missing "url" query parameter'}), 400

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
        has_video = f.get('has_video', vcodec != 'none')
        has_audio = f.get('has_audio', acodec != 'none')

        entry = {
            'itag': f.get('itag'),
            'mimeType': f.get('mimeType'),
            'ext': f.get('ext'),
            'qualityLabel': f.get('qualityLabel'),
            'height': f.get('height'),
            'width': f.get('width'),
            'fps': f.get('fps'),
            'abr': f.get('abr'),
            'vbr': f.get('vbr'),
            'filesize': f.get('filesize'),
            'vcodec': vcodec,
            'acodec': acodec,
            'url': f.get('url'),
        }

        if has_video and has_audio:
            muxed.append(entry)
        elif has_video and not has_audio:
            videos.append(entry)
        elif has_audio and not has_video:
            audios.append(entry)

    def height_key(e):
        return (e.get('height') or 0, e.get('fps') or 0, e.get('filesize') or 0)

    muxed.sort(key=height_key, reverse=True)
    videos.sort(key=height_key, reverse=True)
    audios.sort(key=lambda e: (e.get('abr') or 0, e.get('filesize') or 0), reverse=True)

    return jsonify({
        'status': 'ok',
        'video_id': video_id,
        'title': title,
        'requested_url': youtube_url,
        'muxed_formats': muxed,
        'video_formats': videos,
        'audio_formats': audios,
        'total_formats': len(formats),
        'note': 'filesize may be null if not provided by source'
    }), 200


@app.route('/webhook', methods=['GET', 'POST'])
def webhook():
    return jsonify({"status": "webhook-alive"}), 200


# --- Main for local dev ---
if __name__ == '__main__':
    init_client()
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port, debug=False)
