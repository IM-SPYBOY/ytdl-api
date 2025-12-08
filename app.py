#!/usr/bin/env python3
"""
Flask YouTube Downloader API
A simple API to download YouTube videos and audio
"""

from flask import Flask, request, jsonify, send_file
from flask_cors import CORS
import yt_dlp
import os
import json
from datetime import datetime
import logging
from pathlib import Path

# Initialize Flask app
app = Flask(__name__)
CORS(app)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Configuration
DOWNLOAD_FOLDER = os.path.join(os.path.dirname(__file__), 'downloads')
TEMP_FOLDER = os.path.join(os.path.dirname(__file__), 'temp')
MAX_DOWNLOADS = 10

# Create necessary directories
Path(DOWNLOAD_FOLDER).mkdir(exist_ok=True)
Path(TEMP_FOLDER).mkdir(exist_ok=True)

# Track active downloads
active_downloads = {}


def get_video_info(url):
    """Extract video information without downloading"""
    try:
        ydl_opts = {
            'quiet': True,
            'no_warnings': True,
        }
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            return {
                'title': info.get('title', 'Unknown'),
                'duration': info.get('duration', 0),
                'uploader': info.get('uploader', 'Unknown'),
                'upload_date': info.get('upload_date', 'Unknown'),
                'view_count': info.get('view_count', 0),
                'thumbnail': info.get('thumbnail', ''),
                'formats': len(info.get('formats', [])),
                'description': info.get('description', '')[:200],
            }
    except Exception as e:
        logger.error(f"Error getting video info: {str(e)}")
        return None


@app.route('/', methods=['GET'])
def index():
    """API home endpoint"""
    return jsonify({
        'name': 'YouTube Downloader API',
        'version': '1.0.0',
        'endpoints': {
            'GET /': 'API information',
            'GET /info': 'Get video information (query: url)',
            'POST /download': 'Download video (json: url, format)',
            'GET /status/<download_id>': 'Check download status',
            'GET /health': 'Health check',
        }
    }), 200


@app.route('/health', methods=['GET'])
def health():
    """Health check endpoint"""
    return jsonify({
        'status': 'healthy',
        'timestamp': datetime.utcnow().isoformat(),
        'active_downloads': len(active_downloads)
    }), 200


@app.route('/info', methods=['GET'])
def info():
    """Get video information"""
    url = request.args.get('url')
    
    if not url:
        return jsonify({'error': 'URL parameter is required'}), 400
    
    # Validate URL
    if 'youtube' not in url.lower() and 'youtu.be' not in url.lower():
        return jsonify({'error': 'Invalid YouTube URL'}), 400
    
    try:
        video_info = get_video_info(url)
        if video_info:
            return jsonify({
                'success': True,
                'data': video_info
            }), 200
        else:
            return jsonify({'error': 'Could not retrieve video information'}), 400
    except Exception as e:
        logger.error(f"Error in /info endpoint: {str(e)}")
        return jsonify({'error': str(e)}), 500


@app.route('/download', methods=['POST'])
def download():
    """Download YouTube video or audio"""
    if len(active_downloads) >= MAX_DOWNLOADS:
        return jsonify({'error': 'Too many active downloads. Please try again later.'}), 429
    
    data = request.get_json()
    
    if not data or 'url' not in data:
        return jsonify({'error': 'URL is required'}), 400
    
    url = data.get('url')
    download_format = data.get('format', 'best')  # 'best', 'audio', 'video'
    
    # Validate URL
    if 'youtube' not in url.lower() and 'youtu.be' not in url.lower():
        return jsonify({'error': 'Invalid YouTube URL'}), 400
    
    try:
        download_id = f"download_{len(active_downloads)}_{int(datetime.utcnow().timestamp())}"
        active_downloads[download_id] = {
            'status': 'processing',
            'url': url,
            'format': download_format,
            'started_at': datetime.utcnow().isoformat()
        }
        
        # Configure download options
        ydl_opts = {
            'format': 'best' if download_format == 'best' else ('bestaudio' if download_format == 'audio' else 'best'),
            'outtmpl': os.path.join(DOWNLOAD_FOLDER, '%(title)s.%(ext)s'),
            'quiet': False,
            'no_warnings': False,
            'postprocessors': [],
        }
        
        # Add audio conversion if requested
        if download_format == 'audio':
            ydl_opts['postprocessors'] = [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '192',
            }]
        
        # Perform download
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            filename = ydl.prepare_filename(info)
        
        active_downloads[download_id]['status'] = 'completed'
        active_downloads[download_id]['filename'] = os.path.basename(filename)
        active_downloads[download_id]['completed_at'] = datetime.utcnow().isoformat()
        
        return jsonify({
            'success': True,
            'download_id': download_id,
            'message': 'Download completed successfully',
            'filename': os.path.basename(filename)
        }), 200
    
    except Exception as e:
        logger.error(f"Error during download: {str(e)}")
        active_downloads[download_id]['status'] = 'error'
        active_downloads[download_id]['error'] = str(e)
        return jsonify({'error': str(e)}), 500


@app.route('/status/<download_id>', methods=['GET'])
def status(download_id):
    """Check download status"""
    if download_id not in active_downloads:
        return jsonify({'error': 'Download ID not found'}), 404
    
    return jsonify({
        'download_id': download_id,
        'data': active_downloads[download_id]
    }), 200


@app.route('/downloads/<filename>', methods=['GET'])
def get_download(filename):
    """Download a file"""
    try:
        file_path = os.path.join(DOWNLOAD_FOLDER, filename)
        if not os.path.exists(file_path):
            return jsonify({'error': 'File not found'}), 404
        
        return send_file(file_path, as_attachment=True)
    except Exception as e:
        logger.error(f"Error downloading file: {str(e)}")
        return jsonify({'error': str(e)}), 500


@app.errorhandler(404)
def not_found(error):
    """Handle 404 errors"""
    return jsonify({'error': 'Endpoint not found'}), 404


@app.errorhandler(500)
def internal_error(error):
    """Handle 500 errors"""
    logger.error(f"Internal server error: {str(error)}")
    return jsonify({'error': 'Internal server error'}), 500


if __name__ == '__main__':
    # Run the Flask app
    app.run(
        host='0.0.0.0',
        port=int(os.environ.get('PORT', 5000)),
        debug=os.environ.get('FLASK_ENV') == 'development'
    )
