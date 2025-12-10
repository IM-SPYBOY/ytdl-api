from flask import Flask, request, jsonify
import innertube
import os
import re
import time
import json

app = Flask(__name__)

REQUEST_DELAY = 0.5
INNER_CLIENT = None

def init_client():
    global INNER_CLIENT
    if INNER_CLIENT is None:
        try:
            INNER_CLIENT = innertube.InnerTube("WEB")
            app.logger.info("InnerTube WEB client initialized")
        except Exception as e:
            app.logger.error(f"Failed to init InnerTube: {e}")
            try:
                INNER_CLIENT = innertube.InnerTube("ANDROID")
                app.logger.info("InnerTube ANDROID client initialized (fallback)")
            except Exception as e2:
                app.logger.error(f"Failed to init ANDROID client: {e2}")
                INNER_CLIENT = None
    return INNER_CLIENT

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
    client = init_client()
    if client is None:
        app.logger.error("InnerTube client initialization failed")
        return None, None, None
    
    try:
        time.sleep(REQUEST_DELAY)
        app.logger.info(f"Fetching player data for video_id: {video_id}")
        player_data = client.player(video_id=video_id)
        app.logger.info(f"Player response keys: {list(player_data.keys())}")
        
    except Exception as e:
        app.logger.exception(f"InnerTube player error: {e}")
        return None, None, None

    title = None
    try:
        vd = player_data.get('videoDetails') or {}
        title = vd.get('title')
        app.logger.info(f"Video title: {title}")
    except Exception as e:
        app.logger.error(f"Error extracting title: {e}")

    streaming_data = player_data.get('streamingData') or {}
    app.logger.info(f"StreamingData keys: {list(streaming_data.keys())}")
    
    formats_raw = []
    for key in ('formats', 'adaptiveFormats'):
        key_formats = streaming_data.get(key) or []
        app.logger.info(f"Found {len(key_formats)} in '{key}'")
        formats_raw.extend(key_formats)

    app.logger.info(f"Total raw formats collected: {len(formats_raw)}")

    if not formats_raw:
        app.logger.warning("No formats found in response")
        app.logger.warning(f"Raw streamingData: {json.dumps(streaming_data, indent=2)[:500]}")

    formats = []
    for i, f in enumerate(formats_raw):
        norm = normalize_format_entry(f)
        
        if not norm.get('url'):
            app.logger.debug(f"Format {i}: Skipped (no URL)")
            continue
        
        app.logger.info(f"Format {i}: itag={norm.get('itag')}, ext={norm.get('ext')}, "
                       f"has_video={norm.get('has_video')}, has_audio={norm.get('has_audio')}")
        formats.append(norm)

    app.logger.info(f"Total normalized formats with URLs: {len(formats)}")
    return title, video_id, formats

@app.route('/', methods=['GET', 'HEAD'])
def root():
    youtube_url = request.args.get('url') or request.args.get('u')
    
    if not youtube_url:
        return jsonify({"status": "ok", "service": "yt-formats-api", "version": "1.0"}), 200
    
    if not any(domain in youtube_url for domain in ('youtube.com', 'youtu.be')):
        return jsonify({'error': 'url does not look like a YouTube URL'}), 400

    video_id = extract_video_id(youtube_url)
    if not video_id:
        return jsonify({'error': 'could not extract video id from url'}), 400

    title, vid_id, formats = get_yt_formats_and_meta(video_id)
    
    if formats is None:
        return jsonify({
            'error': 'failed to fetch formats from InnerTube',
            'video_id': video_id,
            'url': youtube_url
        }), 500

    if not formats:
        return jsonify({
            'error': 'no formats found for this video',
            'video_id': video_id,
            'title': title,
            'url': youtube_url
        }), 404

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


@app.route('/online', methods=['GET'])
def online_formats():
    youtube_url = request.args.get('url') or request.args.get('u')
    
    if not youtube_url:
        return jsonify({'error': 'missing "url" query parameter'}), 400

    if not any(domain in youtube_url for domain in ('youtube.com', 'youtu.be')):
        return jsonify({'error': 'url does not look like a YouTube URL'}), 400

    video_id = extract_video_id(youtube_url)
    if not video_id:
        return jsonify({'error': 'could not extract video id from url'}), 400

    title, vid_id, formats = get_yt_formats_and_meta(video_id)
    
    if formats is None:
        return jsonify({
            'error': 'failed to fetch formats from InnerTube',
            'video_id': video_id,
        }), 500

    if not formats:
        return jsonify({
            'error': 'no formats found for this video',
            'video_id': video_id,
            'title': title,
        }), 404

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
    init_client()
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port, debug=False)
