import base64
import io
from PIL import Image
import numpy as np
from typing import Optional


def decode_base64_image(image_b64: str) -> np.ndarray:
    """Decode a base64 (or data URL) image string to an RGB numpy array."""
    if not image_b64:
        raise ValueError("Empty image data provided.")
    if ',' in image_b64:
        image_b64 = image_b64.split(',', 1)[1]
    img_bytes = base64.b64decode(image_b64)
    img = Image.open(io.BytesIO(img_bytes)).convert('RGB')
    return np.array(img)


def decode_base64_audio(audio_b64: str) -> bytes:
    """Decode a base64 (or data URL) audio string to raw bytes."""
    if not audio_b64:
        raise ValueError("Empty audio data provided.")
    if ',' in audio_b64:
        audio_b64 = audio_b64.split(',', 1)[1]
    return base64.b64decode(audio_b64)
