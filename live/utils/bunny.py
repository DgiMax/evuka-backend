import requests
import logging
from django.conf import settings

# Logger setup
logger = logging.getLogger(__name__)

# ✅ CORRECT: Use the /livestreams endpoint (NOT /videos)
# This creates a Live Stream capable of accepting RTMP input.
LIBRARY_ID = getattr(settings, 'BUNNY_LIBRARY_ID', '')
API_KEY = getattr(settings, 'BUNNY_API_KEY', '')
BASE_URL = f"https://video.bunnycdn.com/library/{LIBRARY_ID}/livestreams"

HEADERS = {
    "AccessKey": API_KEY,
    "Content-Type": "application/json",
    "Accept": "application/json"
}


def get_or_create_bunny_stream(lesson):
    """
    Creates a LIVE STREAM container in Bunny.net.
    Returns the Video ID and the specific Stream Key required for authentication.
    """
    # 1. Return existing data if present
    if lesson.bunny_video_id and lesson.stream_key:
        return {
            "video_id": lesson.bunny_video_id,
            "stream_key": lesson.stream_key,
            "playback_url": lesson.hls_playback_url
        }

    try:
        logger.info(f"📡 Creating LIVE STREAM for: {lesson.title}")

        # 2. Create Live Stream
        payload = {"title": f"Live: {lesson.title}"}
        response = requests.post(BASE_URL, json=payload, headers=HEADERS)
        response.raise_for_status()

        data = response.json()

        # 3. Extract Details
        video_id = data.get("guid")
        # ✅ CRITICAL: The /livestreams endpoint returns a specific 'streamKey'
        real_stream_key = data.get("streamKey")

        if not real_stream_key:
            logger.error("❌ Bunny API returned no streamKey. Is the API Key correct?")
            return None

        # 4. Construct Playback URL
        pull_zone = getattr(settings, 'BUNNY_PULL_ZONE', 'evuka-live')
        playback_url = f"https://{pull_zone}.b-cdn.net/{video_id}/playlist.m3u8"

        # 5. Save to DB
        lesson.bunny_video_id = video_id
        lesson.stream_key = real_stream_key
        lesson.hls_playback_url = playback_url
        lesson.save()

        logger.info(f"✅ SUCCESS! Live Stream Ready. ID: {video_id}")

        return {
            "video_id": video_id,
            "stream_key": real_stream_key,
            "playback_url": playback_url
        }

    except Exception as e:
        logger.error(f"❌ Bunny Live API Error: {e}")
        return None