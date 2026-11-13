"""Create an emotional English narration with an Indian English male voice and original sad music.

Run:
  uv add edge-tts numpy soundfile pydub
  # Install FFmpeg separately and make sure it is on PATH.
  uv run python scripts/create_itachi_audio.py
"""
import asyncio
from pathlib import Path

import edge_tts
import numpy as np
import soundfile as sf
from pydub import AudioSegment

TEXT = """Some things we carry don't always show on the outside.
People think strength is loud, but sometimes strength is just staying quiet,
stopping yourself from destroying something when you're angry.
It's choosing patience when impatience feels easier.

People chase recognition. They want applause, they want their names said in the open.
But life asks us for different kinds of courage, including the courage to be unseen.

Sometimes love looks like protecting people from the truth,
because they're not ready, and because you still hope they'll grow.

The cost of that choice is heavy, but the motive matters.
People argue about what's right and what's wrong, like it's a clean line.
But most of the time, it's messy, and you just choose the option that hurts less.

You're still allowed to move forward. You're allowed to learn,
make mistakes, and keep going."""

VOICE = "en-IN-PrabhatNeural"
RATE = "-8%"
PITCH = "-3Hz"
ROOT = Path(__file__).resolve().parent.parent
VOICE_FILE = ROOT / "itachi_narration.mp3"
MUSIC_FILE = ROOT / "itachi_sad_music.wav"
OUTPUT_FILE = ROOT / "itachi_english_emotional.mp3"
SAMPLE_RATE = 44100


async def create_voice():
    tts = edge_tts.Communicate(TEXT, VOICE, rate=RATE, pitch=PITCH)
    await tts.save(str(VOICE_FILE))


def create_music(duration_seconds):
    """Synthesize a simple original minor-key ambient score in Python."""
    count = max(1, int(SAMPLE_RATE * duration_seconds))
    time = np.arange(count, dtype=np.float64) / SAMPLE_RATE
    music = np.zeros(count, dtype=np.float64)
    progression = [
        (110.00, 130.81, 164.81),  # A minor
        (87.31, 110.00, 130.81),   # F
        (130.81, 164.81, 196.00),  # C
        (98.00, 123.47, 146.83),   # G
    ]
    segment = max(duration_seconds / len(progression), 0.1)
    for index, chord in enumerate(progression):
        start = int(index * segment * SAMPLE_RATE)
        end = min(int((index + 1) * segment * SAMPLE_RATE), count)
        if end <= start:
            continue
        local = time[start:end] - time[start]
        for note_index, frequency in enumerate(chord):
            amplitude = 0.035 / (note_index + 1)
            music[start:end] += amplitude * np.sin(2 * np.pi * frequency * local)
            music[start:end] += amplitude * 0.12 * np.sin(
                2 * np.pi * frequency * 2 * local
            )
    fade = min(3 * SAMPLE_RATE, count // 2)
    if fade:
        music[:fade] *= np.linspace(0, 1, fade)
        music[-fade:] *= np.linspace(1, 0, fade)
    peak = np.max(np.abs(music))
    if peak:
        music = music / peak * 0.20
    sf.write(MUSIC_FILE, music.astype(np.float32), SAMPLE_RATE)


async def main():
    await create_voice()
    narration = AudioSegment.from_file(VOICE_FILE)
    create_music(len(narration) / 1000)
    music = AudioSegment.from_file(MUSIC_FILE) - 24
    if len(music) < len(narration):
        music *= len(narration) // max(len(music), 1) + 1
    music = music[:len(narration)]
    music.overlay(narration).export(OUTPUT_FILE, format="mp3", bitrate="192k")
    print(f"Created: {OUTPUT_FILE}")


if __name__ == "__main__":
    asyncio.run(main())
