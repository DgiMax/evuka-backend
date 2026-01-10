import requests
import subprocess
import time
import os

# --- CONFIGURATION (Hardcoded to eliminate variable errors) ---
LIBRARY_ID = "576084"
API_KEY = "ad887a2c-493d-481b-9799ca4975e5-fe45-4f6f"  # Your Master/Library Key
# We use the IP and Port 443 to bypass the University Block
RTMP_SERVER = "rtmps://185.152.64.17:443/live"


def step_1_create_video():
    print("\n🔹 STEP 1: Creating Live Container in Bunny...")
    url = f"https://video.bunnycdn.com/library/{LIBRARY_ID}/videos"
    headers = {"AccessKey": API_KEY, "Content-Type": "application/json"}
    payload = {"title": f"Test Stream {int(time.time())}"}

    try:
        resp = requests.post(url, json=payload, headers=headers)
        if resp.status_code != 200:
            print(f"❌ API ERROR: {resp.status_code} - {resp.text}")
            return None, None

        data = resp.json()
        video_id = data.get("guid")
        print(f"✅ Video Created! ID: {video_id}")

        # KEY LOGIC: If Bunny returns no specific key, the API KEY is the password.
        stream_key = data.get("streamKey")
        if not stream_key:
            print("ℹ️  No specific stream key returned (Standard behavior). Using API Key.")
            stream_key = API_KEY
        else:
            print(f"ℹ️  Specific stream key found: {stream_key}")

        return video_id, stream_key
    except Exception as e:
        print(f"❌ CRITICAL API FAILURE: {e}")
        return None, None


def step_2_test_stream(video_id, password):
    print("\n🔹 STEP 2: Attempting to Stream (5 seconds)...")

    # Construct the Target URL
    # Format: rtmps://SERVER/live/VIDEO_ID?token=PASSWORD
    # We use -tls_verify 0 to ignore certificate issues (common in testing)
    rtmp_target = f"{RTMP_SERVER}/{video_id}?token={password}"

    print(f"📡 Target: {RTMP_SERVER}/{video_id}?token=HIDDEN")

    cmd = [
        "ffmpeg",
        "-f", "lavfi", "-i", "testsrc=size=1280x720:rate=30",  # Generate fake video
        "-f", "lavfi", "-i", "sine=frequency=1000:duration=5",  # Generate fake audio
        "-c:v", "libx264", "-preset", "ultrafast",
        "-c:a", "aac",
        "-t", "5",  # Run for 5 seconds then stop
        "-tls_verify", "0",  # Ignore SSL errors
        "-f", "flv",
        rtmp_target
    ]

    try:
        # Run FFmpeg and capture output
        process = subprocess.run(cmd, capture_output=True, text=True)

        if process.returncode == 0:
            print("\n✅ SUCCESS! FFmpeg streamed successfully.")
            print("👉 This proves the URL and Key format are correct.")
            return True
        else:
            print("\n❌ STREAM FAILED.")
            print("🔎 FFmpeg Error Logs:")
            # Print only the last 10 lines of error log
            print('\n'.join(process.stderr.splitlines()[-10:]))
            return False
    except FileNotFoundError:
        print("❌ ERROR: FFmpeg is not installed on your computer.")
        return False


if __name__ == "__main__":
    vid_id, password = step_1_create_video()
    if vid_id:
        step_2_test_stream(vid_id, password)