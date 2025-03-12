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

# Directory for storing cached files (persist between requests)
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
    Download audio (old endpoint) with caching.
    """
    cache_key = get_cache_key(video_url)
    cached_files = glob.glob(os.path.join(CACHE_DIR, f"{cache_key}.*"))
    if cached_files:
        return cached_files[0]

    unique_id = str(uuid.uuid4())
    output_template = os.path.join(TEMP_DOWNLOAD_DIR, f"{unique_id}.%(ext)s")
    ydl_opts = {
        'format': 'worstaudio/worst',
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
            ext = info.get("ext", "m4a")
            cached_file_path = os.path.join(CACHE_DIR, f"{get_cache_key(video_url)}.{ext}")
            shutil.move(downloaded_file, cached_file_path)
            return cached_file_path
        except Exception as e:
            raise Exception(f"Error downloading video: {e}")

def resolve_spotify_link(url):
    """
    Resolve a Spotify link to a YouTube link via the search API.
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

@app.route('/download', methods=['GET'])
def download_audio_endpoint():
    """
    Download audio from a YouTube video URL or by title.
    """
    try:
        video_url = request.args.get('url')
        video_title = request.args.get('title')
        if not video_url and not video_title:
            return jsonify({"error": "Either 'url' or 'title' parameter is required"}), 400
        if video_title and not video_url:
            response = requests.get(SEARCH_API_URL + video_title)
            if response.status_code != 200:
                return jsonify({"error": "Failed to fetch search results"}), 500
            search_result = response.json()
            if not search_result or 'link' not in search_result:
                return jsonify({"error": "No videos found for the given query"}), 404
            video_url = search_result['link']
        if video_url and "spotify.com" in video_url:
            video_url = resolve_spotify_link(video_url)
        cached_file_path = download_audio(video_url)
        return send_file(
            cached_file_path,
            as_attachment=True,
            download_name=os.path.basename(cached_file_path)
        )
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        for file in os.listdir(TEMP_DOWNLOAD_DIR):
            file_path = os.path.join(TEMP_DOWNLOAD_DIR, file)
            try:
                os.remove(file_path)
            except Exception as cleanup_error:
                print(f"Error deleting file {file_path}: {cleanup_error}")

# --- New endpoints for /song command ---

@app.route('/song/audio', methods=['GET'])
def song_audio_download():
    """
    Download high-quality audio with embedded thumbnail and metadata.
    Accepts ?url= or ?title=.
    """
    try:
        video_url = request.args.get('url')
        video_title = request.args.get('title')
        if not video_url and not video_title:
            return jsonify({"error": "Either 'url' or 'title' parameter is required"}), 400
        if video_title and not video_url:
            response = requests.get(SEARCH_API_URL + video_title)
            if response.status_code != 200:
                return jsonify({"error": "Failed to fetch search results"}), 500
            search_result = response.json()
            if not search_result or 'link' not in search_result:
                return jsonify({"error": "No videos found for the given query"}), 404
            video_url = search_result['link']
        if video_url and "spotify.com" in video_url:
            video_url = resolve_spotify_link(video_url)
        cache_key = get_cache_key(video_url)
        cached_files = glob.glob(os.path.join(CACHE_DIR, f"{cache_key}_hq_audio.*"))
        if cached_files:
            file_to_send = cached_files[0]
        else:
            unique_id = str(uuid.uuid4())
            output_template = os.path.join(TEMP_DOWNLOAD_DIR, f"{unique_id}.%(ext)s")
            ydl_opts = {
                'format': 'bestaudio/best',
                'outtmpl': output_template,
                'noplaylist': True,
                'quiet': True,
                'cookiefile': COOKIES_FILE,
                'socket_timeout': 120,
                'max_memory': 450000,
                'postprocessors': [
                    {'key': 'FFmpegExtractAudio', 'preferredcodec': 'mp3', 'preferredquality': '320'},
                    {'key': 'FFmpegMetadata'},
                    {'key': 'EmbedThumbnail'}
                ],
                'writethumbnail': True,
                'embedthumbnail': True,
                'addmetadata': True,
            }
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                try:
                    info = ydl.extract_info(video_url, download=True)
                    # The final file should be unique_id.mp3
                    final_file = os.path.join(TEMP_DOWNLOAD_DIR, f"{unique_id}.mp3")
                    if not os.path.exists(final_file):
                        raise Exception("Downloaded file not found")
                    cached_file_path = os.path.join(CACHE_DIR, f"{cache_key}_hq_audio.mp3")
                    shutil.move(final_file, cached_file_path)
                    file_to_send = cached_file_path
                except Exception as e:
                    raise Exception(f"Error downloading audio: {e}")
        return send_file(
            file_to_send,
            as_attachment=True,
            download_name=os.path.basename(file_to_send)
        )
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        for file in os.listdir(TEMP_DOWNLOAD_DIR):
            file_path = os.path.join(TEMP_DOWNLOAD_DIR, file)
            try:
                os.remove(file_path)
            except Exception as cleanup_error:
                print(f"Error deleting file {file_path}: {cleanup_error}")

@app.route('/song/video', methods=['GET'])
def song_video_download():
    """
    Download video in 720p (or lower) to keep file size under 50 MB.
    Accepts ?url= or ?title=.
    """
    try:
        video_url = request.args.get('url')
        video_title = request.args.get('title')
        if not video_url and not video_title:
            return jsonify({"error": "Either 'url' or 'title' parameter is required"}), 400
        if video_title and not video_url:
            response = requests.get(SEARCH_API_URL + video_title)
            if response.status_code != 200:
                return jsonify({"error": "Failed to fetch search results"}), 500
            search_result = response.json()
            if not search_result or 'link' not in search_result:
                return jsonify({"error": "No videos found for the given query"}), 404
            video_url = search_result['link']
        if video_url and "spotify.com" in video_url:
            video_url = resolve_spotify_link(video_url)
        cache_key = get_cache_key(video_url)
        cached_files = glob.glob(os.path.join(CACHE_DIR, f"{cache_key}_hq_video.*"))
        if cached_files:
            file_to_send = cached_files[0]
        else:
            unique_id = str(uuid.uuid4())
            output_template = os.path.join(TEMP_DOWNLOAD_DIR, f"{unique_id}.%(ext)s")
            # Use a format that limits height to 720p and sets a max file size of 50 MB.
            ydl_opts = {
                'format': 'bestvideo[height<=720]+bestaudio/best[height<=720]',
                'outtmpl': output_template,
                'noplaylist': True,
                'quiet': True,
                'cookiefile': COOKIES_FILE,
                'socket_timeout': 120,
                'max_filesize': 52428800,  # 50 MB in bytes
                'max_memory': 450000,
            }
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                try:
                    info = ydl.extract_info(video_url, download=True)
                    downloaded_file = ydl.prepare_filename(info)
                    ext = info.get("ext", "mp4")
                    cached_file_path = os.path.join(CACHE_DIR, f"{cache_key}_hq_video.{ext}")
                    shutil.move(downloaded_file, cached_file_path)
                    file_to_send = cached_file_path
                except Exception as e:
                    raise Exception(f"Error downloading video: {e}")
        return send_file(
            file_to_send,
            as_attachment=True,
            download_name=os.path.basename(file_to_send)
        )
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
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
        <li><strong>/download</strong>: Download audio by URL or title.</li>
        <li><strong>/song/audio</strong>: Download high-quality audio with thumbnail/metadata.</li>
        <li><strong>/song/video</strong>: Download high-quality video.</li>
    </ul>
    """

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)

