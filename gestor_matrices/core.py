"""Persistencia y generación de matrices con campos de texto simples."""
from io import BytesIO
from pathlib import Path
import re
from uuid import uuid4
from zipfile import ZipFile
from docxtpl import DocxTemplate
from jinja2 import StrictUndefined
from jinja2.sandbox import SandboxedEnvironment

DATA = Path(__file__).resolve().parent / 'data' / 'matrices'


def environment():
    return SandboxedEnvironment(undefined=StrictUndefined, autoescape=True)


def _extract_field_names_from_xml(xml):
    names = []
    for match in re.finditer(r'{{\s*([^{}]+?)\s*}}', xml):
        expr = match.group(1).strip()
        if not expr:
            continue
        if any(token in expr for token in ('.', '|', '[', ']', '(', ')', ':', '%', ' ', '"', "'")):
            if expr.startswith('if ') or expr.startswith('for ') or expr.startswith('set ') or expr.startswith('macro '):
                raise ValueError('Utiliza solo campos simples {{ nombre }}; no se admiten bucles, filtros ni expresiones.')
            if any(token in expr for token in ('.', '|', '[', ']', '(', ')')):
                raise ValueError('Utiliza solo campos simples {{ nombre }}; no se admiten bucles, filtros ni expresiones.')
        if not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*', expr, re.UNICODE):
            if not re.fullmatch(r'[\w]+', expr, re.UNICODE):
                raise ValueError('Utiliza solo campos simples {{ nombre }}; no se admiten bucles, filtros ni expresiones.')
        names.append(expr)
    return sorted(set(names))


def fields(content):
    if len(content) > 20 * 1024 * 1024:
        raise ValueError('La matriz supera 20 MB.')
    with ZipFile(BytesIO(content)) as archive:
        if sum(i.file_size for i in archive.infolist()) > 100 * 1024 * 1024:
            raise ValueError('La matriz descomprimida supera 100 MB.')
        xml_files = [archive.read(name).decode('utf-8', errors='ignore') for name in archive.namelist() if name.endswith('.xml')]
    names = []
    for xml in xml_files:
        names.extend(_extract_field_names_from_xml(xml))
    return sorted(set(names))


def save_template(name, content, root=DATA):
    name = name.strip()
    if not name or len(name) > 100:
        raise ValueError('Escribe un nombre de entre 1 y 100 caracteres.')
    fields(content)
    root.mkdir(parents=True, exist_ok=True)
    slug = re.sub(r'[^\w -]', '_', name).strip(' .') or 'matriz'
    target = root / f'{slug}--{uuid4().hex}.docx'
    target.write_bytes(content)
    return target


def template_name(path):
    return path.stem.rsplit('--', 1)[0]


def generate(content, values):
    required = fields(content)
    missing = [key for key in required if not values.get(key, '').strip()]
    if missing:
        raise ValueError('Completa los campos: ' + ', '.join(missing))
    template = DocxTemplate(BytesIO(content))
    template.render({key: values[key] for key in required}, jinja_env=environment(), autoescape=True)
    output = BytesIO()
    template.save(output)
    return output.getvalue()
