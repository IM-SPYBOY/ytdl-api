# app.py - Python Flask API for YouTube Downloader using InnerTube API (No IP Bans)
# Deploy on Render: 
# 1. Create new Web Service > Python.
# 2. Upload this as app.py.
# 3. requirements.txt: flask==3.0.3 innertube==0.7.0 ffmpeg-python==0.2.0 requests==2.32.3
# 4. build.sh: apt-get update && apt-get install -y ffmpeg
# 5. runtime.txt: python-3.12.7
# 6. Start command: gunicorn app:app (add gunicorn to reqs)
# Test: POST /download {"url": "https://youtu.be/dQw4w9WgXcQ"}
# Notes: InnerTube API has high/no limits, mimics web client to avoid bans. Add rate limiting for production.

from flask import Flask, request, jsonify, send_file, abort, Response
import innertube
import os
import tempfile
import subprocess
import shutil
import requests
from urllib.parse import urlparse, parse_qs
import threading
import re
from datetime import datetime
import time

app = Flask(__name__)

# Config
TEMP_DIR = tempfile.mkdtemp(prefix='yt_merge_')
os.makedirs(TEMP_DIR, exist_ok=True)
MAX_FILE_SIZE = 500 * 1024 * 1024  # 500MB limit
REQUEST_DELAY = 1  # Delay between requests to avoid throttling

# Global client (reuse for efficiency)
client = None

def init_client():
    global client
    if client is None:
        client = innertube.InnerTube("WEB")
    return client

def extract_video_id(url):
    """Extract video ID from YouTube URL"""
    patterns = [
        r'(?:v=|\/)([0-9A-Za-z_-]{11})',
        r'(?:youtu\.be\/)([0-9A-Za-z_-]{11})'
    ]
    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            return match.group(1)
    return None

def get_yt_formats(video_id):
    """Extract formats using InnerTube API"""
    time.sleep(REQUEST_DELAY)  # Rate limit
    try:
        player_data = client.player(video_id=video_id)
        streaming_data = player_data.get('streamingData', {})
        if not streaming_data:
            return None
        
        # Combine muxed and adaptive formats
        formats = []
        for fmt_list in [streaming_data.get('formats', []), streaming_data.get('adaptiveFormats', [])]:
            for f in fmt_list:
                # Normalize keys to match common format
                norm_fmt = {
                    'itag': f.get('itag'),
                    'url': f.get('url'),
                    'mimeType': f.get('mimeType', ''),
                    'qualityLabel': f.get('qualityLabel'),
                    'height': f.get('height'),
                    'vcodec': 'none' if 'video' not in f.get('mimeType', '') else 'avc1',  # Simplified
                    'acodec': 'none' if 'audio' not in f.get('mimeType', '') else 'mp4a',
                    'filesize': f.get('contentLength'),
                    'ext': f.get('mimeType', '').split('/')[1].split(';')[0] if ';' in f.get('mimeType', '') else 'mp4',
                    'abr': f.get('audioBitrate'),
                    'fps': f.get('fps')
                }
                formats.append(norm_fmt)
        return formats
    except Exception as e:
        print(f"InnerTube error: {e}")
        return None

def is_muxed_format(fmt):
    """Check if format has both video and audio"""
    return fmt.get('vcodec') != 'none' and fmt.get('acodec') != 'none'

def find_best_formats(formats, quality='1080p'):
    """Find best muxed or adaptive pairs"""
    height = int(quality.replace('p', '')) if quality != '4k' else 2160
    muxed = [f for f in formats if is_muxed_format(f) and f.get('height') == height]
    if muxed:
        best_muxed = max(muxed, key=lambda f: f.get('filesize', 0) or 0)
        return {'type': 'muxed', 'url': best_muxed['url'], 'filesize': best_muxed.get('filesize'), 'ext': best_muxed.get('ext', 'mp4')}

    # Adaptive: Best video + best audio
    video_fmts = [f for f in formats if f.get('vcodec') != 'none' and f.get('height') == height and f.get('url')]
    if not video_fmts:
        return None
    best_video = max(video_fmts, key=lambda f: f.get('filesize', 0) or 0)
    audio_fmts = [f for f in formats if f.get('acodec') != 'none' and f.get('url')]
    best_audio = max(audio_fmts, key=lambda f: f.get('abr', 0)) if audio_fmts else None
    if not best_audio:
        return None
    return {'type': 'adaptive', 'video': {'url': best_video['url'], 'ext': best_video['ext']}, 'audio': {'url': best_audio['url'], 'ext': best_audio['ext']}, 'ext': 'mp4'}

@app.route('/download', methods=['POST'])
def download_info():
    data = request.json
    if not data or 'url' not in data:
        return jsonify({'error': 'Missing "url" in JSON body'}), 400

    youtube_url = data['url']
    if not ('youtube.com' in youtube_url or 'youtu.be' in youtube_url):
        return jsonify({'error': 'Invalid YouTube URL'}), 400

    video_id = extract_video_id(youtube_url)
    if not video_id:
        return jsonify({'error': 'Could not extract video ID'}), 400

    formats = get_yt_formats(video_id)
    if not formats:
        return jsonify({'error': 'Failed to extract video info via InnerTube'}), 500

    # Supported qualities
    qualities = ['720p', '1080p', '4k']  # Add more as needed
    options = []
    for q in qualities:
        fmt_info = find_best_formats(formats, q)
        if fmt_info:
            base_url = f'/direct-download' if fmt_info['type'] == 'muxed' else f'/merge-download'
            filesize = fmt_info.get('filesize') or 'Unknown'
            if fmt_info['type'] == 'adaptive':
                filesize = (fmt_info['video'].get('filesize', 0) or 0) + (fmt_info['audio'].get('filesize', 0) or 0)
            options.append({
                'quality': q,
                'format': 'mp4' if fmt_info['type'] == 'muxed' else 'mp4 (merged)',
                'url': f"{base_url}?url={youtube_url}&quality={q}",
                'filesize': filesize,
                'merged': fmt_info['type'] == 'adaptive'
            })

    if not options:
        return jsonify({'error': 'No suitable formats found'}), 404

    # Sort by quality
    options.sort(key=lambda x: int(x['quality'].replace('p', '').replace('k', '000')), reverse=True)

    return jsonify({'video_url': youtube_url, 'download_options': options})

@app.route('/direct-download', methods=['GET'])
def direct_download():
    """Proxy muxed format stream (no merge)"""
    url = request.args.get('url')
    quality = request.args.get('quality')
    if not url or not quality:
        abort(400)

    video_id = extract_video_id(url)
    formats = get_yt_formats(video_id)
    fmt_info = find_best_formats(formats, quality)
    if not fmt_info or fmt_info['type'] != 'muxed':
        abort(404)

    stream_url = fmt_info['url']
    if not stream_url:
        abort(404)

    # Proxy the stream (supports Range for resumable)
    req_headers = {k: v for k, v in request.headers if k.lower() not in ['host', 'content-length']}
    resp = requests.get(stream_url, headers=req_headers, stream=True, timeout=30)
    resp.raise_for_status()

    def generate():
        for chunk in resp.iter_content(chunk_size=8192):
            if chunk:
                yield chunk

    return Response(generate(),
                    content_type=resp.headers.get('content-type', 'video/mp4'),
                    status=resp.status_code,
                    headers=dict(resp.headers))

@app.route('/merge-download', methods=['GET'])
def merge_download():
    """Download video+audio streams, merge with ffmpeg, serve file"""
    url = request.args.get('url')
    quality = request.args.get('quality')
    if not url or not quality:
        abort(400)

    video_id = extract_video_id(url)
    formats = get_yt_formats(video_id)
    fmt_info = find_best_formats(formats, quality)
    if not fmt_info or fmt_info['type'] != 'adaptive':
        abort(404)

    video_url = fmt_info['video']['url']
    audio_url = fmt_info['audio']['url']

    # Temp files
    timestamp = datetime.now().timestamp()
    video_file = os.path.join(TEMP_DIR, f'video_{timestamp}.webm')
    audio_file = os.path.join(TEMP_DIR, f'audio_{timestamp}.m4a')
    merged_file = os.path.join(TEMP_DIR, f'merged_{quality}_{timestamp}.mp4')

    try:
        # Download video stream
        with requests.get(video_url, stream=True, timeout=60) as r:
            r.raise_for_status()
            with open(video_file, 'wb') as f:
                for chunk in r.iter_content(chunk_size=8192):
                    f.write(chunk)

        # Download audio stream
        with requests.get(audio_url, stream=True, timeout=60) as r:
            r.raise_for_status()
            with open(audio_file, 'wb') as f:
                for chunk in r.iter_content(chunk_size=8192):
                    f.write(chunk)

        # Merge with ffmpeg (fast copy video, re-encode audio if needed)
        cmd = [
            'ffmpeg', '-y',
            '-i', video_file,
            '-i', audio_file,
            '-c:v', 'copy',
            '-c:a', 'aac',
            '-movflags', '+faststart',
            merged_file
        ]
        result = subprocess.run(cmd, capture_output=True, check=True, timeout=300)
        if result.returncode != 0:
            raise RuntimeError(f"FFmpeg failed: {result.stderr.decode()}")

        # Check size
        if os.path.getsize(merged_file) > MAX_FILE_SIZE:
            raise RuntimeError("Merged file too large")

        # Auto-cleanup
        def cleanup():
            for f in [video_file, audio_file, merged_file]:
                if os.path.exists(f):
                    os.remove(f)
        threading.Timer(300, cleanup).start()  # 5min

        return send_file(merged_file, as_attachment=True, download_name=f"video_{quality}.mp4")

    except Exception as e:
        # Cleanup on error
        for f in [video_file, audio_file, merged_file]:
            if os.path.exists(f):
                os.remove(f)
        abort(500, description=str(e))

if __name__ == '__main__':
    init_client()
    app.run(debug=True, host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))
