"""Lataa ja tallenna tarvittavat ONNX-mallit paikallisesti.

Käyttää insightface-paketin sisäänrakennettua mallienhallintaa
ja ultralytics-pakettia YOLO-mallin konvertointiin ONNX-muotoon.

Aja: python download_models.py
"""

import shutil
import logging
import sys
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)

MODELS_DIR = Path(__file__).resolve().parent / "models"
INSIGHTFACE_CACHE = Path.home() / ".insightface" / "models" / "buffalo_l"


def download_insightface_models() -> bool:
    """Lataa InsightFace buffalo_l -mallit automaattisesti.

    InsightFace-paketti lataa mallit automaattisesti ~/.insightface/models/
    kun FaceAnalysis tekee prepare(ctx_id=-1).
    """
    logger.info("Loading InsightFace buffalo_l models...")
    try:
        from insightface.app import FaceAnalysis

        app = FaceAnalysis(name="buffalo_l")
        app.prepare(ctx_id=-1)  # CPU
        logger.info("  ✓ InsightFace models loaded (det_10g + w600k_r50)")
        return True
    except Exception as e:
        logger.error(f"  ✗ InsightFace failed: {e}")
        return False


def download_yolo_model() -> bool:
    """Lataa YOLOv8n ja exporttaa ONNX-muotoon."""
    logger.info("Loading YOLOv8n model...")
    try:
        from ultralytics import YOLO

        model = YOLO("yolov8n.pt")
        logger.info("  ✓ YOLOv8n downloaded")

        # Export ONNX
        logger.info("Exporting YOLOv8n to ONNX...")
        onnx_path = model.export(format="onnx", imgsz=640, simplify=True)

        # Siirrä MODELS_DIR:iin
        dest = MODELS_DIR / "yolov8n.onnx"
        model_path = Path(onnx_path)
        if model_path != dest:
            shutil.copy2(model_path, dest)
            logger.info(f"  ✓ ONNX exported: {dest} ({dest.stat().st_size / 1e6:.1f} MB)")

        return True
    except ImportError:
        logger.warning("ultralytics not installed. Install with: pip install ultralytics")
        logger.warning("Then run: python download_models.py --yolo-only")
        return False
    except Exception as e:
        logger.error(f"  ✗ YOLO failed: {e}")
        return False


def copy_insightface_models() -> None:
    """Kopioi InsightFace-mallit ~/.insightface/ → models/."""
    if not INSIGHTFACE_CACHE.exists():
        logger.warning(f"InsightFace cache not found at {INSIGHTFACE_CACHE}")
        logger.warning("Run download_insightface_models() first")
        return

    model_files = {
        "det_10g.onnx": INSIGHTFACE_CACHE / "det_10g.onnx",
        "w600k_r50.onnx": INSIGHTFACE_CACHE / "w600k_r50.onnx",
        "2d106det.onnx": INSIGHTFACE_CACHE / "2d106det.onnx",  # landmark
        "genderage.onnx": INSIGHTFACE_CACHE / "genderage.onnx",  # gender+age
    }

    MODELS_DIR.mkdir(parents=True, exist_ok=True)

    for name, src in model_files.items():
        if src.exists():
            dest = MODELS_DIR / name
            if not dest.exists() or dest.stat().st_mtime < src.stat().st_mtime:
                shutil.copy2(src, dest)
                size_mb = dest.stat().st_size / 1e6
                logger.info(f"  ✓ {name}: {size_mb:.1f} MB")
        else:
            logger.debug(f"  - {name}: not in cache")


def main() -> None:
    """Pääfunktio — lataa ja kopioi kaikki mallit."""
    import argparse

    parser = argparse.ArgumentParser(description="Lataa ML-mallit Clairvoyant-Optics:lle")
    parser.add_argument("--yolo-only", action="store_true", help="Lataa vain YOLO-malli")
    parser.add_argument("--insightface-only", action="store_true", help="Lataa vain InsightFace-mallit")
    parser.add_argument("--ci-mode", action="store_true", help="CI-tila — älä exit errorilla")
    args = parser.parse_args()

    MODELS_DIR.mkdir(parents=True, exist_ok=True)

    success = True

    if not args.yolo_only:
        logger.info("=== InsightFace Models ===")
        try:
            if download_insightface_models():
                copy_insightface_models()
            else:
                success = False
        except Exception as e:
            logger.error(f"InsightFace download crashed: {e}")
            success = False

    if not args.insightface_only:
        logger.info("\n=== YOLO Model ===")
        try:
            if not download_yolo_model():
                success = False
        except Exception as e:
            logger.error(f"YOLO download crashed: {e}")
            success = False

    # Yhteenveto
    logger.info(f"\n=== Models in {MODELS_DIR} ===")
    if MODELS_DIR.exists():
        for f in sorted(MODELS_DIR.glob("*.onnx")):
            logger.info(f"  {f.name}: {f.stat().st_size / 1e6:.1f} MB")
    else:
        logger.warning("No models directory found")

    if success:
        logger.info("\n✅ All models downloaded successfully")
    elif args.ci_mode:
        logger.warning("\n⚠ Some models failed — continuing in CI mode")
    else:
        logger.warning("\n⚠ Some models failed — see errors above")
        sys.exit(1)


if __name__ == "__main__":
    main()
