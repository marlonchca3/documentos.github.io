"""Persistencia y generación de matrices con campos de texto simples."""
from io import BytesIO
from pathlib import Path
import re
from uuid import uuid4
from zipfile import ZipFile
from docxtpl import DocxTemplate
from jinja2 import StrictUndefined, nodes
from jinja2.sandbox import SandboxedEnvironment

DATA = Path(__file__).resolve().parent / 'data' / 'matrices'


def environment():
    return SandboxedEnvironment(undefined=StrictUndefined, autoescape=True)


def fields(content):
    if len(content) > 20 * 1024 * 1024:
        raise ValueError('La matriz supera 20 MB.')
    with ZipFile(BytesIO(content)) as archive:
        if sum(i.file_size for i in archive.infolist()) > 100 * 1024 * 1024:
            raise ValueError('La matriz descomprimida supera 100 MB.')
    template = DocxTemplate(BytesIO(content))
    template.init_docx()
    parts = [template.get_xml()]
    for kind in ('header', 'footer'):
        parts.extend(template.get_part_xml(part) for _, part in template.get_headers_footers(kind))
    for xml in parts:
        tree = environment().parse(template.patch_xml(xml))
        allowed = (nodes.Template, nodes.Output, nodes.TemplateData, nodes.Name)
        if any(not isinstance(node, allowed) for node in tree.find_all(nodes.Node)):
            raise ValueError('Utiliza solo campos simples {{ nombre }}; no se admiten bucles, filtros ni expresiones.')
    return sorted(template.get_undeclared_template_variables(jinja_env=environment()))


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
