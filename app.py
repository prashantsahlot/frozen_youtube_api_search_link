from flask import Flask, request, jsonify, send_file
import yt_dlp
import os
import uuid
import requests

app = Flask(__name__)

# Directory for storing temporary files
TEMP_DIR = "/tmp"
os.makedirs(TEMP_DIR, exist_ok=True)

# Path to your cookies file (if needed)
COOKIES_FILE = "cookies.txt"  # Replace with your actual cookies file path if required

# Search API URL
SEARCH_API_URL = "https://small-bush-de65.tenopno.workers.dev/search?title="

def download_audio(video_url):
    """
    Download audio from the given YouTube video URL.
    """
    unique_id = str(uuid.uuid4())
    output_template = os.path.join(TEMP_DIR, f"{unique_id}.%(ext)s")

    ydl_opts = {
        'format': 'bestaudio/best',
        'outtmpl': output_template,
        'noplaylist': True,
        'quiet': True,
        'cookiefile': COOKIES_FILE,
    }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(video_url, download=True)
        downloaded_file = ydl.prepare_filename(info)
        return downloaded_file


@app.route('/search', methods=['GET'])
def search_video():
    """
    Search for a YouTube video using the external API.
    """
    try:
        query = request.args.get('title')
        if not query:
            return jsonify({"error": "The 'title' parameter is required"}), 400

        # Use the external search API
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
    Download audio from a YouTube video URL or search for it by title and download.
    """
    try:
        video_url = request.args.get('url')
        video_title = request.args.get('title')

        if not video_url and not video_title:
            return jsonify({"error": "Either 'url' or 'title' parameter is required"}), 400

        # Search by title if no URL is provided
        if video_title:
            response = requests.get(SEARCH_API_URL + video_title)
            if response.status_code != 200:
                return jsonify({"error": "Failed to fetch search results"}), 500

            search_result = response.json()
            if not search_result or 'link' not in search_result:
                return jsonify({"error": "No videos found for the given query"}), 404

            video_url = search_result['link']

        # Download audio
        downloaded_file = download_audio(video_url)

        # Serve the downloaded file
        return send_file(
            downloaded_file,
            as_attachment=True,
            download_name=os.path.basename(downloaded_file)
        )
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        # Cleanup temporary files
        for file in os.listdir(TEMP_DIR):
            file_path = os.path.join(TEMP_DIR, file)
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
    </ul>
    """


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)

