# Narrate-AI Code Guide

This guide explains how the Narrate-AI codebase works, its architecture, and how to understand the code.

## Overview

Narrate-AI is a documentary video generator that takes a topic and produces a narrated slideshow video. It uses AI agents for research, script writing, and image selection, combined with various services for web search, vector storage, text-to-speech, and video assembly.

## Architecture

The project follows a pipeline architecture with specialized agents and services:

```
Entry Points
    │
    ├── main.py (CLI)
    └── app.py (Streamlit Web UI)
            │
            ▼
    ┌─────────────────────────────────────────────────────┐
    │                   core/pipeline.py                   │
    │         Orchestrates the documentary pipeline        │
    └─────────────────────────────────────────────────────┘
            │
            ▼
    ┌─────────────────────────────────────────────────────┐
    │                      Agents                          │
    │  (AI-powered decision making using Groq LLM)        │
    ├─────────────────────────────────────────────────────┤
    │  narrative_architect.py  → Creates documentary plan │
    │  query_generator.py     → Generates search queries │
    │  script_writer.py       → Writes narration script  │
    │  image_segmentation.py  → Determines image zones    │
    └─────────────────────────────────────────────────────┘
            │
            ▼
    ┌─────────────────────────────────────────────────────┐
    │                     Services                        │
    │            (Domain-specific utilities)             │
    ├─────────────────────────────────────────────────────┤
    │  research_crawler.py  → Web crawling & discovery    │
    │  rag_manager.py       → Vector DB & semantic search │
    │  image_retrieval.py   → Image search & download     │
    │  image_ranking.py     → CLIP-based image ranking    │
    │  image_placement.py   → Script segmentation         │
    │  audio_generator.py   → TTS synthesis               │
    │  video_assembly.py    → Video rendering             │
    └─────────────────────────────────────────────────────┘
```

## Pipeline Flow

The documentary generation happens in 4 phases:

### Phase 1: Research & Context Building

1. **Narrative Architect** (`agents/narrative_architect.py`)
   - Analyzes the topic using Groq LLM
   - Creates a structured documentary outline with sections
   - Determines tone, pacing, and target duration

2. **Source Discovery** (`services/research_crawler.py`)
   - Uses Serper.dev (Google Search) to find web sources
   - Prioritizes authoritative sources (.edu, .gov, Wikipedia, etc.)
   - Returns ranked list of URLs

3. **Content Crawling** (`services/research_crawler.py`)
   - Crawls each discovered website using crawl4ai
   - Extracts main content and chunks it into 500-word segments
   - Creates research notes with source attribution

4. **RAG Indexing** (`services/rag_manager.py`)
   - Converts text chunks into vector embeddings (MiniLM-L12-v2)
   - Stores embeddings in Pinecone vector database
   - Enables semantic similarity search

5. **Query Generation** (`agents/query_generator.py`)
   - For each section of the outline, generates semantic search queries
   - These queries retrieve relevant context from the vector DB

6. **Semantic Retrieval** (`services/rag_manager.py`)
   - Searches Pinecone using generated queries
   - Retrieves most relevant text chunks for each section

### Phase 2: Content Generation

7. **Script Writer** (`agents/script_writer.py`)
   - Uses retrieved research notes + LLM knowledge
   - Generates spoken narration script in documentary style
   - Written for audio narration (spoken language, not formal)

8. **Image Segmentation** (`agents/image_segmentation.py`)
   - Analyzes script to find natural breakpoints for image changes
   - Considers topic shifts, location changes, time periods
   - Creates image zones (start/end sentence numbers)

9. **Visual Intelligence** (integrated into image services)
   - For each segment, generates optimized search queries
   - Creates CLIP-ready descriptions of ideal images

### Phase 3: Image Retrieval

10. **Image Retrieval** (`services/image_retrieval.py`)
    - Searches Google Images via Serper.dev
    - Downloads candidate images in parallel
    - Uses caching to avoid redundant downloads

10.5. **Aspect Ratio Filtering** (`services/image_retrieval.py`)
    - Filters out portrait and square images
    - Keeps only landscape images (aspect ratio >= 4:3)
    - Ensures images fit the 1280x720 video frame

11. **Image Ranking** (`services/image_ranking.py`)
    - Evaluates candidates using OpenCLIP vision-language model
    - Compares images against segment descriptions
    - Combines CLIP similarity with image quality metrics
    - Selects best image for each segment

### Phase 4: Production

12. **Narration** (`services/audio_generator.py`)
    - Synthesizes audio from script segments
    - Supports ElevenLabs (premium) or Edge TTS (free)
    - Generates WAV audio files

13. **Timeline + Assembly** (`services/video_assembly.py`)
    - Combines image, audio, and timing info
    - Calculates durations from audio file lengths
    - Renders final MP4 at 1280x720, 15fps
    - Applies Ken Burns zoom effects to images
    - Uses ffmpeg for audio mixing (narration + background music)

## Understanding Key Files

### core/pipeline.py

The main orchestration file. `run_pipeline()` executes all steps in sequence:
1. Create run directory
2. Build narrative plan
3. Discover and crawl sources
4. Index to Pinecone
5. Generate queries and retrieve notes
6. Write script
7. Segment for images
8. Retrieve images
9. Filter images by aspect ratio
10. Rank images
11. Synthesize audio
12. Build timeline
13. Assemble video
14. Save manifest

### core/models.py

Defines data structures:
- Pydantic models for LLM response validation (NarrativePlan, ImageSegmentation, etc.)

### agents/*.py

Each agent defines its own `extract_json()` helper and uses Groq LLM with specific prompts:

- **narrative_architect**: Creates documentary structure (sections, objectives, durations)
- **query_generator**: Generates semantic search queries for RAG
- **script_writer**: Writes narration script from plan + context
- **image_segmentation**: Determines where images should change in script

### services/research_crawler.py

Web research pipeline:
- `discover_sources()` - Search for authoritative URLs
- `crawl_and_build_notes()` - Extract content and chunk it

### services/rag_manager.py

Vector database operations using Pinecone:
- `PineconeManager` class - Handles index creation, upserts, queries
- Falls back to direct note use if Pinecone unavailable

### services/image_retrieval.py

Image search and download:
- `retrieve_images()` - Main function for segment images
- `filter_images_by_aspect_ratio()` - Rejects portrait/square images
- `_search_images_with_client()` - Serper.dev image search API
- Uses ThreadPoolExecutor for parallel downloads

### services/image_ranking.py

CLIP-based image selection:
- `create_ranking_state()` - Initializes OpenCLIP model
- `rank_images()` - Main ranking function

### services/audio_generator.py

Text-to-speech with multiple providers:
- Supports ElevenLabs (premium) and Edge TTS (free)
- Provider selected via config

### services/video_assembly.py

Video assembly:
- `build_timeline()` - Creates timeline from segments
- `assemble_video()` - Renders final MP4
- `_mux_audio()` - Combines narration + background music via ffmpeg
- `_build_segment_clip()` - Creates single segment video with zoom effect

## Data Flow

```
Topic String
    │
    ▼
NarrativePlan (sections, objectives, tone, pacing)
    │
    ▼
[Research] → Sources List → Research Notes → Pinecone Vectors
    │
    ▼
[Queries] → Semantic Search → Retrieved Notes
    │
    ▼
Script (narrative text)
    │
    ▼
ImageSegmentation (zones with sentence ranges)
    │
    ▼
ScriptSegments (text + zone info)
    │
    ├──→ [Image Retrieval] → Candidate Images
    │                              │
    │                              ▼
    │                     Aspect Ratio Filter
    │                              │
    │                              ▼
    │                         Ranked Images
    │                              │
    │                              ▼
    │                         Selected Image
    │
    └──→ [TTS] → Audio Files
                    │
                    ▼
            Timeline Items
            (image + audio + duration)
                    │
                    ▼
            Final Video MP4
```

## Key Design Patterns

### 1. Agent Pattern

Each agent follows a similar structure:
1. Takes context (LLM client + config) + input data
2. Constructs prompt with instructions
3. Calls Groq API
4. Parses JSON response (each agent has its own `extract_json()`)
5. Returns structured data (Pydantic models)

### 2. Service Layer

Services are domain-specific utilities that agents use:
- Stateless functions where possible
- Configuration passed as dict
- Clear input/output contracts
- Caching at appropriate levels

### 3. Multi-Layer Cache

`MultiLayerCache` (defined in `core/pipeline.py`, also in `services/image_retrieval.py` and `services/research_crawler.py`) provides:
- Fast memory lookup for recent operations
- Persistent disk cache for expensive operations
- Namespace isolation (research, crawl, images, etc.)
- SHA256 key hashing

### 4. Pipeline Pattern

`core/pipeline.py` orchestrates:
- Sequential execution of phases
- Clear logging at each step
- Error handling with descriptive messages
- Output files at each stage for debugging

## Common Operations

### Adding a New Agent

1. Create `agents/your_agent.py`
2. Define an `extract_json()` helper for parsing LLM output
3. Define Pydantic model in `core/models.py` if needed
4. Export from `agents/__init__.py`
5. Add to pipeline in `core/pipeline.py`

### Debugging Pipeline Issues

Check intermediate outputs in `runs/<timestamp>-<topic>/`:
- `script.txt` - Generated script
- `narrative_plan.json` - Documentary structure
- `sources.json` - Research sources
- `notes.json` - Raw research notes
- `retrieved_notes.json` - RAG-retrieved context
- `timeline.json` - Final timeline
- `manifest.json` - Complete metadata

## Configuration

Configuration is managed through:
1. Environment variables (loaded from `.env`)
2. CLI arguments (for main.py) or UI inputs (for app.py)

Key settings:
- `run_root` - Output directory
- `max_websites` - Sources to crawl
- `max_queries_per_segment` - Image searches per segment
- `sentence_span_per_segment` - Sentences per video clip
- `tts_provider` - "elevenlabs" or "edge_tts"
- `background_mode` - "black" or "blur"

## Dependencies

Managed via `uv` + `pyproject.toml`. Key libraries:
- **crawl4ai** - Async web crawling
- **groq** - LLM API client
- **moviepy** - Video editing
- **open-clip-torch** - Vision-language model for image ranking
- **pinecone** - Vector database
- **sentence-transformers** - Local embeddings
- **edge-tts** / **elevenlabs** - Text-to-speech

## Performance Considerations

- **Caching**: Web searches and crawled pages are cached via `MultiLayerCache`
- **Parallel Downloads**: Image retrieval uses ThreadPoolExecutor
- **GPU Acceleration**: CLIP ranking uses CUDA if available
- **Model Choices**: Groq for fast LLM, MiniLM for quick embeddings
- **Async Crawling**: crawl4ai uses asyncio for web crawling
