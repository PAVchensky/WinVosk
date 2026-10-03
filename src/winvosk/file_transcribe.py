"""Offline transcription of audio and video files.

Used when dictation is not the goal: a recording, a call or a video is fed
through ffmpeg into 16 kHz mono PCM and recognised with the same model.
"""

from __future__ import annotations

import argparse
import json
import logging
import shutil
import subprocess
import sys
import wave
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import vosk

from winvosk import config

log = logging.getLogger(__name__)

CHUNK = 8000


def _ffmpeg() -> str:
    executable = shutil.which("ffmpeg")
    if not executable:
        raise FileNotFoundError(
            "ffmpeg was not found in PATH. Install it or pass a 16 kHz mono wav."
        )
    return executable


def convert(source: Path, target: Path) -> Path:
    target.parent.mkdir(parents=True, exist_ok=True)
    command = [
        _ffmpeg(), "-hide_banner", "-loglevel", "error", "-y",
        "-i", str(source),
        "-ac", "1", "-ar", str(config.SAMPLE_RATE), "-acodec", "pcm_s16le",
        str(target),
    ]
    log.info("converting: %s", " ".join(command))
    subprocess.run(command, check=True, capture_output=True)
    return target


def transcribe_wav(wav_path: Path, model_path: Path, show_words: bool = False) -> str:
    vosk.SetLogLevel(-1)
    model = vosk.Model(str(model_path))
    recognizer = vosk.KaldiRecognizer(model, config.SAMPLE_RATE)
    if show_words:
        recognizer.SetWords(True)
    parts: list[str] = []
    with wave.open(str(wav_path), "rb") as handle:
        if handle.getframerate() != config.SAMPLE_RATE or handle.getnchannels() != 1:
            raise ValueError(
                f"expected {config.SAMPLE_RATE} Hz mono, got "
                f"{handle.getframerate()} Hz and {handle.getnchannels()} channel(s)"
            )
        while True:
            block = handle.readframes(CHUNK)
            if not block:
                break
            if recognizer.AcceptWaveform(block):
                text = json.loads(recognizer.Result()).get("text", "")
                if text:
                    parts.append(text)
    tail = json.loads(recognizer.FinalResult()).get("text", "")
    if tail:
        parts.append(tail)
    return " ".join(parts).strip()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="file_transcribe", description="Transcribe a media file to Russian text"
    )
    parser.add_argument("source", nargs="?", type=Path, help="audio or video file")
    parser.add_argument("-o", "--out", type=Path, help="write the text to this file")
    parser.add_argument("-m", "--model", type=Path, help="override the model directory")
    parser.add_argument("--words", action="store_true", help="include word timings")
    parser.add_argument(
        "--self-test", action="store_true",
        help="load the model and feed it one second of silence",
    )
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    model_path = args.model or config.resolve_model()

    if args.self_test:
        silence = config.TMP_DIR / "silence16k.wav"
        with wave.open(str(silence), "wb") as handle:
            handle.setnchannels(1)
            handle.setsampwidth(2)
            handle.setframerate(config.SAMPLE_RATE)
            handle.writeframes(b"\x00\x00" * config.SAMPLE_RATE)
        text = transcribe_wav(silence, model_path, args.words)
        print(f"model {model_path.name} loaded, silence transcribed as: {text!r}")
        return 0

    if args.source is None:
        parser.error("provide a media file or use --self-test")

    source = args.source.expanduser()
    if not source.is_file():
        print(f"file not found: {source}", file=sys.stderr)
        return 1
    if source.suffix.lower() == ".wav":
        try:
            with wave.open(str(source), "rb") as handle:
                already_ok = (
                    handle.getframerate() == config.SAMPLE_RATE
                    and handle.getnchannels() == 1
                    and handle.getsampwidth() == 2
                )
        except wave.Error:
            already_ok = False
        wav_path = source if already_ok else convert(source, config.TMP_DIR / f"{source.stem}.wav")
    else:
        wav_path = convert(source, config.TMP_DIR / f"{source.stem}.wav")

    text = transcribe_wav(wav_path, model_path, args.words)
    if args.out:
        args.out.write_text(text, encoding="utf-8")
        print(f"written to {args.out} ({len(text)} characters)")
    else:
        print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
