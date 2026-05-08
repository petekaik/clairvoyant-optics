"""YOLOv8 henkilötunnistus ONNX/CoreML-malleilla."""

import cv2
import numpy as np
import logging
import time
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


class PersonDetector:
    """YOLOv8-pohjainen henkilötunnistus.

    Tukee ONNX- ja CoreML-malleja. M1:llä CoreML on nopein.
    """

    # COCO-luokat: 0 = person
    PERSON_CLASS = 0

    def __init__(self, model_path: Path, confidence_threshold: float = 0.5):
        self.model_path = Path(model_path)
        self.confidence_threshold = confidence_threshold

        self._model = None
        self._input_width = 640
        self._input_height = 640
        self._use_coreml = self.model_path.suffix in (".mlpackage", ".mlmodel")

        self._load_model()

    def _load_model(self) -> None:
        """Lataa malli — yritä CoreML, fallback ONNX."""

        if not self.model_path.exists():
            raise FileNotFoundError(f"Model not found: {self.model_path}")

        suffix = self.model_path.suffix.lower()

        if suffix == ".onnx":
            self._load_onnx()
        elif suffix in (".mlpackage", ".mlmodel"):
            self._load_coreml()
        else:
            # Yritä ONNX oletuksena
            logger.warning(f"Unknown model format '{suffix}', trying ONNX...")
            self._load_onnx()

    def _load_onnx(self) -> None:
        """Lataa ONNX-malli onnxruntimella."""
        import onnxruntime as ort

        # Apple Silicon: CoreML Execution Provider jos saatavilla
        providers = ort.get_available_providers()
        logger.info(f"Available ONNX providers: {providers}")

        if "CoreMLExecutionProvider" in providers:
            logger.info("Using CoreMLExecutionProvider for ONNX")
            sess_options = ort.SessionOptions()
            self._model = ort.InferenceSession(
                str(self.model_path),
                sess_options=sess_options,
                providers=["CoreMLExecutionProvider", "CPUExecutionProvider"],
            )
        else:
            self._model = ort.InferenceSession(
                str(self.model_path), providers=["CPUExecutionProvider"]
            )

        # Hae input-koko mallin metadatasta
        input_shape = self._model.get_inputs()[0].shape
        if len(input_shape) == 4:
            self._input_height = input_shape[2] if isinstance(input_shape[2], int) else 640
            self._input_width = input_shape[3] if isinstance(input_shape[3], int) else 640

    def _load_coreml(self) -> None:
        """Lataa CoreML-malli."""
        try:
            import coremltools as ct

            self._model = ct.models.MLModel(str(self.model_path))
            logger.info(f"Loaded CoreML model: {self.model_path}")
            self._use_coreml = True
        except ImportError:
            logger.warning("coremltools not installed, falling back to ONNX")
            # Yritä löytää ONNX-versio samasta hakemistosta
            onnx_path = self.model_path.with_suffix(".onnx")
            if onnx_path.exists():
                self.model_path = onnx_path
                self._load_onnx()
            else:
                raise

    def detect(self, frame: np.ndarray) -> list[dict]:
        """Tunnista henkilöt yhdestä framesta.

        Args:
            frame: BGR-kuva (H, W, 3)

        Returns:
            Lista dict:eja: [{bbox: (x1,y1,x2,y2), confidence: float}, ...]
            Tyhjä lista jos ei henkilöitä.
        """
        if self._model is None:
            return []

        t_start = time.perf_counter()

        # Preprocess: resize + normalize
        input_tensor = self._preprocess(frame)

        # Inferenssi
        if self._use_coreml:
            detections = self._infer_coreml(input_tensor)
        else:
            detections = self._infer_onnx(input_tensor)

        # Skaalaa bboxit alkuperäiseen resoluutioon
        h, w = frame.shape[:2]
        scale_x = w / self._input_width
        scale_y = h / self._input_height

        persons = []
        for det in detections:
            cls_id = int(det.get("class", -1))
            if cls_id != self.PERSON_CLASS:
                continue

            conf = float(det["confidence"])
            if conf < self.confidence_threshold:
                continue

            x1, y1, x2, y2 = det["bbox"]
            persons.append(
                {
                    "bbox": (
                        int(x1 * scale_x),
                        int(y1 * scale_y),
                        int(x2 * scale_x),
                        int(y2 * scale_y),
                    ),
                    "confidence": conf,
                }
            )

        elapsed_ms = (time.perf_counter() - t_start) * 1000
        if persons:
            confs = ", ".join(f"{p['confidence']:.2f}" for p in persons)
            logger.debug(
                f"Person detection: {len(persons)} person(s) in {elapsed_ms:.1f}ms "
                f"(conf: {confs})"
            )

        return persons

    def _preprocess(self, frame: np.ndarray) -> np.ndarray:
        """Preprocess frame: resize, BGR→RGB, normalize, transpose."""
        # Resize
        img = cv2.resize(frame, (self._input_width, self._input_height))

        # BGR → RGB
        img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)

        # Normalize to [0, 1]
        img = img.astype(np.float32) / 255.0

        # HWC → NCHW
        img = np.transpose(img, (2, 0, 1))

        # Add batch dimension
        img = np.expand_dims(img, axis=0)

        return img

    def _infer_onnx(self, input_tensor: np.ndarray) -> list[dict]:
        """ONNX-inferenssi ja YOLOv8-outputin dekoodaus."""
        input_name = self._model.get_inputs()[0].name
        outputs = self._model.run(None, {input_name: input_tensor})
        # YOLOv8 output: [1, 84, 8400] (84 = 4 bbox + 80 classes)
        # tai [1, 5+n_classes, num_predictions]
        return self._decode_yolov8_output(outputs[0])

    def _infer_coreml(self, input_tensor: np.ndarray) -> list[dict]:
        """CoreML-inferenssi."""
        # CoreML odottaa tyypillisesti CHW-muotoa ilman batch-dimensiota
        result = self._model.predict({"image": input_tensor[0]})
        # CoreML output vaihtelee, hae ensimmäinen output
        output = list(result.values())[0]
        if isinstance(output, list):
            output = np.array(output)
        return self._decode_yolov8_output(output)

    @staticmethod
    def _decode_yolov8_output(output: np.ndarray) -> list[dict]:
        """Dekoodaa YOLOv8 output."""
        # output shape: [1, 84, 8400] → squeeze batch dim → [84, 8400]
        output = np.squeeze(output)

        if output.ndim == 1:
            return []

        # Transpose: [8400, 84] → [8400 predictions, 84 features]
        # Features: [cx, cy, w, h, 80 class scores]
        if output.shape[0] == 84:
            output = output.T  # → [8400, 84]

        detections = []
        for pred in output:
            # 4 bbox coords + 80 class scores
            cx, cy, bw, bh = pred[:4]
            scores = pred[4:]

            class_id = int(np.argmax(scores))
            confidence = float(scores[class_id])

            if confidence > 0:
                # Convert center to corner
                x1 = cx - bw / 2
                y1 = cy - bh / 2
                x2 = cx + bw / 2
                y2 = cy + bh / 2

                detections.append(
                    {
                        "bbox": (x1, y1, x2, y2),
                        "class": class_id,
                        "confidence": confidence,
                    }
                )

        return detections

    @property
    def input_size(self) -> tuple[int, int]:
        return self._input_width, self._input_height
