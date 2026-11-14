"""Adaptador para PaddleOCR 3.7; fotos procesadas en memoria."""
from io import BytesIO
import os
import numpy as np
from PIL import Image, ImageOps


def create_engine():
    # Solo usamos inferencia: evita registrar repositorios de entrenamiento.
    # Debe configurarse antes de importar PaddleX, incluso en los reintentos.
    os.environ['PADDLE_PDX_EAGER_INIT'] = 'False'
    os.environ['PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK'] = 'True'
    from paddleocr import PaddleOCR
    return PaddleOCR(device='cpu', enable_mkldnn=False,
                     text_detection_model_name='PP-OCRv5_mobile_det',
                     text_recognition_model_name='latin_PP-OCRv5_mobile_rec',
                     cpu_threads=2, text_recognition_batch_size=1,
                     text_det_limit_side_len=960, text_det_limit_type='max',
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
