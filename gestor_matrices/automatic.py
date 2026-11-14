"""Relleno local con datos explícitos; nunca inventa valores ausentes."""
from collections import defaultdict
from io import BytesIO
import re
import unicodedata

from docx import Document
from core import generate

ALIASES = {
    'destinatario': ('destinatario', 'dirigido a', 'para', 'senor'),
    'cargo_destinatario': ('cargo destinatario', 'cargo del destinatario'),
    'asunto': ('asunto', 'objeto'),
    'fecha': ('fecha', 'fecha del documento'),
    'numero': ('numero', 'numero del documento'),
    'referencia_orden': ('referencia orden', 'referencia de orden'),
    'referencia_oficio': ('referencia oficio', 'referencia de oficio'),
    'parrafo_designacion': ('parrafo designacion', 'designacion'),
    'parrafo_instrucciones': ('parrafo instrucciones', 'instrucciones'),
    'entidad': ('entidad', 'institucion'),
}
MULTILINE = {'asunto', 'parrafo_designacion', 'parrafo_instrucciones', 'cuerpo'}
# Encabezados de tablas OCR: no deben convertirse en el valor del campo anterior.
TABLE_HEADERS = {'hora', 'aeronave', 'modelo', 'n° de serie', 'nº de serie',
                 'fecha de programacion', 'fecha de program', 'trabajo a realizar',
                 'personal', 'firma', 'observaciones'}


def normalize(text):
    text = ''.join(c for c in unicodedata.normalize('NFD', text) if not unicodedata.combining(c))
    return ' '.join(text.lower().replace('_', ' ').split())


def suggest_fields(text, names):
    """Devuelve valores y campos ambiguos. No mezcla valores de varias fuentes."""
    labels = {normalize(alias): field for field, aliases in ALIASES.items() for alias in aliases}
    for name in names:
        labels[normalize(name)] = name
    candidates = defaultdict(list)
    active = None
    chunks = []

    def finish():
        if active and chunks:
            value = '\n'.join(chunks).strip()
            if active == 'numero' and not re.search(r'\d', value):
                return
            candidates[active].append(value)

    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith('--- '):
            finish()
            active, chunks = None, []
            continue
        # Un encabezado explícito delimita un campo, aunque no esté en la matriz.
        match = re.match(r'^([^:]{1,80})\s*:\s*(.*)$', line)
        key = normalize(match[1] if match else line)
        if key in labels:
            finish()
            active, chunks = labels[key], []
            if match and match[2].strip():
                chunks.append(match[2].strip())
                if active not in MULTILINE:
                    finish()
                    active, chunks = None, []
        elif match or key in TABLE_HEADERS:
            finish()
            active, chunks = None, []
        elif active:
            chunks.append(line)
            if active not in MULTILINE:
                finish()
                active, chunks = None, []
    finish()

    # Referencias completas, conservando número y texto tal como los leyó el OCR.
    # No se utiliza el número de la orden como número del nuevo memorándum.
    for line in text.splitlines():
        line = line.strip()
        if line.startswith('--- '):
            continue
        folded = normalize(line)
        if re.match(r'^orden de trabajo\b', folded) and re.search(r'\d', folded):
            candidates['referencia_orden'].append(line)
        elif re.match(r'^oficio\b', folded) and re.search(r'\d', folded):
            candidates['referencia_oficio'].append(line)

    values, conflicts = {}, []
    for name in names:
        unique = {normalize(value): value for value in candidates[name] if value.strip()}
        if len(unique) == 1:
            values[name] = next(iter(unique.values()))
        elif len(unique) > 1:
            conflicts.append(name)
    return values, conflicts


def prepare_word(content, values, incomplete_source=False):
    """Un Word con datos ausentes siempre se identifica como borrador."""
    missing = [name for name, value in values.items() if not value.strip()]
    draft = bool(missing or incomplete_source)
    filled = {name: value.strip() or f'[PENDIENTE: {name}]' for name, value in values.items()}
    result = generate(content, filled)
    if draft:
        doc = Document(BytesIO(result))
        notice = 'BORRADOR — DATOS PENDIENTES DE VERIFICAR'
        if incomplete_source:
            notice += '\nNo se pudieron leer todas las fotos de referencia.'
        if doc.paragraphs:
            doc.paragraphs[0].insert_paragraph_before(notice)
        else:
            paragraph = doc.add_paragraph(notice)
            doc._element.body.insert(0, paragraph._p)
        output = BytesIO()
        doc.save(output)
        result = output.getvalue()
    return result, draft
