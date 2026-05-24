"""Audio recording helpers (WAV/FLAC with optional rotation)."""
from __future__ import annotations

import logging
import wave
from pathlib import Path
from typing import Any, Dict, Optional

import numpy as np

try:  # Optional dependency for FLAC support
    import soundfile as sf  # type: ignore
except Exception:  # pragma: no cover - handled at runtime
    sf = None

logger = logging.getLogger(__name__)

SUPPORTED_FORMATS = {"wav", "flac"}


def resolve_recording_config(audio_cfg: Dict[str, Any]) -> Dict[str, Any]:
    """Resolve recording config with backward compatibility defaults."""
    rec = audio_cfg.get("recording")
    if isinstance(rec, dict):
        fmt = str(rec.get("format", "wav")).lower()
        rotate_seconds = float(rec.get("rotate_seconds", 0) or 0)
        rotate_mb = rec.get("rotate_mb", 0) or 0
        rotate_bytes = rec.get("rotate_bytes", 0) or 0
        if rotate_bytes:
            rotate_bytes = int(rotate_bytes)
        elif rotate_mb:
            rotate_bytes = int(float(rotate_mb) * 1024 * 1024)
        directory = rec.get("directory", "audio")
        system_enabled = bool(rec.get("system", audio_cfg.get("save_wav_system", False)))
        mic_enabled = bool(rec.get("mic", audio_cfg.get("save_wav_mic", False)))
    else:
        # Legacy config fallback
        fmt = "wav"
        rotate_seconds = 0.0
        rotate_bytes = 0
        directory = ""
        system_enabled = bool(audio_cfg.get("save_wav_system", False))
        mic_enabled = bool(audio_cfg.get("save_wav_mic", False))

    return {
        "format": fmt,
        "rotate_seconds": max(0.0, float(rotate_seconds)),
        "rotate_bytes": max(0, int(rotate_bytes)),
        "directory": "" if directory is None else str(directory).strip(),
        "system": system_enabled,
        "mic": mic_enabled,
    }


class AudioRecorder:
    """Stream PCM16 audio into WAV/FLAC files with optional rotation."""

    def __init__(
        self,
        *,
        base_dir: Path,
        basename: str,
        sample_rate: int,
        channels: int,
        sample_width: int,
        fmt: str,
        rotate_seconds: float = 0.0,
        rotate_bytes: int = 0,
        always_index: Optional[bool] = None,
    ) -> None:
        self.base_dir = base_dir
        self.basename = basename
        self.sample_rate = int(sample_rate)
        self.channels = int(channels)
        self.sample_width = int(sample_width)
        self.format = str(fmt).lower()
        self.rotate_seconds = max(0.0, float(rotate_seconds))
        self.rotate_bytes = max(0, int(rotate_bytes))

        if self.format not in SUPPORTED_FORMATS:
            raise ValueError(f"Unsupported audio format: {self.format!r}")
        if self.format == "flac" and sf is None:
            raise RuntimeError("FLAC recording requires the 'soundfile' package.")

        self._bytes_per_frame = self.sample_width * self.channels
        self._max_frames = int(self.rotate_seconds * self.sample_rate) if self.rotate_seconds else 0
        self._max_bytes = int(self.rotate_bytes) if self.rotate_bytes else 0
        self._always_index = bool(always_index) if always_index is not None else bool(self._max_frames or self._max_bytes)

        self._writer = None
        self._current_path: Optional[Path] = None
        self._frames_written = 0
        self._bytes_written = 0
        self._file_index = 0
        self._final_closed = False

    def start(self) -> None:
        if self._final_closed:
            return
        if self._writer is None:
            self._open_new_file()

    def write(self, data: bytes) -> None:
        if self._final_closed or not data:
            return
        if self._bytes_per_frame <= 0:
            return

        incoming_frames = len(data) // self._bytes_per_frame
        if incoming_frames <= 0:
            return

        data = data[: incoming_frames * self._bytes_per_frame]

        if self._writer is None:
            self._open_new_file()
        elif self._should_rotate(incoming_frames, len(data)):
            self._close_writer()
            self._open_new_file()

        self._write_frames(data)
        self._frames_written += incoming_frames
        self._bytes_written += len(data)

    def close(self) -> None:
        self._close_writer()
        self._final_closed = True

    def _should_rotate(self, incoming_frames: int, incoming_bytes: int) -> bool:
        if self._max_frames and (self._frames_written + incoming_frames) > self._max_frames:
            return True
        if self._max_bytes and (self._bytes_written + incoming_bytes) > self._max_bytes:
            return True
        return False

    def _open_new_file(self) -> None:
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self._file_index += 1

        if self._always_index:
            name = f"{self.basename}_{self._file_index:04d}.{self.format}"
            path = self.base_dir / name
            while path.exists():
                self._file_index += 1
                name = f"{self.basename}_{self._file_index:04d}.{self.format}"
                path = self.base_dir / name
        else:
            path = self.base_dir / f"{self.basename}.{self.format}"
        self._current_path = path
        self._frames_written = 0
        self._bytes_written = 0

        if self.format == "wav":
            wf = wave.open(str(path), "wb")
            wf.setnchannels(int(self.channels))
            wf.setsampwidth(int(self.sample_width))
            wf.setframerate(int(self.sample_rate))
            self._writer = wf
        else:
            assert sf is not None  # for type checker
            if self.sample_width != 2:
                raise ValueError("FLAC recording currently supports PCM16 only.")
            self._writer = sf.SoundFile(
                str(path),
                mode="w",
                samplerate=int(self.sample_rate),
                channels=int(self.channels),
                subtype="PCM_16",
                format="FLAC",
            )

        logger.info("Audio recording started: %s", path)

    def _write_frames(self, data: bytes) -> None:
        if self._writer is None:
            return

        if self.format == "wav":
            self._writer.writeframes(data)
            return

        # FLAC: convert to numpy and write
        assert sf is not None
        arr = np.frombuffer(data, dtype=np.int16)
        frames = arr.size // max(1, self.channels)
        if frames <= 0:
            return
        arr = arr[: frames * self.channels]
        if self.channels > 1:
            arr = arr.reshape(frames, self.channels)
        self._writer.write(arr)

    def _close_writer(self) -> None:
        if self._writer is None:
            return
        try:
            self._writer.close()
        except Exception:  # noqa: BLE001
            logger.exception("Failed to close audio file writer.")
        finally:
            if self._current_path:
                seconds = self._frames_written / self.sample_rate if self.sample_rate else 0.0
                logger.info("Audio recording closed: %s (%.2f s)", self._current_path, seconds)
            self._writer = None
            self._current_path = None
