"""Kasvojentunnistus InsightFace/ArcFace-malleilla.

Käyttää snap JPEG -kuvia (1080p) parhaan tarkkuuden saavuttamiseksi.
"""

import cv2
import numpy as np
import pickle
import sqlite3
import logging
import time
from pathlib import Path
from typing import Optional
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


class FaceDatabase:
    """Kasvo-upotusten SQLite-tietokanta."""

    def __init__(self, db_path: Path):
        self.db_path = Path(db_path)
        self._conn: Optional[sqlite3.Connection] = None
        self._init_db()

    def _init_db(self) -> None:
        """Alusta tietokanta ja taulu."""
        self._conn = sqlite3.connect(str(self.db_path))
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS faces (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                person_name TEXT NOT NULL,
                embedding BLOB NOT NULL,
                source_camera TEXT,
                created_at TEXT NOT NULL,
                last_seen TEXT,
                sample_count INTEGER DEFAULT 1,
                UNIQUE(person_name)
            )
        """)
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS detections (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                person_name TEXT,
                camera TEXT,
                confidence REAL,
                detected_at TEXT NOT NULL
            )
        """)
        self._conn.commit()

    def add_face(self, name: str, embedding: np.ndarray, camera: str = "") -> None:
        """Lisää tai päivitä henkilön upotus (average embedding)."""
        embedding_bytes = pickle.dumps(embedding.astype(np.float32))
        now = datetime.now(timezone.utc).isoformat()

        existing = self._conn.execute(
            "SELECT id, embedding, sample_count FROM faces WHERE person_name = ?",
            (name,),
        ).fetchone()

        if existing:
            # Päivitä: laske juokseva keskiarvo
            old_embedding = pickle.loads(existing[1])
            sample_count = existing[2] + 1
            # Weighted average (uusi näyte painotettu 0.3)
            alpha = 0.3
            new_embedding = (1 - alpha) * old_embedding + alpha * embedding

            self._conn.execute(
                "UPDATE faces SET embedding = ?, sample_count = ?, last_seen = ? WHERE id = ?",
                (pickle.dumps(new_embedding.astype(np.float32)), sample_count, now, existing[0]),
            )
            logger.info(f"Updated face embedding for '{name}' (samples: {sample_count})")
        else:
            self._conn.execute(
                "INSERT INTO faces (person_name, embedding, source_camera, created_at, last_seen) "
                "VALUES (?, ?, ?, ?, ?)",
                (name, embedding_bytes, camera, now, now),
            )
            logger.info(f"Added new face: '{name}'")

        self._conn.commit()

    def get_all_faces(self) -> list[dict]:
        """Hae kaikki rekisteröidyt kasvot."""
        rows = self._conn.execute(
            "SELECT person_name, embedding, source_camera, sample_count FROM faces"
        ).fetchall()

        return [
            {
                "name": row[0],
                "embedding": pickle.loads(row[1]),
                "camera": row[2],
                "samples": row[3],
            }
            for row in rows
        ]

    def log_detection(self, name: str, camera: str, confidence: float) -> None:
        """Kirjaa tunnistustapahtuma."""
        now = datetime.now(timezone.utc).isoformat()
        self._conn.execute(
            "INSERT INTO detections (person_name, camera, confidence, detected_at) "
            "VALUES (?, ?, ?, ?)",
            (name, camera, confidence, now),
        )
        # Päivitä last_seen
        self._conn.execute(
            "UPDATE faces SET last_seen = ? WHERE person_name = ?",
            (now, name),
        )
        self._conn.commit()

    def close(self) -> None:
        if self._conn:
            self._conn.close()


class FaceRecognizer:
    """Kasvojentunnistus InsightFace-malleilla."""

    def __init__(
        self,
        detection_model: Path,
        recognition_model: Path,
        db: FaceDatabase,
        detection_confidence: float = 0.7,
        recognition_threshold: float = 0.6,
    ):
        self.detection_model_path = Path(detection_model)
        self.recognition_model_path = Path(recognition_model)
        self.db = db
        self.detection_confidence = detection_confidence
        self.recognition_threshold = recognition_threshold

        self._face_detector = None
        self._face_recognizer = None
        self._load_models()

    def _load_models(self) -> None:
        """Lataa InsightFace-mallit."""
        from insightface.model_zoo import get_model

        if not self.detection_model_path.exists():
            raise FileNotFoundError(f"Detection model not found: {self.detection_model_path}")
        if not self.recognition_model_path.exists():
            raise FileNotFoundError(f"Recognition model not found: {self.recognition_model_path}")

        self._face_detector = get_model(str(self.detection_model_path))
        self._face_detector.prepare(ctx_id=-1)  # -1 = CPU, 0 = GPU (Metal)

        self._face_recognizer = get_model(str(self.recognition_model_path))
        self._face_recognizer.prepare(ctx_id=-1)

        logger.info("Face recognition models loaded")

    def recognize_in_frame(self, frame: np.ndarray, camera_name: str = "") -> list[dict]:
        """Tunnista kasvot yhdestä kuvasta.

        Args:
            frame: BGR-kuva (snap JPEG, 1080p)
            camera_name: Kameran nimi lokitusta varten

        Returns:
            Lista dict:eja: [{name, confidence, bbox}, ...]
        """
        if self._face_detector is None or self._face_recognizer is None:
            return []

        t_start = time.perf_counter()

        # Detect faces
        bboxes, kpss = self._face_detector.detect(frame, threshold=self.detection_confidence)

        if bboxes is None or len(bboxes) == 0:
            return []

        results = []
        known_faces = self.db.get_all_faces()

        for bbox in bboxes:
            x1, y1, x2, y2, score = bbox
            x1, y1, x2, y2 = int(x1), int(y1), int(x2), int(y2)

            # Extract face embedding
            face_crop = frame[y1:y2, x1:x2]
            if face_crop.size == 0:
                continue

            embedding = self._face_recognizer.get_embedding(face_crop)

            if embedding is None:
                continue

            # Compare with known faces
            name, confidence = self._match_embedding(embedding, known_faces)

            results.append(
                {
                    "name": name,
                    "confidence": confidence,
                    "bbox": (x1, y1, x2, y2),
                }
            )

            if name != "unknown":
                self.db.log_detection(name, camera_name, confidence)

        elapsed_ms = (time.perf_counter() - t_start) * 1000
        names = [r["name"] for r in results]
        logger.debug(f"Face recognition: {names} in {elapsed_ms:.1f}ms")

        return results

    def _match_embedding(
        self, embedding: np.ndarray, known_faces: list[dict]
    ) -> tuple[str, float]:
        """Vertaa upotusta tunnettuihin kasvoihin cosine similarityllä.

        Returns:
            (name, confidence) — "unknown" jos ei osumaa.
        """
        if not known_faces:
            return "unknown", 0.0

        best_name = "unknown"
        best_sim = 0.0

        embedding_norm = embedding / (np.linalg.norm(embedding) + 1e-8)

        for face in known_faces:
            known_norm = face["embedding"] / (np.linalg.norm(face["embedding"]) + 1e-8)
            sim = float(np.dot(embedding_norm, known_norm))

            if sim > best_sim:
                best_sim = sim
                best_name = face["name"]

        if best_sim < self.recognition_threshold:
            return "unknown", best_sim

        return best_name, best_sim

    def enroll_person(self, image_paths: list[Path], name: str, camera: str = "") -> int:
        """Rekisteröi henkilö useasta kuvasta.

        Args:
            image_paths: Polut henkilön kuviin (5-10 kuvaa)
            name: Henkilön nimi
            camera: Kameran nimi

        Returns:
            Käytettyjen kuvien määrä.
        """
        embeddings = []

        for path in image_paths:
            frame = cv2.imread(str(path))
            if frame is None:
                logger.warning(f"Cannot read image: {path}")
                continue

            bboxes, _ = self._face_detector.detect(frame, threshold=self.detection_confidence)

            if bboxes is None or len(bboxes) == 0:
                logger.warning(f"No face found in: {path}")
                continue

            # Käytä suurinta kasvoa (oletus: lähin)
            best_bbox = max(bboxes, key=lambda b: (b[2] - b[0]) * (b[3] - b[1]))
            x1, y1, x2, y2 = int(best_bbox[0]), int(best_bbox[1]), int(best_bbox[2]), int(best_bbox[3])

            face_crop = frame[y1:y2, x1:x2]
            if face_crop.size == 0:
                continue

            embedding = self._face_recognizer.get_embedding(face_crop)
            if embedding is not None:
                embeddings.append(embedding)

        if not embeddings:
            logger.error(f"No valid embeddings extracted for '{name}'")
            return 0

        # Average embedding
        avg_embedding = np.mean(embeddings, axis=0)

        self.db.add_face(name, avg_embedding, camera)
        logger.info(f"Enrolled '{name}' with {len(embeddings)} images")

        return len(embeddings)
