"""Adaptador para PaddleOCR 3.7; fotos procesadas en memoria."""
from io import BytesIO
import numpy as np
from PIL import Image, ImageOps


def create_engine():
    from paddleocr import PaddleOCR
    return PaddleOCR(lang='es', ocr_version='PP-OCRv5', device='cpu', enable_mkldnn=False,
                     use_doc_orientation_classify=False, use_doc_unwarping=False,
                     use_textline_orientation=False)


def extract_text(engine, content):
    with Image.open(BytesIO(content)) as source:
        if source.width * source.height > 25_000_000:
            raise ValueError('La foto supera 25 megapíxeles; reduce su tamaño.')
        image = ImageOps.exif_transpose(source).convert('RGB')
        pixels = np.asarray(image)[:, :, ::-1].copy()  # BGR para PaddleOCR
    lines = []
    for result in engine.predict(pixels):
        if 'rec_texts' not in result:
            raise RuntimeError('PaddleOCR no devolvió rec_texts; revisa las versiones.')
        lines.extend(result['rec_texts'])
    return '\n'.join(lines)
