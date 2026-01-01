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
#config_path = os.path.join(os.path.dirname(__file__), "..", "config.ini")
print("config_path:", config_path)
config.read(config_path)

print("config_path:", config_path)

# prefer env var OPENAI_API_KEY, fallback to config.ini [OPENAI].OPENAI_API_KEY
OPENAI_API_KEY = (
    os.environ.get('OPENAI_API_KEY')
    or config.get('OPENAI', 'OPENAI_API_KEY', fallback=None)
)
if not OPENAI_API_KEY:
    raise RuntimeError("OPENAI_API_KEY not set in environment or config.ini")

client = OpenAI(api_key=OPENAI_API_KEY)
# speech_file_path = Path(__file__).parent / "InsightViewer_Test.mp3"

# print("Will write TTS to:", speech_file_path.resolve())

def synth_per_character(script_text: str, voice_map: dict, out_path: Path):
    tmp_files = []
    # split blocks like "Hamurabi: ...\n\nNext:"
    pattern = re.compile(r'^(?P<speaker>[A-Za-zčšžČŠŽ\- ]+):\s*(?P<body>.*?)(?=(?:^[A-Za-zčšžČŠŽ\- ]+:)|\Z)', re.M | re.S)
    for i, m in enumerate(pattern.finditer(script_text)):
        speaker = m.group('speaker').strip()
        body = m.group('body').strip()
        voice = voice_map.get(speaker, "alloy")  # default if not mapped
        tmp = Path(f"{speech_file_path.parent}/tmp_{i}_{speaker.replace(' ','_')}.mp3")
        print("Synthesizing", speaker, "->", tmp, "voice:", voice)
        try:
            with client.audio.speech.with_streaming_response.create(
                model="gpt-4o-mini-tts",
                voice=voice,
                input=body,
                instructions=(
                    f"Speak as the character {speaker}. "
                    "Use a calm, deep, slow, warm tone. "
                    "Neutral emotion, steady pacing. "
                    "Short pauses between sentences."
                    "When you find [pause] dont read it aloud, just pause briefly. "
                    "When you find [long pause] dont read it aloud, just pause. "
                ),
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
    "Presenter ": "alloy ",   # deep/authoritative
    "Pisar":   "fable",   # clear/narrator
    "Kmet":    "marin",   # earthy/warm
    "Suženj":  "coral",   # softer/gentle
    "Upnik":   "alloy"    # harsher/firm
}



script0 = """Presenter: 
Welcome to the Insight Viewer demonstration …
The main idea behind Insight Viewer is to organize your work, documentation and learning. …

In this demo I will show you how to use Insight Viewer to produce and organize
your documents. …

In next step I will show you how to use AI to produce knowledge graph visualisation of documents created in previous step. …

This knowledge graph can be used to feed AI agents to help you analyze and understand your documents better. …

"""

script2 = """Presenter: 
Let's see how easy is to make a meeting brief …
There are prepared templates which will help you create meetings summaries efficently …
Right click on node will open context menu from which you can select "Edit html for power user" …
The dialog box where you can choose template or ask AI for help will open. …
Let's start with prepared template for meetings by clickin Load template button. …
Choose Meetings template from the list and click Load. …
After Html will load into the editor click Save button. …
Close dialog box. …
Right click on node will open context menu from which you can select "Edit html for user". …
The dialog box where you can see and edit document will open. …
You can drag and drop picture. …
You can drag and drop Excel file. In fact if you drag and drop Excel file you will get preview, fast lookup and download. …

"""

script = """Presenter: 
I have created a sample of meeting document. Here it is.
The part of the document we are interested in is at the bottom, so I will scroll down.

Here you can see the tasks assigned to different people.
There is also a “Generate Graph” button, which generates a knowledge graph from the document.

Let’s see what kind of graph is generated.

The program prepares a Cypher query that lists the complete graph.
Cypher is a language developed for graph manipulation in the Neo4j database, which is used by InsightViewer.

At this point, the graph is quite large and complex, so I will focus only on the part related to tasks.

There are two ways to do this.

The first way is to manually modify the Cypher query to select only the nodes and relationships related to tasks.
The second way is to let AI do this for us.

I will use the second approach.
I will ask the AI to modify the Cypher query so that it selects only the people and relationships related to tasks.
"""

scriptEnd = """Presenter: Pillars important for every project …
especially AI projects …
are the following.

First pillar.
The project must solve a real problem from end user point of view.

People are more willing to cooperate …
when a project helps them solve real, everyday problems.

Therefore …
a project should be clearly focused …
on solving a real and relevant problem for end user.

"""

speech_file_path = Path(__file__).parent / "InsightViewer_generateGraph.mp3"
print("Will write TTS to:", speech_file_path.resolve())

synth_per_character(script, voice_map, speech_file_path)
