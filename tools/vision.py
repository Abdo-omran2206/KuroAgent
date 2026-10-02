import os
import base64
import mimetypes
from pathlib import Path
from typing import Dict, Any, Tuple, Optional

def get_image_bytes_and_mime(image_path: str) -> Tuple[Optional[bytes], Optional[str], Optional[str]]:
    """
    Validates and reads an image file, returning (raw_bytes, mime_type, error_msg).
    """
    path = Path(image_path).expanduser().resolve()
    if not path.exists():
        return None, None, f"Image file not found: {image_path}"
    if not path.is_file():
        return None, None, f"Path is not a file: {image_path}"

    mime_type, _ = mimetypes.guess_type(str(path))
    if not mime_type or not mime_type.startswith("image/"):
        # Fallback extension check
        ext = path.suffix.lower()
        if ext in (".png", ".apng"):
            mime_type = "image/png"
        elif ext in (".jpg", ".jpeg"):
            mime_type = "image/jpeg"
        elif ext in (".webp",):
            mime_type = "image/webp"
        elif ext in (".gif",):
            mime_type = "image/gif"
        else:
            return None, None, f"Unsupported image format '{ext}'. Supported: png, jpg, jpeg, webp, gif."

    try:
        raw_bytes = path.read_bytes()
        return raw_bytes, mime_type, None
    except Exception as e:
        return None, None, f"Failed to read image file: {str(e)}"


def analyze_image_tool(image_path: str, prompt: str = "Describe this image in detail and highlight key information.") -> Dict[str, Any]:
    """
    Tool function used by KURO agent to inspect local images.
    """
    raw_bytes, mime_type, err = get_image_bytes_and_mime(image_path)
    if err:
        return {"success": False, "error": err}
    
    b64_data = base64.b64encode(raw_bytes).decode("utf-8")
    return {
        "success": True,
        "image_path": str(image_path),
        "mime_type": mime_type,
        "b64_data": b64_data,
        "prompt": prompt,
        "size_kb": round(len(raw_bytes) / 1024, 2)
    }
