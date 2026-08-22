"""Local speech-to-text. Audio never leaves the machine.

Backend order:
  mlx-whisper      Apple Silicon, fastest
  faster-whisper   CPU/CUDA, everywhere else

Both write `<out>/<stem>.json` in the shape the rest of the package expects:
`{"text": str, "segments": [{"start": float, "end": float, "text": str}, ...]}`
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

DEFAULT_MLX_MODEL = "mlx-community/whisper-large-v3-turbo"
DEFAULT_CT2_MODEL = "large-v3"


class TranscriptionError(RuntimeError):
    pass


def available_backend() -> str:
    if shutil.which("mlx_whisper"):
        return "mlx"
    try:
        import faster_whisper  # noqa: F401

        return "faster"
    except ImportError:
        return "none"


def _run_mlx(audio: Path, out_dir: Path, model: str, language: str) -> Path:
    cmd = [
        "mlx_whisper", str(audio),
        "--model", model,
        "--language", language,
        # Whisper loves to hallucinate repeated text on long files; these two
        # options are what stopped it in practice.
        "--condition-on-previous-text", "False",
        "--compression-ratio-threshold", "2.0",
        "--word-timestamps", "True",
        "--output-dir", str(out_dir),
        "--output-format", "json",
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise TranscriptionError(f"mlx_whisper failed:\n{proc.stderr[-2000:]}")
    produced = out_dir / f"{audio.stem}.json"
    if not produced.exists():
        raise TranscriptionError(f"mlx_whisper produced no JSON at {produced}")
    return produced


def _run_faster(audio: Path, out_dir: Path, model: str, language: str) -> Path:
    from faster_whisper import WhisperModel

    whisper = WhisperModel(model, compute_type="auto")
    segments, _info = whisper.transcribe(
        str(audio),
        language=language,
        condition_on_previous_text=False,
        compression_ratio_threshold=2.0,
        word_timestamps=True,
    )
    seg_list = [
        {"start": float(s.start), "end": float(s.end), "text": s.text}
        for s in segments
    ]
    payload = {
        "text": " ".join(s["text"].strip() for s in seg_list),
        "segments": seg_list,
    }
    produced = out_dir / f"{audio.stem}.json"
    produced.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
    return produced


def transcribe(
    audio_path: str | Path,
    out_dir: str | Path,
    *,
    backend: str = "auto",
    model: str | None = None,
    language: str = "en",
) -> Path:
    audio = Path(audio_path).expanduser().resolve()
    if not audio.exists():
        raise FileNotFoundError(audio)
    out = Path(out_dir).expanduser().resolve()
    out.mkdir(parents=True, exist_ok=True)

    chosen = available_backend() if backend == "auto" else backend
    if chosen == "mlx":
        return _run_mlx(audio, out, model or DEFAULT_MLX_MODEL, language)
    if chosen == "faster":
        return _run_faster(audio, out, model or DEFAULT_CT2_MODEL, language)
    raise TranscriptionError(
        "No local speech-to-text backend found.\n"
        "  Apple Silicon : pip install 'opic-rater[mlx]'\n"
        "  everything else: pip install 'opic-rater[cpu]'"
    )
