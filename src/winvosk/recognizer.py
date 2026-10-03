"""Streaming microphone recognition engine built on vosk."""

from __future__ import annotations

import json
import logging
import queue
import threading
import time
from array import array
from collections import deque
from pathlib import Path

import sounddevice as sd
import vosk

from . import text

log = logging.getLogger(__name__)

_START = object()
_STOP = object()
_SHUTDOWN = object()
# Asked for through the same queue as the audio, so the check runs on this thread
# against the model that is already loaded and never blocks the Tk thread.
_CHECK = object()

# Levels for the recording chip. PortAudio hands over the whole block at once,
# every BLOCK_SIZE / SAMPLE_RATE seconds, which is 500 ms and far too coarse to
# drive an animation from. The block is therefore measured in sub-frames, one
# every 31 ms, and those are buffered for the Tk thread to consume.
LEVEL_POINTS = 16
LEVEL_HISTORY = 64
_INT16_PEAK = 32767


def levels_from_block(indata, points: int = LEVEL_POINTS) -> list[float]:
    """One normalised 0.0-1.0 peak per sub-frame of a raw int16 mono block.

    The block is split into `points` roughly equal slices and the loudest
    sample of each slice becomes that slice's level, so a bar driven from the
    result moves smoothly instead of jumping twice a second. The peak of a
    slice is taken with min()/max() over an array slice, not by walking the
    samples in Python: this runs on the PortAudio real time thread, where a
    slow callback costs dropouts and clicks in the dictated audio.

    Pure on purpose. It reads no instance state and touches no model, no
    microphone and no window, so the logic can be proved headlessly.
    """
    if points < 1:
        return []
    samples = array("h")
    try:
        samples.frombytes(bytes(indata))
    except (TypeError, ValueError, BufferError):
        return [0.0] * points
    total = len(samples)
    if not total:
        return [0.0] * points
    levels: list[float] = []
    start = 0
    for index in range(points):
        stop = ((index + 1) * total) // points
        chunk = samples[start:stop]
        start = stop
        if not chunk:
            levels.append(0.0)
            continue
        peak = max(max(chunk), -min(chunk))
        levels.append(peak / _INT16_PEAK if peak < _INT16_PEAK else 1.0)
    return levels


def input_device(preferred: int | None = None) -> int | None:
    """The device index to record from, or None to leave it to PortAudio.

    An explicit `preferred` is never overridden. Otherwise PortAudio's own
    default is only trusted when it names a device: on this machine
    `Pa_GetDefaultInputDevice()` answers `paNoDevice`, because MME, DirectSound
    and WASAPI all report no default input and only WDM-KS names one — so
    `device=None` raises `Error querying device -1` and the stream never opens.
    The host API default is used, and the first device that can record is the
    fallback. Devices come and go with whatever Windows does to the sound
    mapper, so this is asked again on every start rather than cached.
    """
    if preferred is not None:
        return preferred
    try:
        for hostapi in sd.query_hostapis():
            device = hostapi["default_input_device"]
            if device >= 0:
                log.info("input device %d, the %s default", device, hostapi["name"])
                return device
        for index, device in enumerate(sd.query_devices()):
            if device["max_input_channels"] > 0:
                log.info("input device %d, no host API names a default", index)
                return index
    except sd.PortAudioError:
        log.warning("could not resolve an input device", exc_info=True)
    return None


class DictationEngine:
    """Owns the model, the microphone stream and one worker thread.

    Control is pushed into an internal queue so that audio chunks and
    commands are consumed in a single well ordered stream: no locks are
    needed between the PortAudio callback and the caller thread.
    """

    def __init__(
        self,
        model_path: Path,
        events: queue.Queue,
        device: int | None = None,
        sample_rate: int = 16000,
        block_size: int = 8000,
        show_words: bool = False,
        max_seconds: float = 0.0,
    ) -> None:
        self._model_path = Path(model_path)
        self._events = events
        self._device = device
        self._sample_rate = sample_rate
        self._block_size = block_size
        self._show_words = show_words
        self._max_seconds = max_seconds
        self._queue: queue.Queue = queue.Queue()
        self._active = threading.Event()
        self._levels: deque[float] = deque(maxlen=LEVEL_HISTORY)
        self._level_lock = threading.Lock()
        self._model = None
        self._stream = None
        self._thread: threading.Thread | None = None
        self._done = ""
        self._partial = ""
        self._deadline = 0.0

    @property
    def is_active(self) -> bool:
        return self._active.is_set()

    @property
    def is_ready(self) -> bool:
        """Whether the model is loaded, so a query can be put to it at all."""
        return self._model is not None

    def next_level(self) -> float | None:
        """Pop one measured level, or None while the buffer is momentarily empty.

        Called from the Tk thread that paints the chip, never from the audio
        thread. The buffer is deliberately not the events queue: that queue is
        drained in batches by the Tk pump, which 32 levels a second would
        overflow. The lock is the only thing shared with the callback, and it
        is held for a single popleft.
        """
        with self._level_lock:
            if not self._levels:
                return None
            return self._levels.popleft()

    def start_thread(self) -> None:
        self._thread = threading.Thread(
            target=self._run, name="recognizer", daemon=True
        )
        self._thread.start()

    def start(self) -> None:
        if self._active.is_set():
            return
        # Empty the meter before the callback is allowed to fill it again, so
        # the first frames of a session cannot animate from the tail of the
        # previous one.
        with self._level_lock:
            self._levels.clear()
        self._active.set()
        self._queue.put(_START)

    def stop(self) -> None:
        if not self._active.is_set():
            return
        self._active.clear()
        self._queue.put(_STOP)

    def check_phrases(self, phrases: list[str]) -> None:
        """Ask the loaded model which of `phrases` it can hear.

        The work happens on this thread, in the gap between audio blocks, and
        the answer arrives as a `vocab` event like everything else, so the Tk
        thread never waits on a model. Nothing is recorded while it runs, which
        the caller is expected to have arranged.
        """
        self._queue.put((_CHECK, list(phrases)))

    def close(self) -> None:
        self._active.clear()
        self._queue.put(_SHUTDOWN)
        if self._thread is not None:
            self._thread.join(timeout=3.0)

    def _emit(self, **payload) -> None:
        self._events.put(payload)

    def _load(self) -> None:
        vosk.SetLogLevel(-1)
        started = time.perf_counter()
        self._model = vosk.Model(str(self._model_path))
        self._stream = sd.RawInputStream(
            samplerate=self._sample_rate,
            blocksize=self._block_size,
            device=input_device(self._device),
            dtype="int16",
            channels=1,
            callback=self._audio_callback,
        )
        self._stream.start()
        log.info(
            "model %s ready in %.2fs, input device %r",
            self._model_path.name,
            time.perf_counter() - started,
            self._stream.device,
        )
        self._emit(type="ready", model=self._model_path.name, device=self._stream.device)

    def _audio_callback(self, indata, frames, time_info, status) -> None:
        if status:
            log.debug("input status: %s", status)
        if self._active.is_set():
            block = bytes(indata)
            self._queue.put(block)
            # Only while recording: in idle this callback must do no work at
            # all. No Tk call may appear here, the chip is read by the Tk thread.
            with self._level_lock:
                self._levels.extend(levels_from_block(block, LEVEL_POINTS))

    def _drain(self) -> None:
        while True:
            try:
                self._queue.get_nowait()
            except queue.Empty:
                return

    def _extend(self, text: str) -> None:
        if text:
            self._done = f"{self._done} {text}".strip()

    def _begin(self) -> object:
        self._done = ""
        self._partial = ""
        self._drain()
        recognizer = vosk.KaldiRecognizer(self._model, self._sample_rate)
        if self._show_words:
            recognizer.SetWords(True)
        if self._max_seconds:
            self._deadline = time.monotonic() + self._max_seconds
        self._emit(type="state", recording=True, text="", partial="", tail="")
        return recognizer

    def _finish(self, recognizer) -> None:
        self._drain()
        tail = ""
        if recognizer is not None:
            tail = json.loads(recognizer.FinalResult()).get("text", "")
        self._partial = ""
        self._emit(
            type="state", recording=False, text=self._done, partial="", tail=tail,
        )

    def _check(self, phrases: list[str]) -> None:
        """Report which phrases the loaded model knows, never raising."""
        from . import vocabulary

        started = time.perf_counter()
        try:
            known, missing = vocabulary.split_by_model(self._model, phrases)
        except Exception:
            log.exception("the own-word check failed")
            known, missing = [], list(phrases)
        log.info(
            "own-word check: %d known, %d unknown in %.2fs",
            len(known), len(missing), time.perf_counter() - started,
        )
        self._emit(type="vocab", known=known, missing=missing)

    def _run(self) -> None:
        try:
            self._load()
        except Exception as exc:
            # No local may be named `text` anywhere in this function: it would
            # shadow the message module and turn this report into a
            # NameError, which under pythonw.exe is the one failure a user
            # cannot see and cannot report.
            log.exception("engine startup failed")
            self._emit(type="fatal",
                       message=text.t("engine_failed", error=exc))
            return
        recognizer = None
        try:
            while True:
                item = self._queue.get()
                if item is _SHUTDOWN:
                    break
                if item is _START:
                    recognizer = self._begin()
                    continue
                if item is _STOP:
                    self._finish(recognizer)
                    recognizer = None
                    continue
                if isinstance(item, tuple) and item[0] is _CHECK:
                    self._check(item[1])
                    continue
                if recognizer is None:
                    continue
                if self._deadline and time.monotonic() > self._deadline:
                    log.warning(
                        "hit the %.0f s limit, stopping on behalf of the caller",
                        self._max_seconds,
                    )
                    self._active.clear()
                    self._finish(recognizer)
                    recognizer = None
                    continue
                try:
                    accepted = recognizer.AcceptWaveform(item)
                    payload = recognizer.Result() if accepted else recognizer.PartialResult()
                except Exception:
                    log.exception("recognizer call failed")
                    continue
                data = json.loads(payload)
                if accepted:
                    spoken = data.get("text", "")
                    self._partial = ""
                    if spoken:
                        self._extend(spoken)
                    self._emit(
                        type="utterance", text=spoken, total=self._done, partial="",
                    )
                else:
                    self._partial = data.get("partial", "")
                    self._emit(
                        type="partial", text=self._partial, total=self._done,
                    )
        finally:
            if self._stream is not None:
                try:
                    self._stream.stop()
                    self._stream.close()
                except Exception:
                    log.exception("failed to close the input stream")
            log.info("recognizer thread finished")
