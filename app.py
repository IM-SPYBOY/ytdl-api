from flask import Flask, request, jsonify
import innertube
import os
import re
import time
import json

app = Flask(__name__)
REQUEST_DELAY = 0.5

# List of client names to try, in order of preference
CLIENT_FALLBACK_ORDER = [
    "WEB",
    "ANDROID",
    "IOS",
    "WEB_EMBEDDED",
    "ANDROID_EMBED",
    "TV_EMBEDDED",
    "MEDIA_CONNECT",  # sometimes useful for restricted content
]

INNER_CLIENTS = {}  # cache initialized clients: name -> InnerTube instance

def get_client(client_name: str):
    """Initialize and cache a specific InnerTube client."""
    if client_name in INNER_CLIENTS:
        return INNER_CLIENTS[client_name]
    
    try:
        client = innertube.InnerTube(client_name)
        app.logger.info(f"InnerTube client '{client_name}' initialized successfully")
        INNER_CLIENTS[client_name] = client
        return client
    except Exception as e:
        app.logger.warning(f"Failed to initialize InnerTube client '{client_name}': {e}")
        INNER_CLIENTS[client_name] = None
        return None

def get_working_client():
    """Return the first working client from the fallback list."""
    for name in CLIENT_FALLBACK_ORDER:
        client = get_client(name)
        if client is not None:
            return client
    return None

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
    mime = f.get('mimeType', '') or ''
    ext = 'mp4'
    try:
        if '/' in mime:
            ext = mime.split('/')[1].split(';')[0]
    except Exception:
        pass
    filesize = f.get('contentLength') or f.get('content_length')
    filesize = safe_int(filesize)
    mime_lower = mime.lower()
    has_video = 'video' in mime_lower
    has_audio = 'audio' in mime_lower
    vcodec = f.get('vcodec')
    acodec = f.get('acodec')
   
    if not vcodec and has_video:
        try:
            if 'codecs=' in mime:
                codecs_str = mime.split('codecs=')[1].strip('"\'')
                vcodec = codecs_str.split(',')[0] if ',' in codecs_str else codecs_str
        except Exception:
            vcodec = 'avc1'
   
    if not acodec and has_audio:
        try:
            if 'codecs=' in mime:
                codecs_str = mime.split('codecs=')[1].strip('"\'')
                parts = codecs_str.split(',')
                acodec = parts[-1] if len(parts) > 1 else parts[0]
        except Exception:
            acodec = 'mp4a'
    return {
        'itag': f.get('itag'),
        'url': f.get('url'),
        'mimeType': mime,
        'ext': ext,
        'qualityLabel': f.get('qualityLabel') or f.get('quality_label'),
        'height': safe_int(f.get('height')),
        'width': safe_int(f.get('width')),
        'fps': safe_int(f.get('fps')),
        'abr': safe_int(f.get('audioBitrate') or f.get('audio_bitrate')),
        'vbr': safe_int(f.get('bitrate') or f.get('video_bitrate')),
        'filesize': filesize,
        'vcodec': vcodec or ('avc1' if has_video else 'none'),
        'acodec': acodec or ('mp4a' if has_audio else 'none'),
        'has_video': has_video,
        'has_audio': has_audio,
    }

def get_yt_formats_and_meta(video_id: str):
    title = None
    playability_reason = None
    playability_status = None

    for client_name in CLIENT_FALLBACK_ORDER:
        client = get_client(client_name)
        if client is None:
            continue

        try:
            time.sleep(REQUEST_DELAY)
            app.logger.info(f"Fetching player data for video_id: {video_id} using client '{client_name}'")
            player_data = client.player(video_id=video_id)
        except Exception as e:
            app.logger.exception(f"InnerTube player error with client '{client_name}': {e}")
            continue

        # Extract playability status
        playability = player_data.get('playabilityStatus', {})
        status = playability.get('status')
        reason = playability.get('reason')
        if status != 'OK':
            app.logger.warning(f"Playability error with client '{client_name}': {status} - {reason}")
            playability_status = status
            playability_reason = reason or "Unknown restriction"
            # Continue trying other clients even if not OK – some clients may succeed
            continue

        # Extract title
        try:
            vd = player_data.get('videoDetails') or {}
            title = vd.get('title')
            if title:
                app.logger.info(f"Video title extracted with client '{client_name}': {title}")
        except Exception as e:
            app.logger.error(f"Error extracting title with client '{client_name}': {e}")

        # Extract streaming data
        streaming_data = player_data.get('streamingData') or {}
        formats_raw = []
        for key in ('formats', 'adaptiveFormats'):
            key_formats = streaming_data.get(key) or []
            app.logger.info(f"Client '{client_name}': Found {len(key_formats)} formats in '{key}'")
            formats_raw.extend(key_formats)

        if not formats_raw:
            app.logger.warning(f"No formats found with client '{client_name}'")
            continue  # try next client

        # Normalize formats
        formats = []
        for i, f in enumerate(formats_raw):
            norm = normalize_format_entry(f)
            if not norm.get('url'):
                app.logger.debug(f"Format {i} skipped (no URL) with client '{client_name}'")
                continue
            formats.append(norm)

        if formats:
            app.logger.info(f"Successfully retrieved {len(formats)} formats with client '{client_name}'")
            return title, video_id, formats, None, None

    # If we reach here, no client succeeded
    return title, video_id, [], playability_status, playability_reason or "No client could retrieve formats (possibly age-restricted, private, or unavailable)"

@app.route('/', methods=['GET', 'HEAD'])
@app.route('/online', methods=['GET'])  # unified endpoint
def formats_endpoint():
    youtube_url = request.args.get('url') or request.args.get('u')
   
    if not youtube_url:
        return jsonify({"status": "ok", "service": "yt-formats-api", "version": "1.1", "note": "Improved client fallback and error reporting"}), 200
   
    if not any(domain in youtube_url for domain in ('youtube.com', 'youtu.be')):
        return jsonify({'error': 'url does not look like a YouTube URL'}), 400

    video_id = extract_video_id(youtube_url)
    if not video_id:
        return jsonify({'error': 'could not extract video id from url'}), 400

    title, vid_id, formats, play_status, play_reason = get_yt_formats_and_meta(video_id)
   
    if formats is None:  # should not happen now
        return jsonify({
            'error': 'failed to fetch formats from InnerTube',
            'video_id': video_id,
            'requested_url': youtube_url
        }), 500

    if not formats:
        response = {
            'error': 'no formats found for this video',
            'video_id': vid_id,
            'title': title,
            'requested_url': youtube_url,
            'playability_status': play_status,
            'playability_reason': play_reason,
            'note': 'This is commonly caused by age-restriction, privacy settings, or regional blocks. Some clients cannot bypass these without authentication.'
        }
        return jsonify(response), 404

    # Categorize and sort formats
    muxed = []
    videos = []
    audios = []
    for f in formats:
        has_video = f.get('has_video', False)
        has_audio = f.get('has_audio', False)
        entry = {
            'itag': f.get('itag'),
            'ext': f.get('ext'),
            'mimeType': f.get('mimeType'),
            'qualityLabel': f.get('qualityLabel'),
            'height': f.get('height'),
            'width': f.get('width'),
            'fps': f.get('fps'),
            'vcodec': f.get('vcodec'),
            'acodec': f.get('acodec'),
            'abr': f.get('abr'),
            'vbr': f.get('vbr'),
            'filesize': f.get('filesize'),
            'url': f.get('url'),
        }
        if has_video and has_audio:
            muxed.append(entry)
        elif has_video:
            videos.append(entry)
        elif has_audio:
            audios.append(entry)

    muxed.sort(key=lambda e: (e.get('height') or 0, e.get('fps') or 0, e.get('filesize') or 0), reverse=True)
    videos.sort(key=lambda e: (e.get('height') or 0, e.get('fps') or 0, e.get('filesize') or 0), reverse=True)
    audios.sort(key=lambda e: (e.get('abr') or 0, e.get('filesize') or 0), reverse=True)

    return jsonify({
        'status': 'ok',
        'video_id': vid_id,
        'title': title,
        'requested_url': youtube_url,
        'muxed_formats': muxed,
        'video_formats': videos,
        'audio_formats': audios,
        'total_formats': len(formats),
    }), 200

@app.route('/webhook', methods=['GET', 'POST'])
def webhook():
    return jsonify({"status": "webhook-alive"}), 200

if __name__ == '__main__':
    # Pre-initialize common clients
    for name in CLIENT_FALLBACK_ORDER:
        get_client(name)
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port, debug=False)
