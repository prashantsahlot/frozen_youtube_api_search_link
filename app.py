from flask import Flask, request, jsonify, send_file
import yt_dlp
import os
import uuid
import requests
import hashlib
import glob
import shutil

app = Flask(__name__)

# Base temporary directory (using /tmp for this example)
BASE_TEMP_DIR = "/tmp"

# Directory for storing temporary download files (will be cleaned after each request)
TEMP_DOWNLOAD_DIR = os.path.join(BASE_TEMP_DIR, "download")
os.makedirs(TEMP_DOWNLOAD_DIR, exist_ok=True)

# Directory for storing cached audio files (persist between requests)
CACHE_DIR = os.path.join(BASE_TEMP_DIR, "cache")
os.makedirs(CACHE_DIR, exist_ok=True)

# Path to your cookies file (if needed)
COOKIES_FILE = "cookies.txt"  # Replace with your actual cookies file path if required

# Search API URL (used both for regular searches and Spotify link resolution)
SEARCH_API_URL = "https://odd-block-a945.tenopno.workers.dev/search?title="

def get_cache_key(video_url):
    """Generate a cache key from the video URL."""
    return hashlib.md5(video_url.encode('utf-8')).hexdigest()

def download_audio(video_url):
    """
    Download audio from the given YouTube video URL with caching.
    If the audio file was previously downloaded, return the cached file.
    """
    cache_key = get_cache_key(video_url)
    # Look for any file in the cache directory with the cache key as prefix
    cached_files = glob.glob(os.path.join(CACHE_DIR, f"{cache_key}.*"))
    if cached_files:
        return cached_files[0]

    # If not cached, download the file to TEMP_DOWNLOAD_DIR
    unique_id = str(uuid.uuid4())
    output_template = os.path.join(TEMP_DOWNLOAD_DIR, f"{unique_id}.%(ext)s")
    ydl_opts = {
        'format': 'worstaudio/worst',  # Audio quality settings
        'outtmpl': output_template,     # Output template path
        'noplaylist': True,             # Only download single video
        'quiet': True,                  # Suppress verbose output
        'cookiefile': COOKIES_FILE,     # Cookies file (if needed)
        'socket_timeout': 60,           # Increased timeout in seconds
        'max_memory': 450000,           # Limit memory usage (in KB)
    }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        try:
            info = ydl.extract_info(video_url, download=True)
            downloaded_file = ydl.prepare_filename(info)
            # Determine the extension (default to m4a if not provided)
            ext = info.get("ext", "m4a")
            # Define the cached file path using the cache key and extension
            cached_file_path = os.path.join(CACHE_DIR, f"{cache_key}.{ext}")
            # Move the downloaded file to the cache directory
            shutil.move(downloaded_file, cached_file_path)
            return cached_file_path
        except Exception as e:
            raise Exception(f"Error downloading video: {e}")

def resolve_spotify_link(url):
    """
    If the URL is a Spotify link, use the search API to find the corresponding YouTube link.
    Otherwise, return the URL unchanged.
    """
    if "spotify.com" in url:
        response = requests.get(SEARCH_API_URL + url)
        if response.status_code != 200:
            raise Exception("Failed to fetch search results for the Spotify link")
        search_result = response.json()
        if not search_result or 'link' not in search_result:
            raise Exception("No YouTube link found for the given Spotify link")
        return search_result['link']
    return url

@app.route('/search', methods=['GET'])
def search_video():
    """
    Search for a YouTube video using the external API.
    """
    try:
        query = request.args.get('title')
        if not query:
            return jsonify({"error": "The 'title' parameter is required"}), 400

        response = requests.get(SEARCH_API_URL + query)
        if response.status_code != 200:
            return jsonify({"error": "Failed to fetch search results"}), 500

        search_result = response.json()
        if not search_result or 'link' not in search_result:
            return jsonify({"error": "No videos found for the given query"}), 404

        return jsonify({
            "title": search_result["title"],
            "url": search_result["link"],
            "duration": search_result.get("duration"),
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

def download_video(video_url):
    """
    Download video (with audio) from the given YouTube video URL in 360p or lower quality with caching.
    If the video file was previously downloaded, return the cached file.
    """
    # Create a cache key that is unique for video downloads.
    cache_key = hashlib.md5((video_url + "_video").encode('utf-8')).hexdigest()
    cached_files = glob.glob(os.path.join(CACHE_DIR, f"{cache_key}.*"))
    if cached_files:
        return cached_files[0]

    unique_id = str(uuid.uuid4())
    output_template = os.path.join(TEMP_DOWNLOAD_DIR, f"{unique_id}.%(ext)s")
    # yt-dlp options: download the best available video with height<=360 (with audio if available)
    ydl_opts = {
        'format': 'best[height<=720]',
        'outtmpl': output_template,
        'noplaylist': True,
        'quiet': True,
        'cookiefile': COOKIES_FILE,
        'socket_timeout': 60,
        'max_memory': 450000,
    }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        try:
            info = ydl.extract_info(video_url, download=True)
            downloaded_file = ydl.prepare_filename(info)
            # Use the extension provided in info or default to mp4
            ext = info.get("ext", "mp4")
            cached_file_path = os.path.join(CACHE_DIR, f"{cache_key}.{ext}")
            shutil.move(downloaded_file, cached_file_path)
            return cached_file_path
        except Exception as e:
            raise Exception(f"Error downloading video: {e}")

@app.route('/vdown', methods=['GET'])
def download_video_endpoint():
    """
    Download video from a YouTube video URL (or search by title) in 360p or lower quality.
    Works similarly to the /download endpoint, but returns the video file.
    """
    try:
        video_url = request.args.get('url')
        video_title = request.args.get('title')

        if not video_url and not video_title:
            return jsonify({"error": "Either 'url' or 'title' parameter is required"}), 400

        # If title provided and URL not, perform search
        if video_title and not video_url:
            response = requests.get(SEARCH_API_URL + video_title)
            if response.status_code != 200:
                return jsonify({"error": "Failed to fetch search results"}), 500
            search_result = response.json()
            if not search_result or 'link' not in search_result:
                return jsonify({"error": "No videos found for the given query"}), 404
            video_url = search_result['link']

        # Resolve Spotify links if needed
        if video_url and "spotify.com" in video_url:
            video_url = resolve_spotify_link(video_url)

        # Download (or get from cache) the video file
        cached_file_path = download_video(video_url)

        return send_file(
            cached_file_path,
            as_attachment=True,
            download_name=os.path.basename(cached_file_path)
        )
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        # Clean up temporary download files; cached files remain intact
        for file in os.listdir(TEMP_DOWNLOAD_DIR):
            file_path = os.path.join(TEMP_DOWNLOAD_DIR, file)
            try:
                os.remove(file_path)
            except Exception as cleanup_error:
                print(f"Error deleting file {file_path}: {cleanup_error}")


@app.route('/download', methods=['GET'])
def download_audio_endpoint():
    """
    Download audio from a YouTube video URL or search for it by title and download.
    Utilizes caching so repeated downloads for the same video are avoided.
    Also supports Spotify links by resolving them via the search API.
    """
    try:
        video_url = request.args.get('url')
        video_title = request.args.get('title')

        if not video_url and not video_title:
            return jsonify({"error": "Either 'url' or 'title' parameter is required"}), 400

        # If a title is provided and URL is not, perform a search
        if video_title and not video_url:
            response = requests.get(SEARCH_API_URL + video_title)
            if response.status_code != 200:
                return jsonify({"error": "Failed to fetch search results"}), 500

            search_result = response.json()
            if not search_result or 'link' not in search_result:
                return jsonify({"error": "No videos found for the given query"}), 404

            video_url = search_result['link']

        # If the provided URL is a Spotify link, resolve it to a YouTube link
        if video_url and "spotify.com" in video_url:
            video_url = resolve_spotify_link(video_url)

        # Download (or fetch from cache) the audio file
        cached_file_path = download_audio(video_url)

        return send_file(
            cached_file_path,
            as_attachment=True,
            download_name=os.path.basename(cached_file_path)
        )
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        # Clean up temporary download files; cached files remain intact
        for file in os.listdir(TEMP_DOWNLOAD_DIR):
            file_path = os.path.join(TEMP_DOWNLOAD_DIR, file)
            try:
                os.remove(file_path)
            except Exception as cleanup_error:
                print(f"Error deleting file {file_path}: {cleanup_error}")

@app.route('/')
def home():
    return """
    <h1>🎶 YouTube Audio Downloader API</h1>
    <p>Use this API to search and download audio from YouTube videos.</p>
    <p><strong>Endpoints:</strong></p>
    <ul>
        <li><strong>/search</strong>: Search for a video by title. Query parameter: <code>?title=</code></li>
        <li><strong>/download</strong>: Download audio by URL or search for a title and download. Query parameters: <code>?url=</code> or <code>?title=</code></li>
    </ul>
    <p>Examples:</p>
    <ul>
        <li>Search: <code>/search?title=Your%20Favorite%20Song</code></li>
        <li>Download by URL: <code>/download?url=https://www.youtube.com/watch?v=dQw4w9WgXcQ</code></li>
        <li>Download by Title: <code>/download?title=Your%20Favorite%20Song</code></li>
        <li>Download from Spotify: <code>/download?url=https://open.spotify.com/track/...</code></li>
    </ul>
    """

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)

