from flask import Flask, request, jsonify, send_file
import yt_dlp
import os
import uuid
import requests
import hashlib
import glob
import shutil
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# Base directory using /tmp (Render free plan uses ephemeral storage)
BASE_TEMP_DIR = "/tmp"
# Directories for temporary downloads and caches
TEMP_DOWNLOAD_DIR = os.path.join(BASE_TEMP_DIR, "download")
CACHE_AUDIO_DIR = os.path.join(BASE_TEMP_DIR, "cache_audio")
CACHE_VIDEO_DIR = os.path.join(BASE_TEMP_DIR, "cache_video")
for directory in (TEMP_DOWNLOAD_DIR, CACHE_AUDIO_DIR, CACHE_VIDEO_DIR):
    os.makedirs(directory, exist_ok=True)

# Cache settings
MAX_CACHE_SIZE = 500 * 1024 * 1024  # 500 MB
COOKIES_FILE = "cookies.txt"
SEARCH_API_URL = "https://odd-block-a945.tenopno.workers.dev/search?title="


def get_cache_key(url: str) -> str:
    """Generate an MD5 cache key for a given URL"""
    return hashlib.md5(url.encode('utf-8')).hexdigest()


def get_directory_size(path: str) -> int:
    """Return size of all files in directory (bytes)"""
    total = 0
    for root, _, files in os.walk(path):
        for f in files:
            fp = os.path.join(root, f)
            if os.path.isfile(fp):
                total += os.path.getsize(fp)
    return total


def check_cache_size_and_cleanup() -> None:
    """Clear entire cache if combined size exceeds limit"""
    total = get_directory_size(CACHE_AUDIO_DIR) + get_directory_size(CACHE_VIDEO_DIR)
    if total > MAX_CACHE_SIZE:
        logger.info("Cache size exceeded %d bytes, clearing all caches", MAX_CACHE_SIZE)
        for cache_dir in (CACHE_AUDIO_DIR, CACHE_VIDEO_DIR):
            for fname in os.listdir(cache_dir):
                try:
                    os.remove(os.path.join(cache_dir, fname))
                except OSError as e:
                    logger.warning("Failed to remove cache file %s: %s", fname, e)


def resolve_spotify_link(url: str) -> str:
    """If the URL is a Spotify track, resolve to YouTube via external API"""
    if 'spotify.com' in url:
        resp = requests.get(SEARCH_API_URL + url)
        resp.raise_for_status()
        data = resp.json()
        if 'link' not in data:
            raise Exception("No corresponding YouTube link found for Spotify URL.")
        return data['link']
    return url


def download_audio(video_url: str) -> str:
    """Download worst-quality audio only, with caching"""
    key = get_cache_key(video_url)
    # Return cached
    cached = glob.glob(os.path.join(CACHE_AUDIO_DIR, f"{key}.*"))
    if cached:
        logger.info("Serving audio from cache: %s", cached[0])
        return cached[0]

    tmp_out = os.path.join(TEMP_DOWNLOAD_DIR, f"{uuid.uuid4()}.%(ext)s")
    ydl_opts = {
        'format': 'worstaudio/worst',
        'outtmpl': tmp_out,
        'noplaylist': True,
        'quiet': True,
        'cookiefile': COOKIES_FILE,
        'socket_timeout': 60,
        'max_memory': 450000,
        'geo_bypass': True,
        'nocheckcertificate': True
    }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(video_url, download=True)
        filename = ydl.prepare_filename(info)

    ext = info.get('ext', 'm4a')
    cached_path = os.path.join(CACHE_AUDIO_DIR, f"{key}.{ext}")
    shutil.move(filename, cached_path)
    check_cache_size_and_cleanup()
    return cached_path


def download_video(video_url: str) -> str:
    """Download 240p video + worst audio, with caching"""
    key = get_cache_key(video_url + "_video")
    cached = glob.glob(os.path.join(CACHE_VIDEO_DIR, f"{key}.*"))
    if cached:
        logger.info("Serving video from cache: %s", cached[0])
        return cached[0]

    tmp_out = os.path.join(TEMP_DOWNLOAD_DIR, f"{uuid.uuid4()}.%(ext)s")
    ydl_opts = {
        'format': 'bestvideo[height<=240]+worstaudio/worst',
        'outtmpl': tmp_out,
        'noplaylist': True,
        'quiet': True,
        'cookiefile': COOKIES_FILE,
        'socket_timeout': 60,
        'max_memory': 450000,
        'geo_bypass': True,
        'nocheckcertificate': True,
        'merge_output_format': 'mp4'
    }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(video_url, download=True)
        filename = ydl.prepare_filename(info)

    cached_path = os.path.join(CACHE_VIDEO_DIR, f"{key}.mp4")
    shutil.move(filename, cached_path)
    check_cache_size_and_cleanup()
    return cached_path


def clean_temp():
    """Remove all files from temp download directory"""
    for fname in os.listdir(TEMP_DOWNLOAD_DIR):
        try:
            os.remove(os.path.join(TEMP_DOWNLOAD_DIR, fname))
        except OSError:
            pass


@app.route('/search', methods=['GET'])
def search_video():
    """Search for a YouTube video by title via external API"""
    title = request.args.get('title')
    if not title:
        return jsonify(error="The 'title' query parameter is required."), 400
    try:
        resp = requests.get(SEARCH_API_URL + title)
        resp.raise_for_status()
        data = resp.json()
        if 'link' not in data:
            return jsonify(error="No video found for the given title."), 404
        return jsonify(title=data.get('title'), url=data['link'], duration=data.get('duration'))
    except Exception as e:
        logger.error("Search API error: %s", e)
        return jsonify(error=str(e)), 500


@app.route('/download', methods=['GET'])
def download_audio_endpoint():
    """Endpoint to download audio by URL or title"""
    try:
        url = request.args.get('url')
        title = request.args.get('title')
        if not url and not title:
            return jsonify(error="Provide either 'url' or 'title' query parameter."), 400

        if title and not url:
            resp = requests.get(SEARCH_API_URL + title)
            resp.raise_for_status()
            data = resp.json()
            url = data.get('link')
            if not url:
                return jsonify(error="No video found for the given title."), 404

        url = resolve_spotify_link(url)
        path = download_audio(url)
        return send_file(path, as_attachment=True, download_name=os.path.basename(path))
    except Exception as e:
        logger.error("/download error: %s", e)
        return jsonify(error=str(e)), 500
    finally:
        clean_temp()


@app.route('/vdown', methods=['GET'])
def download_video_endpoint():
    """Endpoint to download video by URL or title"""
    try:
        url = request.args.get('url')
        title = request.args.get('title')
        if not url and not title:
            return jsonify(error="Provide either 'url' or 'title' query parameter."), 400

        if title and not url:
            resp = requests.get(SEARCH_API_URL + title)
            resp.raise_for_status()
            data = resp.json()
            url = data.get('link')
            if not url:
                return jsonify(error="No video found for the given title."), 404

        url = resolve_spotify_link(url)
        path = download_video(url)
        return send_file(path, as_attachment=True, download_name=os.path.basename(path))
    except Exception as e:
        logger.error("/vdown error: %s", e)
        return jsonify(error=str(e)), 500
    finally:
        clean_temp()


@app.route('/')
def home():
    return (
        "<h1>🎶 YouTube Downloader API</h1>"
        "<p>Use /search, /download (audio), or /vdown (video).</p>"
    )

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)



