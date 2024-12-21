from flask import Flask, request, jsonify, send_file
import yt_dlp
import os
import uuid

app = Flask(__name__)

# Directory for storing temporary files
TEMP_DIR = "/tmp"
os.makedirs(TEMP_DIR, exist_ok=True)

# Path to your cookies file
COOKIES_FILE = "cookies.txt"  # Replace with your actual cookies file path

@app.route('/search', methods=['GET'])
def search_video():
    """
    Search for a YouTube video by title using yt-dlp.
    """
    try:
        query = request.args.get('title')
        if not query:
            return jsonify({"error": "The 'title' parameter is required"}), 400

        # yt-dlp options for searching
        ydl_opts = {
            'quiet': True,
            'cookiefile': COOKIES_FILE,
            'simulate': True,  # Do not download, just fetch metadata
        }

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            search_results = ydl.extract_info(f"ytsearch:{query}", download=False)

        if not search_results or 'entries' not in search_results or not search_results['entries']:
            return jsonify({"error": "No videos found for the given title"}), 404

        video = search_results['entries'][0]
        return jsonify({
            "title": video["title"],
            "url": video["webpage_url"],
            "duration": video.get("duration"),
            "channel": video.get("uploader"),
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/download', methods=['GET'])
def download_video():
    """
    Download a YouTube video by URL or search for a video by title and download.
    """
    try:
        video_url = request.args.get('url')
        video_title = request.args.get('title')

        if not video_url and not video_title:
            return jsonify({"error": "Either 'url' or 'title' parameter is required"}), 400

        if video_title:
            ydl_opts = {
                'quiet': True,
                'cookiefile': COOKIES_FILE,
                'simulate': True,
            }

            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                search_results = ydl.extract_info(f"ytsearch:{video_title}", download=False)

            if not search_results or 'entries' not in search_results or not search_results['entries']:
                return jsonify({"error": "No videos found for the given title"}), 404

            video_url = search_results['entries'][0]['webpage_url']

        unique_id = str(uuid.uuid4())
        output_template = os.path.join(TEMP_DIR, f"{unique_id}.%(ext)s")

        ydl_opts = {
            'format': 'bestvideo+bestaudio/best',
            'outtmpl': output_template,
            'quiet': True,
            'cookiefile': COOKIES_FILE,
        }

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(video_url, download=True)
            downloaded_file = ydl.prepare_filename(info)

        return send_file(
            downloaded_file,
            as_attachment=True,
            download_name=os.path.basename(downloaded_file)
        )
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        for file in os.listdir(TEMP_DIR):
            file_path = os.path.join(TEMP_DIR, file)
            try:
                os.remove(file_path)
            except Exception as cleanup_error:
                print(f"Error deleting file {file_path}: {cleanup_error}")

@app.route('/')
def home():
    return """
    <h1>🎥 YouTube Video Downloader API</h1>
    <p>Use this API to search and download YouTube videos.</p>
    <p><strong>Endpoints:</strong></p>
    <ul>
        <li><strong>/search</strong>: Search for a video by title. Query parameter: <code>?title=</code></li>
        <li><strong>/download</strong>: Download a video by URL or search for a title and download. Query parameters: <code>?url=</code> or <code>?title=</code></li>
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

