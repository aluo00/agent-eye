"""
OmniParser perception layer — pure vision screen parsing for ANY UI.

Uses Microsoft's OmniParser (YOLO icon detection + Florence caption + OCR)
to extract structured UI elements from screenshots.  Works on Chrome, VS Code,
Unity, games, custom UIs — everything UIA can't see.

Requires:
    pip install ultralytics transformers torch easyocr
    # Models auto-downloaded from HuggingFace on first use (~1.5 GB)

Model weights from: huggingface.co/microsoft/OmniParser-v2.0
"""

from __future__ import annotations

import sys
from typing import Any, Optional

_OMNIPARSER_AVAILABLE = False
_som_model: Any = None
_caption_processor: Any = None
_ocr_available: bool = False
_device: str = "cpu"


def _ensure_omniparser() -> None:
    """Lazy-load OmniParser models. Call once before first use."""
    global _OMNIPARSER_AVAILABLE, _som_model, _caption_processor, _ocr_available, _device

    if _OMNIPARSER_AVAILABLE:
        return

    # Check dependencies.
    missing = []
    try:
        import torch
        _device = "cuda" if torch.cuda.is_available() else "cpu"
    except ImportError:
        missing.append("torch")
    try:
        from ultralytics import YOLO
    except ImportError:
        missing.append("ultralytics")
    try:
        import transformers
    except ImportError:
        missing.append("transformers")
    try:
        import easyocr
        _ocr_available = True
    except ImportError:
        pass  # OCR is optional; OmniParser can still detect icons without it.

    if missing:
        raise RuntimeError(
            f"OmniParser not available. Install dependencies: "
            f"pip install {' '.join(missing)}\n"
            f"Full: pip install ultralytics transformers torch easyocr"
        )

    # Load YOLO detection model.
    try:
        from ultralytics import YOLO
        _som_model = YOLO("microsoft/OmniParser-v2.0/icon_detect/model.pt")
    except Exception as e:
        # Try local path if HuggingFace download fails.
        raise RuntimeError(
            f"Failed to load OmniParser YOLO model: {e}\n"
            f"Try: pip install huggingface_hub && "
            f"huggingface-cli download microsoft/OmniParser-v2.0 icon_detect/model.pt "
            f"--local-dir ./weights"
        )

    # Load Florence caption model.
    try:
        from transformers import AutoProcessor, AutoModelForCausalLM
        _caption_processor = {
            "processor": AutoProcessor.from_pretrained(
                "microsoft/Florence-2-large", trust_remote_code=True
            ),
            "model": AutoModelForCausalLM.from_pretrained(
                "microsoft/Florence-2-large", trust_remote_code=True
            ).to(_device).eval(),
        }
    except Exception as e:
        raise RuntimeError(
            f"Failed to load Florence caption model: {e}"
        )

    _OMNIPARSER_AVAILABLE = True


def parse_screenshot(
    image_path: str,
    box_threshold: float = 0.05,
    iou_threshold: float = 0.7,
    max_elements: int = 120,
) -> list[dict[str, Any]]:
    """
    Parse a screenshot and return structured UI elements.

    Args:
        image_path: Path to screenshot PNG file.
        box_threshold: YOLO confidence threshold (lower = more elements).
        iou_threshold: NMS overlap threshold for dedup.
        max_elements: Maximum elements to return.

    Returns:
        List of dicts with keys:
            type: 'icon' or 'text'
            bbox: [x1, y1, x2, y2] in pixel coordinates
            content: label text (e.g. 'Save', 'Close', 'Bold')
            interactivity: bool (True = clickable)
            source: detection source
    """
    _ensure_omniparser()

    import torch
    from PIL import Image

    image = Image.open(image_path).convert("RGB")
    w, h = image.size

    # --- YOLO icon detection ---
    results = _som_model(image, conf=box_threshold, iou=iou_threshold, verbose=False)
    boxes = []
    if results and len(results) > 0:
        for box in results[0].boxes:
            x1, y1, x2, y2 = box.xyxy[0].tolist()
            conf = float(box.conf[0])
            boxes.append({
                "bbox": [x1 / w, y1 / h, x2 / w, y2 / h],
                "confidence": conf,
                "type": "icon",
                "source": "yolo_detect",
            })

    # --- Florence caption for each icon ---
    elements: list[dict[str, Any]] = []
    if boxes and _caption_processor:
        from transformers import AutoProcessor

        processor = _caption_processor["processor"]
        model = _caption_processor["model"]

        for i, box in enumerate(boxes[:max_elements]):
            bx1, by1, bx2, by2 = box["bbox"]
            # Crop region with context
            margin = 0.02
            cx1 = max(0, int((bx1 - margin) * w))
            cy1 = max(0, int((by1 - margin) * h))
            cx2 = min(w, int((bx2 + margin) * w))
            cy2 = min(h, int((by2 + margin) * h))
            crop = image.crop((cx1, cy1, cx2, cy2))

            try:
                inputs = processor(
                    text="<OD>",
                    images=crop,
                    return_tensors="pt",
                ).to(_device)
                generated_ids = model.generate(
                    input_ids=inputs["input_ids"],
                    pixel_values=inputs["pixel_values"],
                    max_new_tokens=20,
                    num_beams=1,
                    do_sample=False,
                )
                caption = processor.batch_decode(
                    generated_ids, skip_special_tokens=True
                )[0]
            except Exception:
                caption = ""

            elements.append({
                "type": "icon",
                "bbox": [
                    int(bx1 * w), int(by1 * h),
                    int(bx2 * w), int(by2 * h),
                ],
                "x": int(bx1 * w),
                "y": int(by1 * h),
                "w": int((bx2 - bx1) * w),
                "h": int((by2 - by1) * h),
                "content": caption.strip(),
                "interactivity": True,
                "source": "omniparser_yolo_florence",
            })

    # --- OCR text extraction ---
    if _ocr_available:
        try:
            import easyocr
            reader = easyocr.Reader(["en", "ch_sim"], gpu=(_device == "cuda"))
            ocr_results = reader.readtext(
                image, paragraph=False, text_threshold=0.9
            )
            for bbox, text, conf in ocr_results:
                if conf < 0.7:
                    continue
                x1 = int(min(p[0] for p in bbox))
                y1 = int(min(p[1] for p in bbox))
                x2 = int(max(p[0] for p in bbox))
                y2 = int(max(p[1] for p in bbox))
                elements.append({
                    "type": "text",
                    "bbox": [x1, y1, x2, y2],
                    "x": x1, "y": y1,
                    "w": x2 - x1, "h": y2 - y1,
                    "content": text,
                    "interactivity": False,
                    "source": "omniparser_ocr",
                })
        except Exception:
            pass  # OCR is best-effort.

    # Sort by position (top-to-bottom, left-to-right).
    elements.sort(key=lambda e: (e["y"], e["x"]))
    elements = elements[:max_elements]

    return elements


def flatten_for_llm(elements: list[dict[str, Any]]) -> str:
    """Format OmniParser elements into a text block the LLM can reason about."""
    if not elements:
        return "(OmniParser found no elements — screen may be empty)"

    lines: list[str] = []
    for i, el in enumerate(elements):
        icon = "🖱️" if el.get("interactivity") else "📝"
        label = el.get("content", "") or f"({el['type']})"
        lines.append(
            f"[id={i}] {icon} {label} "
            f"({el.get('x', 0)},{el.get('y', 0)})~"
            f"({el.get('x', 0) + el.get('w', 0)},{el.get('y', 0) + el.get('h', 0)})"
        )
    return "\n".join(lines)
