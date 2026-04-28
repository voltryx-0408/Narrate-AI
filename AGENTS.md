# AGENTS.md — Narrate-AI

## What this is

Documentary video generator: takes a topic, researches it via web crawling + RAG, writes a script, generates TTS audio, finds/ranks images, assembles a narrated slideshow video. Two entrypoints: CLI (`main.py`) and Streamlit web UI (`app.py`).

## Quick commands

```bash
uv sync                          # install deps (ALWAYS use uv, never pip)
uv run main.py "Topic"           # CLI run
uv run main.py "Topic" --tts-provider edge_tts --max-websites 6
uv run streamlit run app.py      # web UI
```

## Non-obvious gotchas

- **Python 3.13 required** (`.python-version` + `pyproject.toml`). `Any | None` union syntax used throughout.
- **`core/` has no `__init__.py`** — imports work as `from core.pipeline import ...` directly. Do not add one.
- **`agents/__init__.py` re-exports services** — `from agents import retrieve_images` works but the function lives in `services/`. Prefer importing from the source module.
- **`core/models.py` has duplicate function definitions** — `create_research_note`, `create_image_candidate`, `create_script_segment`, `create_timeline_item` are each defined twice. Later definitions shadow earlier ones. This is a known issue; don't duplicate further.
- **`MultiLayerCache` is copy-pasted** identically in `core/pipeline.py`, `services/image_retrieval.py`, `services/research_crawler.py`. Do not "fix" this without understanding the circular import it avoids.
- **`app.py` is the Streamlit entry point**, not `streamlit_app.py` (README is outdated on this).
- **Dead code** in `services/video_assembly.py` after a `return` (~line 342). Do not "fix" without understanding why it's there.

## Architecture

```
main.py          CLI entry → loads .env, builds config, calls run_pipeline()
app.py           Streamlit UI → spawns main.py as subprocess, parses stdout
core/pipeline.py Pipeline orchestration (run_pipeline is the main function)
core/models.py   Pydantic models + dict factory functions
agents/          LLM agents (narrative, queries, script, segmentation)
services/        Domain services (audio, video, image, RAG, crawl)
```

Pipeline order: narrative plan → source discovery → crawl → RAG index → query gen → retrieve notes → script writing → image segmentation → image retrieval → image ranking → audio synthesis → video assembly.

## API keys (.env)

| Key | Required? | Fallback |
|-----|-----------|----------|
| `GROQ_API_KEY` | Yes | None |
| `SERPER_API_KEY` | Yes | None (raises) |
| `ELEVENLABS_API_KEY` | No | Edge TTS (free) |
| `PINECONE_API` | No | Uses raw notes directly |

## Video output specs

1280x720 @ 15fps, libx264+AAC, Ken Burns zoom (0.3 ratio), 0.3s clip overlap, background music from `services/background.mp3` at 50% volume.

## What does NOT exist

- No tests (CODE_GUIDE.md claims pytest but no test files exist)
- No linter/formatter config (`.ruff_cache` in `.gitignore` but no ruff config)
- No CI/CD workflows
- No pre-commit hooks

## Dependencies

Managed via `uv` + `pyproject.toml` + `uv.lock`. Key libs: crawl4ai, edge-tts, elevenlabs, groq, moviepy, open-clip-torch, pinecone, streamlit, torch.

## Async quirk

`crawl4ai` and `edge-tts` both call `asyncio.run()` internally. Do not call them from within an existing async context.
