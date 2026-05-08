"""Pääsilmukka — orkestroi koko tunnistusputken.

Arkkitehtuuri:
1. Lue HLS-streamit (Low/Medium resoluutio)
2. Henkilötunnistus (YOLOv8n) jokaisesta framesta
3. Jos henkilö havaittu → hae snap JPEG kameralta (1080p)
4. Kasvojentunnistus (InsightFace) snap-kuvasta
5. Lähetä tulos MQTT:lla Home Assistantiin
"""

import logging
import time
import threading
from pathlib import Path
from typing import Optional

import cv2
import numpy as np
import requests

from src.config import Config, CameraConfig, load_config
from src.streams import HLSStreamReader
from src.detection import PersonDetector
from src.recognition import FaceRecognizer, FaceDatabase
from src.integration import MQTTNotifier
from src.utils import setup_logging

logger = logging.getLogger(__name__)


class DetectionPipeline:
    """Pääputki: yhdistää streamit, tunnistuksen ja MQTT:n."""

    def __init__(self, config: Config):
        self.config = config

        # Tietokanta
        db_path = config.project_root / "data" / "faces.db"
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self.face_db = FaceDatabase(db_path)

        # Person detector (YOLOv8n)
        logger.info(f"Loading YOLO model: {config.models.yolo}")
        self.person_detector = PersonDetector(
            model_path=config.models.yolo,
            confidence_threshold=config.detection.person_confidence,
        )

        # Face recognizer (InsightFace)
        logger.info(f"Loading face models: {config.models.face_detection}, {config.models.face_recognition}")
        try:
            self.face_recognizer = FaceRecognizer(
                detection_model=config.models.face_detection,
                recognition_model=config.models.face_recognition,
                db=self.face_db,
                detection_confidence=config.detection.face_confidence,
                recognition_threshold=config.detection.recognition_threshold,
            )
        except FileNotFoundError as e:
            logger.warning(f"Face models not available: {e}")
            logger.warning("Person detection only — face recognition disabled")
            self.face_recognizer = None

        # MQTT
        self.mqtt = MQTTNotifier(
            broker=config.mqtt.broker,
            port=config.mqtt.port,
            username=config.mqtt.username,
            password=config.mqtt.password,
            topic_prefix=config.mqtt.topic_prefix,
        )
        self.mqtt.connect()

        # Stream readerit per kamera
        self.streams: dict[str, HLSStreamReader] = {}
        self._init_streams()

        # Debounce: estä spam (sama henkilö + kamera)
        self._last_detection: dict[str, float] = {}  # key: "{camera}:{name}" → timestamp
        self._debounce_seconds = 30  # Sama henkilö samasta kamerasta max 1/30s

        # State tracking: henkilöt kuvassa
        self._active_persons: dict[str, set[str]] = {}  # camera → {names}

        self._running = False

    def _init_streams(self) -> None:
        """Alusta HLS-stream-lukijat kaikille kameroille."""
        for cam in self.config.cameras:
            if cam.stream_url:
                self.streams[cam.name] = HLSStreamReader(
                    stream_url=cam.stream_url,
                    name=cam.name,
                )

    def start(self) -> None:
        """Käynnistä putki."""
        if self._running:
            return

        logger.info(f"Starting detection pipeline for {len(self.streams)} camera(s)")
        logger.info(f"  Frame interval: every {self.config.detection.frame_interval}th frame")
        logger.info(f"  Person confidence: {self.config.detection.person_confidence}")
        logger.info(f"  Face confidence: {self.config.detection.face_confidence}")
        logger.info(f"  Recognition threshold: {self.config.detection.recognition_threshold}")
        logger.info(f"  Debounce: {self._debounce_seconds}s")
        logger.info(f"  Registered faces: {len(self.face_db.get_all_faces())}")

        # Käynnistä streamit
        for stream in self.streams.values():
            stream.start()

        self._running = True

        # Anna streamien lämmetä
        time.sleep(2)

        try:
            self._main_loop()
        except KeyboardInterrupt:
            logger.info("Shutting down...")
        finally:
            self.stop()

    def stop(self) -> None:
        """Pysäytä putki siististi."""
        self._running = False
        for stream in self.streams.values():
            stream.stop()
        self.mqtt.disconnect()
        self.face_db.close()
        logger.info("Pipeline stopped")

    def _main_loop(self) -> None:
        """Pääsilmukka: prosessoi frameja kameroittain."""

        frame_counter = 0
        interval = self.config.detection.frame_interval

        while self._running:
            # Prosessoi jokainen kamera
            for cam in self.config.cameras:
                stream = self.streams.get(cam.name)
                if stream is None:
                    continue

                # Haetaan frame vain joka N:s
                frame_counter += 1
                if frame_counter % interval != 0:
                    continue

                result = stream.get_latest_frame()
                if result is None:
                    continue

                frame, _ = result
                self._process_frame(frame, cam)

            # Pieni lepotauko ettei polteta CPU:ta jos ei frameja
            time.sleep(0.05)

    def _process_frame(self, frame, cam: CameraConfig) -> None:
        """Prosessoi yksi frame: henkilötunnistus → kasvojentunnistus."""

        # 1. Person detection (low-res frame)
        persons = self.person_detector.detect(frame)

        current_names = set()

        if not persons:
            # Ei henkilöitä framessa → tarkista ketkä poistuivat
            self._handle_gone_persons(cam.name, current_names)
            return

        # 2. Fetch snap JPEG (1080p) for face recognition
        snap_frame = self._fetch_snap(cam.snap_url)
        if snap_frame is None:
            # Fallback: käytä HLS-framea kasvojentunnistukseen (huonompi laatu)
            snap_frame = frame
            logger.debug(f"[{cam.name}] Using HLS frame as fallback (snap unavailable)")

        # 3. Face recognition
        if self.face_recognizer is not None:
            face_results = self.face_recognizer.recognize_in_frame(snap_frame, cam.name)

            for result in face_results:
                name = result["name"]
                conf = result["confidence"]

                current_names.add(name)

                if name == "unknown":
                    self.mqtt.notify_unknown_person(
                        cam.name, result["bbox"]
                    )
                    continue

                # Debounce check
                key = f"{cam.name}:{name}"
                now = time.time()
                last = self._last_detection.get(key, 0)
                if now - last < self._debounce_seconds:
                    continue  # Skip, liian vähän aikaa edellisestä

                self._last_detection[key] = now
                self.mqtt.notify_person_detected(name, cam.name, conf)

            # Piirrä bounding boxit debug-kuvaan (valinnainen)
            self._draw_debug(snap_frame, face_results, cam.name)

        # Tarkista ketkä poistuivat (vain jos kasvontunnistus käytössä)
        if self.face_recognizer is not None:
            self._handle_gone_persons(cam.name, current_names)

    def _fetch_snap(self, snap_url: str, timeout: float = 2.0) -> Optional:
        """Hae snap JPEG -kuva kameralta.

        Args:
            snap_url: Kameran snap-URL (https://...)
            timeout: HTTP-aikakatkaisu sekunteina

        Returns:
            BGR-kuva numpy arrayna tai None jos haku epäonnistui.
        """
        if not snap_url:
            return None

        try:
            resp = requests.get(
                snap_url, timeout=timeout, verify=False
            )  # verify=False koska self-signed certit
            resp.raise_for_status()

            # Dekoodaa JPEG → numpy array
            img_array = np.frombuffer(resp.content, dtype=np.uint8)
            frame = cv2.imdecode(img_array, cv2.IMREAD_COLOR)

            if frame is None:
                logger.warning(f"Failed to decode snap from {snap_url}")
                return None

            return frame

        except requests.RequestException as e:
            logger.debug(f"Snap fetch failed: {e}")
            return None

    def _handle_gone_persons(self, camera: str, current_names: set[str]) -> None:
        """Tarkista ketkä poistuivat kuvasta ja lähetä gone-ilmoitus."""
        previous = self._active_persons.get(camera, set())

        gone = previous - current_names
        for name in gone:
            self.mqtt.notify_person_gone(name, camera)

        self._active_persons[camera] = current_names

    def _draw_debug(self, frame, face_results: list[dict], camera: str) -> None:
        """Piirrä bounding boxit debug-kuvaan (valinnainen, poista tuotannosta)."""
        # Debug-värit
        colors = {
            "unknown": (0, 0, 255),  # punainen
        }

        for i, r in enumerate(face_results):
            x1, y1, x2, y2 = r["bbox"]
            name = r["name"]
            conf = r["confidence"]

            # Määritä väri: vihreä tunnetulle, punainen tuntemattomalle
            color = colors.get(name, (0, 255, 0))

            cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)

            label = f"{name} ({conf:.2f})"
            cv2.putText(
                frame, label, (x1, y1 - 10),
                cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 1
            )

        # Tallenna debug-kuva
        debug_dir = self.config.project_root / "debug"
        debug_dir.mkdir(exist_ok=True)
        timestamp = int(time.time())
        debug_path = debug_dir / f"{camera}_{timestamp}_{time.strftime('%H%M%S')}.jpg"
        cv2.imwrite(str(debug_path), frame)


# Globals for simple process management
_pipeline: Optional[DetectionPipeline] = None


def main() -> None:
    """Sovelluksen sisäänmenopiste."""
    import argparse

    parser = argparse.ArgumentParser(description="Clairvoyant-Optics — paikallinen kasvojentunnistus")
    parser.add_argument(
        "--env", type=Path, default=None,
        help="Polku .env-tiedostoon (oletus: projektin juuri/.env)"
    )
    parser.add_argument(
        "--enroll", type=str, nargs=2, metavar=("NAME", "IMAGE_DIR"),
        help="Rekisteröi henkilö hakemiston kuvista"
    )
    parser.add_argument(
        "--list-faces", action="store_true",
        help="Listaa rekisteröidyt kasvot"
    )
    args = parser.parse_args()

    config = load_config(args.env)
    setup_logging(config.log_level)

    if args.enroll:
        name, img_dir = args.enroll
        _do_enroll(config, name, Path(img_dir))
        return

    if args.list_faces:
        _do_list_faces(config)
        return

    # Normaali ajo: käynnistä putki
    global _pipeline
    _pipeline = DetectionPipeline(config)
    _pipeline.start()


def _do_enroll(config: Config, name: str, img_dir: Path) -> None:
    """CLI: rekisteröi henkilön kasvot."""
    setup_logging("INFO")

    db_path = config.project_root / "data" / "faces.db"
    db_path.parent.mkdir(parents=True, exist_ok=True)
    db = FaceDatabase(db_path)

    recognizer = FaceRecognizer(
        detection_model=config.models.face_detection,
        recognition_model=config.models.face_recognition,
        db=db,
        detection_confidence=config.detection.face_confidence,
        recognition_threshold=config.detection.recognition_threshold,
    )

    # Hae kaikki kuvat hakemistosta
    image_extensions = {".jpg", ".jpeg", ".png", ".webp"}
    images = [p for p in img_dir.glob("*") if p.suffix.lower() in image_extensions]

    if not images:
        logger.error(f"No images found in {img_dir}")
        return

    logger.info(f"Enrolling '{name}' from {len(images)} images in {img_dir}")
    count = recognizer.enroll_person(images, name, camera="manual")
    logger.info(f"Enrollment complete: {count} images used")

    db.close()


def _do_list_faces(config: Config) -> None:
    """CLI: listaa rekisteröidyt kasvot."""
    setup_logging("WARNING")  # Hiljennä logit

    db_path = config.project_root / "data" / "faces.db"
    if not db_path.exists():
        print("No faces registered yet (database not found).")
        return

    db = FaceDatabase(db_path)
    faces = db.get_all_faces()

    if not faces:
        print("No faces registered.")
    else:
        print(f"\nRegistered faces ({len(faces)}):")
        print("-" * 50)
        for face in faces:
            print(f"  {face['name']:<20} | samples: {face['samples']} | embedding dim: {face['embedding'].shape}")
        print("-" * 50)

    db.close()


if __name__ == "__main__":
    main()
