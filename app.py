from flask import Flask, request, jsonify, send_file
from youtubesearchpython import VideosSearch
import yt_dlp
import os
import uuid

app = Flask(__name__)

# Directory for storing temporary files (consider a secure location)
TEMP_DIR = "/tmp/youtube_downloader"  # Use a dedicated subdirectory
# Ensure the directory exists (with appropriate permissions)
os.makedirs(TEMP_DIR, exist_ok=True)

# Path to your cookies file (secure this file)
COOKIES_FILE = "cookies.txt"  # Replace with your actual path

# Function to generate a unique filename with extension
def generate_unique_filename(ext):
    unique_id = str(uuid.uuid4())
    return os.path.join(TEMP_DIR, f"{unique_id}.{ext}")

@app.route('/search', methods=['GET'])
def search_video():
    """
    Search for a YouTube video by title using youtubesearchpython.
    """
    try:
        # Get the query parameter for the search
        query = request.args.get('title')
        if not query:
            return jsonify({"error": "The 'title' parameter is required"}), 400

        # Use youtubesearchpython to search for videos
        search = VideosSearch(query, limit=1)
        results = search.result()
        if not results["result"]:
            return jsonify({"error": "No videos found for the given title"}), 404

        # Get the first video's details
        video = results["result"][0]
        return jsonify({
            "title": video["title"],
            "url": video["link"],
            "duration": video["duration"],
            "channel": video["channel"]["name"],
        })
    except Exception as e:
        # Log the error for debugging
        print(f"Error searching video: {e}")
        return jsonify({"error": "An error occurred during search"}), 500

@app.route('/download', methods=['GET'])
def download_video():
    """
    Download a YouTube video by URL or search for a video by title and download.
    """
    try:
        # Get the video URL or title from query parameters
        video_url = request.args.get('url')
        video_title = request.args.get('title')

        # Check if either URL or title is provided
        if not video_url and not video_title:
            return jsonify({"error": "Either 'url' or 'title' parameter is required"}), 400

        # If title is provided, search for the video and get the URL
        if video_title:
            search = VideosSearch(video_title, limit=1)
            results = search.result()
            if not results["result"]:
                return jsonify({"error": "No videos found for the given title"}), 404
            video_url = results["result"][0]["link"]

        # Generate a unique filename with extension
        output_template = generate_unique_filename("%(ext)s")

        # yt-dlp options
        ydl_opts = {
            'format': 'mp4',  # You can specify other formats ('best', 'bestaudio', etc.)
            'outtmpl': output_template,
            'quiet': True,
            # Consider using a secure way to handle cookies (e.g., environment variables)
            # 'cookiefile': COOKIES_FILE,
        }

        # Download the video
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            try:
                info = ydl.extract_info(video_url, download=True)
            except yt_dlp.utils.DownloadError as e:
                # Handle specific download errors
                print(f"Download error: {e}")
                return jsonify({"error": "Error downloading the video"}), 500
            downloaded_file = ydl.prepare_filename(info)

        # Send the file to the user (consider security implications)
        return send_file(downloaded_file, as_attachment=True, download_name=os.path.basename
