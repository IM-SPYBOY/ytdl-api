# YTDL API - YouTube Downloader API

A powerful and flexible REST API for downloading YouTube videos, playlists, and audio. Built with modern best practices, this API provides an easy-to-use interface for video and audio extraction from YouTube.

## Features

- 🎬 **Download Videos** - Extract high-quality videos from YouTube links
- 🎵 **Audio Extraction** - Convert videos to audio format (MP3, M4A, etc.)
- 📺 **Playlist Support** - Download entire playlists with a single request
- ⚡ **Fast Processing** - Optimized for quick downloads and conversions
- 🔒 **Secure** - Built with security best practices in mind
- 📊 **Format Selection** - Choose from multiple video and audio formats
- 🌐 **RESTful API** - Simple HTTP endpoints for easy integration
- 📝 **Comprehensive Logging** - Track all download activities
- ⚙️ **Flexible Configuration** - Customize behavior to your needs
- 🔄 **Queue Management** - Handle multiple downloads efficiently

## Table of Contents

- [Installation](#installation)
- [Quick Start](#quick-start)
- [API Endpoints](#api-endpoints)
- [Configuration](#configuration)
- [Examples](#examples)
- [Error Handling](#error-handling)
- [Rate Limiting](#rate-limiting)
- [Troubleshooting](#troubleshooting)
- [Contributing](#contributing)
- [License](#license)

## Installation

### Prerequisites

- Node.js (v14.0 or higher)
- npm or yarn package manager
- Python 3.7+ (for yt-dlp backend)

### Setup

1. Clone the repository:
```bash
git clone https://github.com/IM-SPYBOY/ytdl-api.git
cd ytdl-api
```

2. Install dependencies:
```bash
npm install
```

3. Install Python dependencies:
```bash
pip install yt-dlp
```

4. Create a `.env` file in the root directory:
```bash
cp .env.example .env
```

5. Configure your environment variables (see [Configuration](#configuration) section)

6. Start the server:
```bash
npm start
```

The API will be available at `http://localhost:3000` by default.

## Quick Start

### Basic Video Download

```bash
curl -X POST http://localhost:3000/api/download \
  -H "Content-Type: application/json" \
  -d '{
    "url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
    "format": "best"
  }'
```

### Download Audio Only

```bash
curl -X POST http://localhost:3000/api/download \
  -H "Content-Type: application/json" \
  -d '{
    "url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
    "format": "audio",
    "audioFormat": "mp3"
  }'
```

## API Endpoints

### POST /api/download

Download a single video or audio file from YouTube.

**Request Body:**
```json
{
  "url": "string (required)",
  "format": "string (optional, default: 'best')",
  "audioFormat": "string (optional, default: 'mp3')",
  "quality": "string (optional, default: 'best')",
  "outputPath": "string (optional)"
}
```

**Parameters:**
- `url` - YouTube video URL
- `format` - Download format: `best`, `video`, `audio`
- `audioFormat` - Audio format: `mp3`, `m4a`, `wav`, `opus`, `vorbis`
- `quality` - Video quality: `best`, `worst`, `720p`, `480p`, `360p`, `240p`
- `outputPath` - Custom output directory path

**Response:**
```json
{
  "success": true,
  "data": {
    "videoId": "dQw4w9WgXcQ",
    "title": "Video Title",
    "duration": 213,
    "fileSize": 45678900,
    "filePath": "/downloads/video_title.mp4",
    "downloadTime": 25,
    "format": "best"
  }
}
```

### POST /api/playlist

Download an entire YouTube playlist.

**Request Body:**
```json
{
  "playlistUrl": "string (required)",
  "format": "string (optional, default: 'best')",
  "maxVideos": "number (optional, default: unlimited)"
}
```

**Parameters:**
- `playlistUrl` - YouTube playlist URL
- `format` - Download format: `best`, `video`, `audio`
- `maxVideos` - Maximum number of videos to download

**Response:**
```json
{
  "success": true,
  "data": {
    "playlistTitle": "Playlist Name",
    "totalVideos": 50,
    "downloadedVideos": 50,
    "failedVideos": 0,
    "totalDuration": 12600,
    "totalFileSize": 2500000000,
    "downloadTime": 3600
  }
}
```

### GET /api/status/:jobId

Check the status of an ongoing download.

**Response:**
```json
{
  "success": true,
  "data": {
    "jobId": "job_123456",
    "status": "downloading",
    "progress": 65,
    "currentVideo": "Video Title",
    "videoNumber": 15,
    "totalVideos": 50
  }
}
```

### GET /api/formats/:videoId

Get available download formats for a video.

**Response:**
```json
{
  "success": true,
  "data": {
    "videoId": "dQw4w9WgXcQ",
    "title": "Video Title",
    "duration": 213,
    "formats": [
      {
        "formatId": "18",
        "extension": "mp4",
        "resolution": "360p",
        "fps": 30,
        "videoCodec": "h264",
        "audioCodec": "aac",
        "fileSize": 45678900
      },
      {
        "formatId": "22",
        "extension": "mp4",
        "resolution": "720p",
        "fps": 30,
        "videoCodec": "h264",
        "audioCodec": "aac",
        "fileSize": 89345600
      }
    ]
  }
}
```

### DELETE /api/cancel/:jobId

Cancel an ongoing download job.

**Response:**
```json
{
  "success": true,
  "message": "Download job cancelled successfully"
}
```

## Configuration

Create a `.env` file in the root directory with the following variables:

```env
# Server Configuration
PORT=3000
NODE_ENV=development

# Download Configuration
DOWNLOAD_DIR=./downloads
MAX_CONCURRENT_DOWNLOADS=3
DOWNLOAD_TIMEOUT=3600
MAX_FILESIZE=5000000000

# API Configuration
API_KEY=your_api_key_here
RATE_LIMIT_WINDOW=15
RATE_LIMIT_MAX_REQUESTS=100

# Logging
LOG_LEVEL=info
LOG_FORMAT=json

# YT-DLP Configuration
YTDLP_SOCKET_TIMEOUT=30
YTDLP_RETRIES=3
YTDLP_SLEEP_INTERVAL=1

# Audio Processing
AUDIO_CODEC=libmp3lame
AUDIO_BITRATE=192

# Security
ALLOW_ORIGIN=*
ENABLE_HTTPS=false
SSL_CERT_PATH=./certs/cert.pem
SSL_KEY_PATH=./certs/key.pem
```

## Examples

### JavaScript/Node.js

```javascript
const axios = require('axios');

async function downloadVideo() {
  try {
    const response = await axios.post('http://localhost:3000/api/download', {
      url: 'https://www.youtube.com/watch?v=dQw4w9WgXcQ',
      format: 'best',
      quality: '720p'
    });
    
    console.log('Download successful:', response.data);
  } catch (error) {
    console.error('Download failed:', error.response.data);
  }
}

downloadVideo();
```

### Python

```python
import requests
import json

def download_video(url):
    endpoint = 'http://localhost:3000/api/download'
    payload = {
        'url': url,
        'format': 'best',
        'quality': '720p'
    }
    
    try:
        response = requests.post(endpoint, json=payload)
        response.raise_for_status()
        data = response.json()
        print('Download successful:', json.dumps(data, indent=2))
    except requests.exceptions.RequestException as e:
        print('Download failed:', e)

download_video('https://www.youtube.com/watch?v=dQw4w9WgXcQ')
```

### cURL

```bash
# Download video
curl -X POST http://localhost:3000/api/download \
  -H "Content-Type: application/json" \
  -d '{
    "url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
    "format": "best",
    "quality": "720p"
  }'

# Get available formats
curl http://localhost:3000/api/formats/dQw4w9WgXcQ

# Check download status
curl http://localhost:3000/api/status/job_123456

# Cancel download
curl -X DELETE http://localhost:3000/api/cancel/job_123456
```

## Error Handling

The API returns appropriate HTTP status codes and error messages:

### Status Codes

- `200 OK` - Successful request
- `201 Created` - Resource created successfully
- `400 Bad Request` - Invalid request parameters
- `401 Unauthorized` - Missing or invalid API key
- `403 Forbidden` - Access denied
- `404 Not Found` - Resource not found
- `429 Too Many Requests` - Rate limit exceeded
- `500 Internal Server Error` - Server error
- `503 Service Unavailable` - Service temporarily unavailable

### Error Response Format

```json
{
  "success": false,
  "error": {
    "code": "INVALID_URL",
    "message": "The provided URL is not a valid YouTube link",
    "details": {
      "url": "https://example.com/video"
    }
  }
}
```

### Common Error Codes

- `INVALID_URL` - URL is not a valid YouTube link
- `VIDEO_NOT_FOUND` - The video could not be found
- `PLAYLIST_ERROR` - Error processing playlist
- `FORMAT_NOT_AVAILABLE` - Requested format is not available
- `DOWNLOAD_TIMEOUT` - Download exceeded timeout limit
- `INSUFFICIENT_SPACE` - Not enough disk space
- `INVALID_API_KEY` - API key is invalid or expired
- `RATE_LIMIT_EXCEEDED` - Too many requests

## Rate Limiting

The API implements rate limiting to prevent abuse:

- **Default Limit**: 100 requests per 15 minutes
- **Per-IP Limiting**: Yes
- **Response Header**: `X-RateLimit-Remaining` indicates remaining requests

When rate limit is exceeded, you'll receive a `429` status code with:

```json
{
  "success": false,
  "error": {
    "code": "RATE_LIMIT_EXCEEDED",
    "message": "Rate limit exceeded. Try again in 30 seconds",
    "retryAfter": 30
  }
}
```

## Troubleshooting

### Common Issues and Solutions

#### 1. "Video not found" error
- Verify the YouTube URL is correct and the video is publicly available
- The video may be age-restricted or removed
- Try using the video ID directly instead of the full URL

#### 2. "Connection timeout" error
- Check your internet connection
- The YouTube server might be temporarily unavailable
- Increase the `YTDLP_SOCKET_TIMEOUT` in your `.env` file

#### 3. "Insufficient space" error
- Check available disk space: `df -h`
- Increase the `MAX_FILESIZE` limit if needed
- Delete old downloads to free up space

#### 4. "Format not available" error
- Some videos may not have the requested quality available
- Try using `format: 'best'` to get the best available quality
- Check available formats with the `/api/formats` endpoint

#### 5. "Port already in use" error
- The default port 3000 is already in use
- Change the PORT in your `.env` file: `PORT=3001`
- Or kill the process using the port: `lsof -ti:3000 | xargs kill -9`

#### 6. API not responding
- Ensure the server is running: `npm start`
- Check logs for errors: `tail -f logs/app.log`
- Verify the API URL is correct
- Check firewall settings

### Debugging

Enable debug logging by setting the log level:

```bash
# In .env file
LOG_LEVEL=debug
```

Then check the logs:

```bash
tail -f logs/debug.log
```

## Contributing

We welcome contributions! Please follow these guidelines:

1. Fork the repository
2. Create a feature branch: `git checkout -b feature/your-feature`
3. Commit your changes: `git commit -am 'Add new feature'`
4. Push to the branch: `git push origin feature/your-feature`
5. Submit a pull request

### Development Setup

```bash
# Install dev dependencies
npm install --save-dev

# Run tests
npm test

# Run linter
npm run lint

# Format code
npm run format
```

### Code Style

- Use ESLint for JavaScript linting
- Follow Prettier formatting rules
- Write meaningful commit messages
- Add tests for new features

## Security Considerations

- Always validate and sanitize input URLs
- Use HTTPS in production
- Keep dependencies updated regularly
- Use strong API keys
- Implement proper authentication
- Monitor for suspicious activity
- Set appropriate rate limits
- Use environment variables for sensitive data

## Performance Tips

- Use the `/api/formats` endpoint to check available formats before downloading
- Set appropriate `MAX_CONCURRENT_DOWNLOADS` based on your server resources
- Use specific quality selections instead of always choosing "best"
- Implement request queuing on the client side for batch operations
- Monitor disk space regularly

## License

This project is licensed under the MIT License - see the LICENSE file for details.

## Support

For issues, questions, or suggestions:

- 📝 Open an issue on [GitHub Issues](https://github.com/IM-SPYBOY/ytdl-api/issues)
- 💬 Start a discussion on [GitHub Discussions](https://github.com/IM-SPYBOY/ytdl-api/discussions)
- 📧 Contact the maintainers

## Disclaimer

This tool is provided for educational and personal use only. Respect copyright laws and YouTube's Terms of Service. Do not use this tool to download copyrighted content without proper authorization.

## Changelog

### Version 1.0.0 (2025-12-08)
- Initial release
- Video download support
- Playlist download support
- Audio extraction feature
- Format selection
- Queue management
- Rate limiting
- Comprehensive API documentation

---

**Last Updated**: 2025-12-08  
**Maintained by**: IM-SPYBOY
