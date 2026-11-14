"""Extracción y propuestas locales para preparar borradores verificables."""
from collections import defaultdict
from datetime import date
from io import BytesIO
import re
import unicodedata

from docx import Document
from core import generate

ALIASES = {
    'destinatario': ('destinatario', 'dirigido a', 'para', 'senor'),
    'cargo_destinatario': ('cargo destinatario', 'cargo del destinatario', 'cargo', 'grado', 'puesto'),
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
TASK_LABELS = {'trabajo a realizar', 'actividad a realizar', 'descripcion del trabajo',
               'descripcion de trabajo', 'tarea a realizar'}
PENDING_VALUES = {
    'asunto': '[PENDIENTE: describir el asunto según la orden]',
    'cargo_destinatario': '[PENDIENTE: confirmar cargo del destinatario]',
    'destinatario': '[PENDIENTE: identificar destinatario]',
    'numero': '[PENDIENTE: asignar número oficial]',
}


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


def infer_missing_fields(text, names, explicit_values):
    """Propone campos del borrador solo cuando hay contexto de la fuente."""
    if not text.strip():
        return {}, set(), set()

    lines = [line.strip() for line in text.splitlines() if line.strip() and not line.startswith('--- ')]
    inferred = {}
    inferred_names = set()
    unresolved_names = set()
    normalized_names = {normalize(name): name for name in names}

    def add_inference(field, value):
        name = normalized_names.get(normalize(field))
        if name and name not in explicit_values and value:
            inferred[name] = value
            inferred_names.add(name)

    task = ''
    for index, line in enumerate(lines):
        match = re.match(r'^([^:]{1,80})\s*:\s*(.*)$', line)
        label = normalize(match[1]) if match else normalize(line)
        if label not in TASK_LABELS:
            continue
        task = match[2].strip() if match else ''
        if not task and index + 1 < len(lines):
            next_line = lines[index + 1]
            next_match = re.match(r'^([^:]{1,80})\s*:\s*', next_line)
            if not next_match and normalize(next_line) not in TABLE_HEADERS:
                task = next_line
        if task:
            break

    if task:
        add_inference('asunto', task)
    else:
        order = next((line for line in lines
                      if re.match(r'^orden de trabajo\b', normalize(line))), '')
        if order:
            add_inference('asunto', f'Mantenimiento conforme a: {order}')

    recipient_index = None
    for index, line in enumerate(lines):
        match = re.match(r'^señor(?:a|es)?\.?\s*:?\s*(.+)$', line, re.IGNORECASE)
        if match:
            recipient = match[1].strip()
            if normalize(recipient) not in {'presente', 'a quien corresponda'}:
                add_inference('destinatario', recipient)
                recipient_index = index
                break

    if recipient_index is not None:
        for line in lines[recipient_index + 1:recipient_index + 3]:
            role = re.sub(r'^(?:cargo|grado|puesto)\s*:\s*', '', line, flags=re.IGNORECASE).strip()
            if re.match(r'^(?:jefe|director|comandante|coronel|mayor|capit[aá]n|teniente|ingeniero|supervisor|encargado)\b',
                        role, re.IGNORECASE):
                add_inference('cargo_destinatario', role)
                break

    date_name = normalized_names.get('fecha')
    if date_name and date_name not in explicit_values:
        add_inference('fecha', date.today().strftime('%d/%m/%Y'))

    for field in PENDING_VALUES:
        name = normalized_names.get(normalize(field))
        if name and name not in explicit_values and name not in inferred:
            inferred[name] = PENDING_VALUES[field]
            unresolved_names.add(name)

    return inferred, inferred_names, unresolved_names


def is_pending_value(value):
    return value.strip().startswith('[PENDIENTE:')


def prepare_word(content, values, incomplete_source=False, inferred_fields=()):
    """Un Word con datos ausentes siempre se identifica como borrador."""
    missing = [name for name, value in values.items() if not value.strip() or is_pending_value(value)]
    draft = bool(missing or incomplete_source or inferred_fields)
    filled = {name: value.strip() or f'[PENDIENTE: {name}]' for name, value in values.items()}
    result = generate(content, filled)
    if draft:
        doc = Document(BytesIO(result))
        notice = 'BORRADOR — DATOS PENDIENTES DE VERIFICAR'
        if incomplete_source:
            notice += '\nNo se pudieron leer todas las fotos de referencia.'
        if inferred_fields:
            notice += '\nRevisa las propuestas automáticas antes de utilizar este documento.'
        if doc.paragraphs:
            doc.paragraphs[0].insert_paragraph_before(notice)
        else:
            paragraph = doc.add_paragraph(notice)
            doc._element.body.insert(0, paragraph._p)
        output = BytesIO()
        doc.save(output)
        result = output.getvalue()
    return result, draft
