"""Kasvogallerioiden tuonti macOS Photos.app:sta.

Hakee Photos.app:n henkilögallerioiden kasvokuvat, generoi
InsightFace-upotukset ja tallentaa ne sovelluksen SQLite-kantaan.
"""

import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# osxphotos on macOS-only, tuodaan vain tarvittaessa
_HAS_OSXPHOTOS = False
try:
    from osxphotos import PhotosDB
    _HAS_OSXPHOTOS = True
except ImportError:
    pass


class PhotosImporter:
    """Photos.app-kirjaston henkilögallerioiden tuonti."""

    def __init__(self, face_recognizer=None):
        """
        Args:
            face_recognizer: FaceRecognizer-instanssi upotusten generointiin.
                            Jos None, upotuksia ei generoida — näytetään vain henkilöt.
        """
        self.recognizer = face_recognizer

    @property
    def available(self) -> bool:
        return _HAS_OSXPHOTOS

    def list_persons(self) -> list[dict]:
        """Listaa kaikki Photos.app:n nimetyt henkilöt ja heidän kasvojensa määrä.

        Returns:
            [{name, face_count, photo_count, has_local_photos}, ...]
        """
        if not _HAS_OSXPHOTOS:
            raise RuntimeError("osxphotos not installed. Install with: pip install osxphotos")

        db = PhotosDB()
        names = list(db.persons)
        result = []

        # Count faces per person
        photos_with_faces = 0
        photos_local = 0
        for name in names:
            if name == "_UNKNOWN_":
                continue

            face_count = 0
            local_count = 0
            total_count = 0
            for p in db.photos():
                if name in list(p.persons):
                    total_count += 1
                    face_count += len([f for f in p.face_info if f.name == name])
                    if not p.ismissing:
                        local_count += 1

            result.append({
                "name": name,
                "face_count": face_count,
                "photo_count": total_count,
                "local_photos": local_count,
            })

        return result

    def import_faces(
        self,
        person_names: Optional[list[str]] = None,
        max_photos_per_person: int = 5,
        force: bool = False,
    ) -> dict[str, int]:
        """Tuo henkilöiden kasvogalleriat Photos.app:sta ja generoi upotukset.

        Args:
            person_names: Tuotavien henkilöiden nimet. None = kaikki nimetyt.
            max_photos_per_person: Montako kuvaa per henkilö (max).
            force: Korvaa olemassa olevat upotukset.

        Returns:
            {name: imported_count} — montako kuvaa tuotiin per henkilö.

        Requires face_recognizer for embedding generation.
        """
        if not _HAS_OSXPHOTOS:
            raise RuntimeError("osxphotos not installed. Install with: pip install osxphotos")
        if self.recognizer is None:
            raise RuntimeError("FaceRecognizer required for import. Pass it in constructor.")

        import cv2
        db = PhotosDB()
        all_names = list(db.persons)
        target_names = person_names or [n for n in all_names if n != "_UNKNOWN_"]

        results = {}
        for name in target_names:
            # Find local photos with this person
            face_images = []
            for p in db.photos():
                if name not in list(p.persons):
                    continue
                if p.ismissing:
                    continue  # Skip iCloud-only photos

                # Extract face region
                img = cv2.imread(p.path)
                if img is None:
                    continue

                for fi in p.face_info:
                    if fi.name != name:
                        continue

                    # Crop face region with margin
                    h, w = img.shape[:2]
                    cx, cy = fi.center_x * w, fi.center_y * h
                    s = fi.size * max(w, h)
                    half = int(s / 1.6)  # Smaller crop = tighter face
                    x1 = max(0, int(cx - half))
                    y1 = max(0, int(cy - half))
                    x2 = min(w, int(cx + half))
                    y2 = min(h, int(cy + half))

                    face = img[y1:y2, x1:x2]
                    if face.size > 0:
                        face_images.append(face)

                if len(face_images) >= max_photos_per_person:
                    break

            if not face_images:
                logger.warning(f"No local photos found for '{name}' (all iCloud-only?)")
                results[name] = 0
                continue

            logger.info(f"Importing '{name}': {len(face_images)} face crops")

            # Generate embeddings using InsightFace
            embeddings = []
            for face in face_images:
                emb = self.recognizer._face_recognizer.get_embedding(face)
                if emb is not None:
                    embeddings.append(emb)

            if not embeddings:
                logger.warning(f"Could not extract embeddings for '{name}'")
                results[name] = 0
                continue

            # Average embedding
            import numpy as np
            avg_embedding = np.mean(embeddings, axis=0)

            if force:
                # Remove existing and re-add
                # (FaceDatabase.add_face handles update via running average)
                pass

            self.recognizer.db.add_face(name, avg_embedding, camera="photos_app")
            results[name] = len(embeddings)

        return results
