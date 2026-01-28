from pathlib import Path
from app.routes.open_tts import OpenAITTS 
from dotenv import load_dotenv

load_dotenv()

def main():
    tts = OpenAITTS()                          # uses OPENAI_API_KEY from config.env
    out = Path("example_output.mp3")
    tts.synth("Pozdravljeni iz testne sinteze.", voice="alloy", out_path=out)
    print("Wrote:", out.resolve())

if __name__ == "__main__":
    main()
