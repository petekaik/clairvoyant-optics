"""CLI-komennot — sovelluksen käynnistys, hallinta ja konfigurointi."""

import argparse
import logging
import sys
from pathlib import Path

logger = logging.getLogger(__name__)


def build_parser() -> argparse.ArgumentParser:
    """Rakenna CLI-parseri."""
    parser = argparse.ArgumentParser(
        prog="clairvoyant",
        description="Clairvoyant-Optics — Privacy-first facial recognition for macOS",
    )

    sub = parser.add_subparsers(dest="command", help="Available commands")

    # start
    start_p = sub.add_parser("start", help="Start the detection pipeline")
    start_p.add_argument("--env", type=Path, help="Path to .env file")
    start_p.add_argument("--no-menubar", action="store_true", help="Run without menubar")
    start_p.add_argument("--no-web", action="store_true", help="Run without web dashboard")

    # enroll
    enroll_p = sub.add_parser("enroll", help="Enroll a person from images")
    enroll_p.add_argument("name", help="Person's name")
    enroll_p.add_argument("image_dir", type=Path, help="Directory with person's photos")
    enroll_p.add_argument("--env", type=Path, help="Path to .env file")

    # import-from-photos
    import_p = sub.add_parser("import-from-photos", help="Import faces from macOS Photos.app")
    import_p.add_argument("--person", nargs="*", help="Specific person names (default: all)")
    import_p.add_argument("--max-photos", type=int, default=5, help="Max photos per person")
    import_p.add_argument("--env", type=Path, help="Path to .env file")

    # list-faces
    list_p = sub.add_parser("list-faces", help="List enrolled faces")
    list_p.add_argument("--env", type=Path, help="Path to .env file")

    # serve
    serve_p = sub.add_parser("serve", help="Start web dashboard only")
    serve_p.add_argument("--port", type=int, default=8765, help="Web server port")
    serve_p.add_argument("--host", type=str, default="127.0.0.1", help="Web server host")
    serve_p.add_argument("--env", type=Path, help="Path to .env file")

    return parser


def main(argv: list[str] | None = None):
    """CLI-sisäänmenopiste."""
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command is None:
        parser.print_help()
        return

    if args.command == "start":
        _cmd_start(args)
    elif args.command == "enroll":
        _cmd_enroll(args)
    elif args.command == "import-from-photos":
        _cmd_import_photos(args)
    elif args.command == "list-faces":
        _cmd_list_faces(args)
    elif args.command == "serve":
        _cmd_serve(args)


def _cmd_start(args):
    """Käynnistä koko putki + menubar + web."""
    from src.config import load_config
    from src.utils import setup_logging

    config = load_config(args.env)
    setup_logging(config.log_level)

    from src.main import DetectionPipeline

    pipeline = DetectionPipeline(config)

    if not args.no_menubar:
        from src.macos.menubar_app import MenubarApp
        menubar = MenubarApp(pipeline=pipeline, web_port=args.web_port if not args.no_web else 0)
        if menubar.available:
            import threading
            def _start_pipeline():
                pipeline.start()
            t = threading.Thread(target=_start_pipeline, daemon=True)
            t.start()
            menubar.run()
            return

    # Fallback: suora ajo ilman menubaria
    if not args.no_web:
        from src.macos.web_server import WebServer
        import threading
        ws = WebServer(pipeline=pipeline, config=config)
        if ws.available:
            app = ws.create_app()
            import uvicorn
            t = threading.Thread(target=uvicorn.run, args=(app,), kwargs={"host": ws.host, "port": ws.port}, daemon=True)
            t.start()
            print(f"Dashboard: {ws.url}")

    pipeline.start()


def _cmd_enroll(args):
    """Rekisteröi henkilö kuvahakemistosta."""
    from src.config import load_config
    from src.utils import setup_logging

    config = load_config(args.env)
    setup_logging("INFO")

    from src.recognition import FaceRecognizer, FaceDatabase
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

    image_exts = {".jpg", ".jpeg", ".png", ".webp", ".heic"}
    images = [p for p in args.image_dir.glob("*") if p.suffix.lower() in image_exts]

    if not images:
        logger.error(f"No images found in {args.image_dir}")
        return

    logger.info(f"Enrolling '{args.name}' from {len(images)} images")
    count = recognizer.enroll_person(images, args.name)
    logger.info(f"Done: {count} faces enrolled for '{args.name}'")

    db.close()


def _cmd_import_photos(args):
    """Tuo henkilöiden kasvogalleriat Photos.app:sta."""
    from src.config import load_config
    from src.utils import setup_logging

    config = load_config(args.env)
    setup_logging("INFO")

    from src.recognition import FaceRecognizer, FaceDatabase
    from src.macos.photos_importer import PhotosImporter

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

    importer = PhotosImporter(face_recognizer=recognizer)

    if not importer.available:
        logger.error("osxphotos not installed. Install with: pip install osxphotos")
        return

    # List persons first
    persons = importer.list_persons()
    print(f"\nPhotos.app persons ({len(persons)}):")
    print("-" * 60)
    for p in persons:
        has_local = "✅" if p["local_photos"] > 0 else "☁️"
        print(f"  {has_local} {p['name']:<25} {p['face_count']:>3} faces, {p['local_photos']:>3}/{p['photo_count']} local photos")

    # Import
    target = args.person or None
    print(f"\nImporting faces...")
    results = importer.import_faces(
        person_names=target,
        max_photos_per_person=args.max_photos,
    )

    total = sum(results.values())
    print(f"\nDone: {total} face embeddings generated from {len(results)} persons")

    db.close()


def _cmd_list_faces(args):
    """Listaa rekisteröidyt kasvot."""
    from src.config import load_config

    config = load_config(args.env)
    db_path = config.project_root / "data" / "faces.db"

    if not db_path.exists():
        print("No faces registered yet.")
        return

    from src.recognition import FaceDatabase
    db = FaceDatabase(db_path)
    faces = db.get_all_faces()

    if not faces:
        print("No faces registered.")
    else:
        print(f"\nEnrolled faces ({len(faces)}):")
        print("-" * 50)
        for f in faces:
            print(f"  {f['name']:<20} | samples: {f.get('samples', 1)} | source: {f.get('camera', 'manual')}")
        print("-" * 50)

    db.close()


def _cmd_serve(args):
    """Käynnistä pelkkä web-dashboard."""
    from src.config import load_config
    from src.utils import setup_logging

    config = load_config(args.env)
    setup_logging("INFO")

    from src.main import DetectionPipeline
    from src.macos.web_server import WebServer
    import uvicorn

    pipeline = DetectionPipeline(config)
    ws = WebServer(pipeline=pipeline, config=config, host=args.host, port=args.port)
    app = ws.create_app()

    print(f"Dashboard: {ws.url}")
    uvicorn.run(app, host=args.host, port=args.port)
