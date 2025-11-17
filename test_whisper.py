#!/usr/bin/env python3
import whisper
import os

# Add FFmpeg to PATH for this Python session
ffmpeg_path = r"C:\Users\ceato\AppData\Local\Microsoft\WinGet\Packages\Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe\ffmpeg-8.0-full_build\bin"
if ffmpeg_path not in os.environ.get('PATH', ''):
    os.environ['PATH'] = ffmpeg_path + ';' + os.environ.get('PATH', '')
    print(f"Added FFmpeg to PATH: {ffmpeg_path}")

# Load model
print("Loading Whisper model...")
model = whisper.load_model("tiny")
print("Model loaded!")

# Test transcription with one of the preserved audio files
audio_file = os.path.abspath("audio_files/audio_1757950622668.wav")

print(f"Testing transcription of: {audio_file}")
print(f"File exists: {os.path.exists(audio_file)}")
print(f"File size: {os.path.getsize(audio_file) if os.path.exists(audio_file) else 'N/A'}")

# First try to read the file with basic Python
print("Testing basic file access...")
try:
    with open(audio_file, 'rb') as f:
        data = f.read(100)  # Read first 100 bytes
        print(f"Successfully read first 100 bytes: {len(data)}")
        print(f"First few bytes: {data[:20].hex()}")
except Exception as e:
    print(f"Basic file read error: {e}")

# Now try Whisper
print("Testing Whisper transcription...")
try:
    result = model.transcribe(audio_file)
    print(f"Transcription: {result['text']}")
except Exception as e:
    print(f"Whisper error: {e}")
    import traceback
    traceback.print_exc()