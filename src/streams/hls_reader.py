"""HLS-videovirtojen luku OpenCV:llä."""

import cv2
import time
import logging
from threading import Thread
from typing import Optional
from collections import deque

logger = logging.getLogger(__name__)


class HLSStreamReader:
    """Lukee HLS-streamia ja tarjoaa viimeisimmän framen."""

    def __init__(
        self,
        stream_url: str,
        name: str,
        max_reconnect_attempts: int = 10,
        reconnect_base_delay: float = 2.0,
        buffer_size: int = 1,
    ):
        self.stream_url = stream_url
        self.name = name
        self.max_reconnect_attempts = max_reconnect_attempts
        self.reconnect_base_delay = reconnect_base_delay
        self.buffer_size = buffer_size

        self._cap: Optional[cv2.VideoCapture] = None
        self._thread: Optional[Thread] = None
        self._running = False
        self._frame_buffer: deque = deque(maxlen=buffer_size)
        self._last_frame_time: float = 0.0
        self._fps: float = 0.0
        self._frames_read: int = 0

    def start(self) -> None:
        """Käynnistä taustasäie streamin lukemiseen."""
        if self._running:
            return
        self._running = True
        self._thread = Thread(target=self._read_loop, daemon=True, name=f"hls-{self.name}")
        self._thread.start()
        logger.info(f"[{self.name}] HLS stream reader started: {self.stream_url}")

    def stop(self) -> None:
        """Pysäytä streamin luku."""
        self._running = False
        if self._thread:
            self._thread.join(timeout=5.0)
        self._release_capture()

    def _open_capture(self) -> bool:
        """Avaa HLS-stream VideoCapturen kautta."""
        self._release_capture()

        # OpenCV HLS-tuki vaatii ffmpeg-backendin
        # macOS:lla opencv-python asennetaan tyypillisesti ffmpeg-tuella
        cap = cv2.VideoCapture(self.stream_url, cv2.CAP_FFMPEG)

        if not cap.isOpened():
            logger.error(f"[{self.name}] Failed to open stream: {self.stream_url}")
            return False

        # Asetetaan puskurointi pieneksi (low latency HLS)
        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)

        self._cap = cap
        self._frames_read = 0
        logger.info(f"[{self.name}] Stream opened successfully")
        return True

    def _release_capture(self) -> None:
        if self._cap is not None:
            self._cap.release()
            self._cap = None

    def _read_loop(self) -> None:
        """Pääsilmukka: lue frameja ja yhdistä tarvittaessa uudelleen."""
        reconnect_attempts = 0

        while self._running:
            if self._cap is None or not self._cap.isOpened():
                if not self._open_capture():
                    reconnect_attempts += 1
                    if reconnect_attempts > self.max_reconnect_attempts:
                        logger.error(
                            f"[{self.name}] Max reconnect attempts ({self.max_reconnect_attempts}) reached, giving up"
                        )
                        break
                    delay = self.reconnect_base_delay * (2 ** (reconnect_attempts - 1))
                    logger.warning(
                        f"[{self.name}] Reconnect attempt {reconnect_attempts}/{self.max_reconnect_attempts} "
                        f"in {delay:.1f}s"
                    )
                    time.sleep(delay)
                    continue
                reconnect_attempts = 0

            ret, frame = self._cap.read()
            if not ret:
                logger.warning(f"[{self.name}] Frame read failed, will reconnect")
                self._release_capture()
                continue

            reconnect_attempts = 0
            self._frames_read += 1
            self._last_frame_time = time.time()
            self._frame_buffer.append(frame)

    def get_latest_frame(self) -> Optional[tuple]:
        """Hae viimeisin frame.

        Returns:
            Tuple (frame, timestamp) tai None jos ei frameja saatavilla.
        """
        if self._frame_buffer:
            frame = self._frame_buffer[-1]
            return frame, self._last_frame_time
        return None

    @property
    def is_connected(self) -> bool:
        return self._cap is not None and self._cap.isOpened()

    @property
    def fps(self) -> float:
        if self._last_frame_time == 0:
            return 0.0
        elapsed = time.time() - self._last_frame_time
        if elapsed > 5:
            return 0.0
        return self._frames_read / max(elapsed, 0.001) if elapsed > 0 else 0.0
