"""Video Assembly Service.

This module handles the final video production:
1. Timeline building - Creates time-ordered segment list
2. Video rendering - Assembles images + audio into MP4
3. Visual effects - Zoom animation with black letterboxing

Uses MoviePy for video manipulation with PIL for image processing.
"""

import math
import os
import subprocess
import tempfile
from pathlib import Path

import numpy as np
from moviepy import (
    AudioFileClip,
    ColorClip,
    CompositeVideoClip,
    ImageClip,
    concatenate_videoclips,
)
from PIL import Image

from core.models import create_timeline_item


CONFIG = {
    "resolution": (1280, 720),
    "fps": 15,
    "transition_seconds": 0.3,
    "zoom_strength": 0.3,
    "background_music_path": Path(__file__).parent / "background.mp3",
    "music_volume": 0.5,
    "music_fade_duration": 2.0,
}


def zoom_in_effect(clip, zoom_ratio=CONFIG["zoom_strength"]):
    """Apply smooth zoom-in effect using PIL for high-quality resizing.

    Creates a Ken Burns effect by slowly zooming into the image over time.
    Uses PIL for high-quality Lanczos resizing.

    Args:
        clip: MoviePy video clip
        zoom_ratio: Total zoom amount across the clip (0.08 = 8% total zoom)

    Returns:
        Transformed clip with zoom effect
    """

    clip_duration = float(clip.duration or 0.0)

    def effect(get_frame, t):
        return _apply_zoom_frame(get_frame(t), zoom_ratio, t, clip_duration)

    return clip.transform(effect)


def _apply_zoom_frame(frame, zoom_ratio, time_seconds, clip_duration):
    """Apply zoom transformation to a single video frame.

    This is the inner function that does the actual zoom processing:
    1. Convert frame to PIL Image
    2. Calculate zoomed size based on time
    3. Resize up (zoom in)
    4. Crop to original size (pan center)
    5. Resize back down to maintain frame size
    6. Convert back to numpy array

    Args:
        frame: Video frame as numpy array
        zoom_ratio: Total zoom amount across the clip
        time_seconds: Current time in video
        clip_duration: Total clip duration in seconds

    Returns:
        Transformed frame as numpy array
    """
    img = Image.fromarray(frame)
    base_size = img.size

    # Normalize zoom over full clip duration so long segments do not explode in size.
    # Example: zoom_ratio=0.08 means 8% total zoom from start to end of clip.
    duration = max(clip_duration, 0.001)
    progress = min(max(time_seconds / duration, 0.0), 1.0)
    scale = 1.0 + (zoom_ratio * progress)

    # Calculate new size with zoom
    new_size = [
        math.ceil(img.size[0] * scale),
        math.ceil(img.size[1] * scale),
    ]

    # Ensure even dimensions for video codec compatibility
    new_size[0] = new_size[0] + (new_size[0] % 2)
    new_size[1] = new_size[1] + (new_size[1] % 2)

    # High-quality resize up (zoom in)
    img = img.resize(new_size, Image.Resampling.LANCZOS)

    # Crop back to original size (center crop for zoom effect)
    x = math.ceil((new_size[0] - base_size[0]) / 2)
    y = math.ceil((new_size[1] - base_size[1]) / 2)
    img = img.crop((x, y, new_size[0] - x, new_size[1] - y)).resize(
        base_size, Image.Resampling.LANCZOS
    )

    result = np.array(img)
    img.close()

    return result


def build_timeline(segments):
    """Build a timeline from script segments.

    Converts segments with images and audio into a time-ordered list
    with precise timing. Duration is determined by audio file length.

    Args:
        segments: List of segment dicts with image and audio paths

    Returns:
        List of timeline item dicts with timing info

    Raises:
        RuntimeError: If audio file cannot be loaded
    """
    print(f"[TIMELINE] Building timeline from {len(segments)} segments", flush=True)
    timeline = []
    cursor = 0.0  # Current timestamp

    for segment in segments:
        selected_image = segment.get("selected_image_path")
        narration_audio = segment.get("narration_audio_path")

        # Skip segments missing required files
        if selected_image is None or narration_audio is None:
            print(
                f"[TIMELINE] Segment {segment['segment_id']}: missing image/audio, skipped",
                flush=True,
            )
            continue

        if not selected_image.exists() or not narration_audio.exists():
            print(
                f"[TIMELINE] Segment {segment['segment_id']}: missing files on disk, skipped",
                flush=True,
            )
            continue

        # Get duration from audio file
        try:
            audio_clip = AudioFileClip(str(narration_audio))
            try:
                duration = float(audio_clip.duration)
            finally:
                audio_clip.close()
        except Exception as e:
            raise RuntimeError(f"Failed to load audio file: {narration_audio}: {e}")

        segment["duration_seconds"] = duration
        timeline.append(
            create_timeline_item(
                segment_id=segment["segment_id"],
                text=segment["text"],
                start_seconds=cursor,
                end_seconds=cursor + duration,
                duration_seconds=duration,
                image_path=selected_image,
                audio_path=narration_audio,
            )
        )
        cursor += duration
        print(
            f"[TIMELINE] Segment {segment['segment_id']}: duration={duration:.2f}s start={timeline[-1]['start_seconds']:.2f}s",
            flush=True,
        )
    print(f"[TIMELINE] Timeline ready with {len(timeline)} items", flush=True)
    return timeline


def assemble_video(
    timeline,
    output_path,
    resolution=CONFIG["resolution"],
    fps=CONFIG["fps"],
    transition_seconds=CONFIG["transition_seconds"],
    zoom_strength=CONFIG["zoom_strength"],
):
    """Assemble final video from timeline items.

    For each timeline item:
    1. Create black background
    2. Create foreground image (centered, zoom effect)
    3. Composite with audio
    4. Concatenate all clips

    Args:
        timeline: List of timeline item dicts
        output_path: Output MP4 file path
        resolution: Video resolution (width, height)
        fps: Frames per second
        transition_seconds: Overlap between clips
        zoom_strength: Zoom effect intensity (0 to disable)

    Returns:
        Path to generated video file
    """
    if not timeline:
        raise ValueError("Timeline is empty; cannot assemble video.")

    print(
        f"[VIDEO] Rendering video with {len(timeline)} clips -> {output_path}",
        flush=True,
    )

    clips = []
    try:
        for item in timeline:
            print(
                f"[VIDEO] Building clip for segment {item['segment_id']} ({item['duration_seconds']:.2f}s)",
                flush=True,
            )
            clip = _build_segment_clip(
                item,
                resolution=resolution,
                fps=fps,
                zoom_strength=zoom_strength,
            )
            clips.append(clip)

        # Concatenate with small negative padding for smooth transitions
        final_clip = concatenate_videoclips(
            clips,
            method="compose",
            padding=-transition_seconds,
        )

        final_duration = final_clip.duration

        # Write video-only (no audio) to avoid moviepy pipe deadlocks
        video_only_path = str(output_path) + ".video_only.mp4"
        print(f"[VIDEO] Rendering video frames", flush=True)
        final_clip.write_videofile(
            video_only_path,
            fps=fps,
            codec="libx264",
            audio=False,
            logger="bar",
        )

        # Write narration audio to a separate file
        narration_audio_path = str(output_path) + ".narration.wav"
        print(f"[VIDEO] Extracting narration audio", flush=True)
        final_clip.audio.write_audiofile(narration_audio_path, logger=None)

        final_clip.close()
        for clip in clips:
            clip.close()
        clips.clear()

        # Use ffmpeg to combine video + narration + background music
        background_music_path = CONFIG["background_music_path"]
        print(f"[VIDEO] Muxing audio with ffmpeg", flush=True)
        _mux_audio(
            video_only_path, narration_audio_path, background_music_path,
            str(output_path), final_duration, CONFIG["music_volume"],
            CONFIG["music_fade_duration"],
        )

        # Cleanup temp files
        for p in [video_only_path, narration_audio_path]:
            if os.path.exists(p):
                os.remove(p)

        print(f"[VIDEO] Render complete: {output_path}", flush=True)
    finally:
        for clip in clips:
            clip.close()

    return output_path


def _mux_audio(
    video_path, narration_path, music_path, output_path, duration, volume, fade_duration
):
    """Combine video + narration + background music using ffmpeg CLI.

    Avoids all moviepy audio pipe deadlocks by doing audio mixing in ffmpeg.
    """
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
        mixed_audio = tmp.name

    try:
        narration_exists = os.path.exists(narration_path) and os.path.getsize(narration_path) > 0
        music_exists = os.path.exists(music_path) and os.path.getsize(music_path) > 0

        if narration_exists and music_exists:
            # Trim + fade background music
            fade_out_start = max(0, duration - fade_duration)
            cmd_bg = [
                "ffmpeg", "-y", "-loglevel", "error",
                "-i", str(music_path),
                "-t", f"{duration:.3f}",
                "-af", (
                    f"volume={volume},"
                    f"afade=t=in:st=0:d={fade_duration:.3f},"
                    f"afade=t=out:st={fade_out_start:.3f}:d={fade_duration:.3f}"
                ),
                "-ar", "44100", "-ac", "2",
                mixed_audio,
            ]
            subprocess.run(cmd_bg, check=True, capture_output=True)

            # Mix narration + bg music
            cmd_mix = [
                "ffmpeg", "-y", "-loglevel", "error",
                "-i", narration_path,
                "-i", mixed_audio,
                "-filter_complex",
                "[0:a][1:a]amix=inputs=2:duration=first:dropout_transition=2[out]",
                "-map", "[out]",
                "-ar", "44100", "-ac", "2",
                mixed_audio + ".final.wav",
            ]
            subprocess.run(cmd_mix, check=True, capture_output=True)
            final_audio = mixed_audio + ".final.wav"
        elif narration_exists:
            final_audio = narration_path
        else:
            print("[VIDEO] Warning: no audio found, creating silent track", flush=True)
            cmd_silent = [
                "ffmpeg", "-y", "-loglevel", "error",
                "-f", "lavfi", "-i", f"anullsrc=r=44100:cl=stereo",
                "-t", f"{duration:.3f}",
                mixed_audio,
            ]
            subprocess.run(cmd_silent, check=True, capture_output=True)
            final_audio = mixed_audio

        # Mux video + combined audio
        cmd_mux = [
            "ffmpeg", "-y", "-loglevel", "error",
            "-i", video_path,
            "-i", final_audio,
            "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
            "-shortest",
            str(output_path),
        ]
        subprocess.run(cmd_mux, check=True, capture_output=True)
        print(f"[VIDEO] Audio muxed successfully", flush=True)
    finally:
        for f in [mixed_audio, mixed_audio + ".final.wav"]:
            if os.path.exists(f):
                os.remove(f)


def _build_segment_clip(
    item,
    resolution,
    fps,
    zoom_strength,
):
    """Build a single segment video clip.

    Creates a composited clip with:
    - Black background (letterboxing)
    - Foreground image (centered, with zoom effect)
    - Audio track

    Args:
        item: Timeline item dict
        resolution: Video resolution
        fps: Frames per second
        zoom_strength: Zoom intensity

    Returns:
        MoviePy CompositeVideoClip
    """
    width, height = resolution
    duration = max(0.1, item["duration_seconds"])

    # Create black background
    background = ColorClip(size=resolution, color=(0, 0, 0)).with_duration(duration)

    # Create foreground image
    foreground = (
        ImageClip(str(item["image_path"])).with_duration(duration).with_fps(fps)
    )
    # Fit image to frame (letterbox if needed)
    foreground = foreground.resized(height=height)
    if foreground.w > width:
        foreground = foreground.resized(width=width)

    # Apply zoom effect
    if zoom_strength > 0:
        foreground = zoom_in_effect(foreground, zoom_ratio=zoom_strength)

    foreground = foreground.with_position(("center", "center"))

    # Composite and add audio
    clips = [background, foreground]
    composite = CompositeVideoClip(clips, size=resolution).with_duration(duration)
    audio_clip = AudioFileClip(str(item["audio_path"]))
    composite = composite.with_audio(audio_clip)
    return composite
