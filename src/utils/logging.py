"""Apufunktiot: lokitus, debounce, kuvan haku."""

import logging
import sys


def setup_logging(level: str = "INFO") -> None:
    """Konfiguroi strukturoitu lokitus stdout:iin."""

    formatter = logging.Formatter(
        "%(asctime)s | %(levelname)-5s | %(name)s | %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
    )

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)

    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, level, logging.INFO))
    root_logger.handlers.clear()
    root_logger.addHandler(handler)

    # Hiljennä kolmannen osapuolen loggereissa oleva melu
    logging.getLogger("paho").setLevel(logging.WARNING)
    logging.getLogger("onnxruntime").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("PIL").setLevel(logging.WARNING)
