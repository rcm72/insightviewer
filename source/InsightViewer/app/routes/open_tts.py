# SPDX-License-Interier: AGPL-3.0-or-later
# Copyright (c) 2025 Robert Čmrlec

from pathlib import Path
from openai import OpenAI
import os, configparser
import re
from pydub import AudioSegment  # pip install pydub ; system: sudo apt install ffmpeg

# --- load config (same logic as app.py) ---

config = configparser.ConfigParser()

# compute project root (two levels up from routes/)
base_dir = os.getenv('BASE_DIR', os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))
config_path = os.path.join(base_dir, 'config.ini')
config.read(config_path)

print("config_path:", config_path)

# prefer env var, fallback to config.ini [NEO4J].OPENAI_API_KEY
OPENAI_API_KEY = os.environ.get('OPENAI_API_KEY') or config.get('NEO4J', 'OPENAI_API_KEY', fallback=None)
if not OPENAI_API_KEY:
    raise RuntimeError("OPENAI_API_KEY not set in environment or config.ini")

client = OpenAI(api_key=OPENAI_API_KEY)
speech_file_path = Path(__file__).parent / "InsightViewer_04.mp3"

print("Will write TTS to:", speech_file_path.resolve())

def synth_per_character(script_text: str, voice_map: dict, out_path: Path):
    tmp_files = []
    # split blocks like "Hamurabi: ...\n\nNext:"
    pattern = re.compile(r'^(?P<speaker>[A-Za-zčšžČŠŽ\- ]+):\s*(?P<body>.*?)(?=(?:^[A-Za-zčšžČŠŽ\- ]+:)|\Z)', re.M | re.S)
    for i, m in enumerate(pattern.finditer(script_text)):
        speaker = m.group('speaker').strip()
        body = m.group('body').strip()
        voice = voice_map.get(speaker, "coral")  # default if not mapped
        tmp = Path(f"{speech_file_path.parent}/tmp_{i}_{speaker.replace(' ','_')}.mp3")
        print("Synthesizing", speaker, "->", tmp, "voice:", voice)
        try:
            with client.audio.speech.with_streaming_response.create(
                model="gpt-4o-mini-tts",
                voice=voice,
                input=body,
                instructions=f"Speak as the character {speaker}.",
            ) as resp:
                resp.stream_to_file(tmp)
            tmp_files.append(tmp)
        except Exception as e:
            print("TTS failed for", speaker, e)
            raise

    # concatenate with pydub
    combined = AudioSegment.empty()
    for f in tmp_files:
        combined += AudioSegment.from_file(f)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    combined.export(out_path, format="mp3")
    print("Wrote combined:", out_path)

    # cleanup tmp files
    for f in tmp_files:
        try: f.unlink()
        except: pass

# Example usage:
voice_map = {
    "Presenter ": "onyx ",   # deep/authoritative
    "Pisar":   "fable",   # clear/narrator
    "Kmet":    "marin",   # earthy/warm
    "Suženj":  "coral",   # softer/gentle
    "Upnik":   "alloy"    # harsher/firm
}
script = """Presenter: One of the biggest advantages of InsightViewer
is that you can attach HTML documentation —
and even let AI help you write it."""
synth_per_character(script, voice_map, speech_file_path)
