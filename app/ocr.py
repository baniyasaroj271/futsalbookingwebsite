from pathlib import Path
import re

from flask import current_app


def extract_receipt_text(image_path):
    """Extract text when the optional pytesseract/Tesseract setup is available."""
    try:
        import pytesseract
        from PIL import Image
    except ImportError as exc:
        raise RuntimeError(
            "Receipt scanning requires the optional pytesseract and Pillow packages."
        ) from exc

    tesseract_cmd = current_app.config.get("TESSERACT_CMD")
    if tesseract_cmd:
        pytesseract.pytesseract.tesseract_cmd = tesseract_cmd
    if not Path(image_path).is_file():
        raise FileNotFoundError(f"Receipt image does not exist: {image_path}")
    try:
        return pytesseract.image_to_string(Image.open(image_path))
    except (pytesseract.TesseractNotFoundError, OSError) as exc:
        raise RuntimeError("Tesseract could not process this receipt image.") from exc


def parse_receipt_text(text):
    """Best-effort extraction; values remain editable and never verify payment."""
    amount = re.search(r"(?:total|amount|rs\.?|npr)\s*[:\-]?\s*([0-9][0-9,]*(?:\.[0-9]{1,2})?)", text, re.I)
    reference = re.search(r"(?:reference|transaction|txn|trace)\s*(?:id|no|number)?\s*[:#\-]?\s*([A-Z0-9\-]{5,})", text, re.I)
    transaction_date = re.search(r"\b(\d{4}[-/]\d{1,2}[-/]\d{1,2}|\d{1,2}[-/]\d{1,2}[-/]\d{2,4})\b", text)
    merchant = next(
        (line.strip() for line in text.splitlines() if line.strip()),
        "",
    )
    return {
        "merchant_name": merchant[:180],
        "transaction_date": transaction_date.group(1) if transaction_date else "",
        "amount": amount.group(1) if amount else "",
        "transaction_reference": reference.group(1) if reference else "",
    }
