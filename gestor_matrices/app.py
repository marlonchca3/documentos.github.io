from hashlib import sha256
from importlib.metadata import version
from pathlib import Path
import logging
import streamlit as st
from core import DATA, fields, save_template, template_name
from ocr import create_engine, extract_text
from automatic import (
    suggest_fields, infer_missing_fields, prepare_word, normalize,
    is_pending_value, TABLE_HEADERS,
)

st.set_page_config(page_title='Gestor de matrices Word', page_icon='📄', layout='wide')
st.title('Gestor de matrices Word')
st.caption('Memorándums, oficios, informes y otros documentos a partir de tus matrices.')


@st.cache_resource
def ocr_engine():
    from threading import Lock
    return create_engine(), Lock()


with st.sidebar:
    st.header('Matrices guardadas')
    with st.form('upload_template', clear_on_submit=True):
        name = st.text_input('Nombre de la matriz', max_chars=100)
        uploaded = st.file_uploader('Matriz de Word', type=['docx'])
        save = st.form_submit_button('Guardar matriz')
    if save:
        try:
            if uploaded is None:
                raise ValueError('Selecciona un archivo .docx.')
            saved = save_template(name, uploaded.getvalue())
            st.session_state['selected_template'] = str(saved)
            st.success('Matriz guardada.')
        except Exception as exc:
            st.error(f'No se pudo guardar la matriz: {exc}')
    paths = sorted(DATA.glob('*.docx'), key=lambda p: p.name.casefold())
    selected = st.selectbox('Seleccionar matriz', [str(p) for p in paths],
                            format_func=lambda p: template_name(Path(p)), key='selected_template')
    with st.expander('Versiones instaladas'):
        for package in ('streamlit', 'paddleocr', 'paddlepaddle', 'docxtpl', 'python-docx'):
            st.text(f'{package}: {version(package)}')

st.subheader('1. Extraer y revisar texto de fotos')
st.info('Selecciona una matriz y sube las fotos: extraeremos el texto, completaremos los datos identificables y prepararemos el Word. Si faltan datos, obtendrás un borrador con marcas PENDIENTE.')
photos = st.file_uploader('Fotos de referencia', type=['png', 'jpg', 'jpeg', 'webp'], accept_multiple_files=True, key='reference_photos')
st.caption('El procesamiento comienza al subir las fotos. Puedes corregir el texto y los campos. Cambiar las fotos o el texto inicia un nuevo llenado; las correcciones de campos se conservan mientras no cambie la fuente.')
photo_signature = sha256(repr([(p.name, sha256(p.getvalue()).hexdigest()) for p in photos]).encode()).hexdigest() if photos else None
retry = st.button('Volver a extraer', disabled=not photos, key='retry_ocr')
if not photos and st.session_state.get('photo_signature'):
    st.session_state['ocr_text'] = ''
    st.session_state['photo_signature'] = None
    st.session_state['ocr_incomplete'] = False
if photos and (retry or st.session_state.get('photo_signature') != photo_signature):
    st.session_state['photo_signature'] = photo_signature
    st.session_state['ocr_text'] = ''
    st.session_state['ocr_incomplete'] = False
    texts = []
    with st.spinner('Extrayendo texto en español…'):
        try:
            engine, lock = ocr_engine()
            for photo in photos:
                try:
                    if photo.size > 20 * 1024 * 1024:
                        raise ValueError('La foto supera 20 MB.')
                    with lock:
                        text = extract_text(engine, photo.getvalue())
                    if not text.strip():
                        st.warning(f'No se encontró texto en {photo.name}.')
                        st.session_state['ocr_incomplete'] = True
                    texts.append(f'--- {photo.name} ---\n{text}')
                except Exception as exc:
                    st.error(f'No se pudo procesar {photo.name}: {exc}')
                    st.session_state['ocr_incomplete'] = True
            if texts:
                st.session_state['ocr_text'] = '\n\n'.join(texts)
        except Exception as exc:
            st.session_state['ocr_incomplete'] = True
            logging.getLogger(__name__).exception('No se pudo iniciar PaddleOCR')
            st.error(f'No se pudo iniciar PaddleOCR: {exc}')
            if 'PDX has already been initialized' in str(exc):
                st.info('El proceso conserva una inicialización anterior de PaddleX. '
                        'Reinicia la aplicación desde Streamlit Cloud (Reboot app) '
                        'para aplicar la configuración de OCR. Recargar la página no reinicia el servidor.')
            else:
                st.info('Consulta el registro del servidor para ver la causa original. '
                        'Comprueba las dependencias y la conexión si el registro indica un fallo de descarga.')
st.text_area('Texto extraído (editable)', key='ocr_text', height=250)

st.subheader('2. Word preparado automáticamente')
if not selected:
    st.info('Sube y nombra una matriz .docx para continuar. Ejemplo de campo: {{ destinatario }}.')
    st.stop()
try:
    content = Path(selected).read_bytes()
    names = fields(content)
except Exception as exc:
    st.error(f'No se pudo leer la matriz: {exc}')
    st.stop()
identity = sha256(content).hexdigest() + Path(selected).stem
if not names:
    st.warning('Esta matriz no contiene campos: se generará una copia de su contenido.')
source_text = st.session_state.get('ocr_text', '')
source_id = sha256(source_text.encode()).hexdigest()
suggestions, conflicts = suggest_fields(source_text, names)
inference_source = {**suggestions, **{name: '' for name in conflicts}}
inferred_values, inferred_fields, unresolved_fields = infer_missing_fields(
    source_text, names, inference_source)
suggestions.update(inferred_values)
if conflicts:
    st.warning('Hay valores distintos para estos campos; elige el correcto: ' + ', '.join(conflicts))
values = {}
with st.expander('Revisar o corregir campos', expanded=True):
    for name in names:
        key = f'field:{identity}:{source_id}:{name}'
        if key not in st.session_state:
            st.session_state[key] = suggestions.get(name, '')
        if name == 'numero' and normalize(st.session_state[key]) in TABLE_HEADERS:
            st.session_state[key] = ''
        values[name] = st.text_area(name, key=key, height=85)
        if name in inferred_fields:
            st.caption('Propuesta automática según el contexto; revisa antes de usar.')
        elif name in unresolved_fields:
            st.caption('No se puede deducir de la foto; completa este dato manualmente.')
missing = [name for name, value in values.items() if not value.strip() or is_pending_value(value)]
if missing:
    st.warning('El borrador marcará como PENDIENTE: ' + ', '.join(missing))
if names:
    st.table([{'Campo': name, 'Valor': 'PENDIENTE' if not value.strip() or is_pending_value(value) else value}
              for name, value in values.items()])
incomplete = st.session_state.get('ocr_incomplete', False)
revision = sha256(repr((identity, values, incomplete, sorted(inferred_fields))).encode()).hexdigest()
if source_text.strip() or any(value.strip() for value in values.values()) or not names:
    result = st.session_state.get('generated')
    if not result or result[0] != revision:
        try:
            document, draft = prepare_word(
                content, values, incomplete_source=incomplete, inferred_fields=inferred_fields)
            st.session_state['generated'] = (revision, document, draft)
        except Exception as exc:
            st.error(f'No se pudo generar el Word: {exc}')
    result = st.session_state.get('generated')
    if result and result[0] == revision:
        draft = result[2]
        st.success('Borrador preparado. Los datos ausentes están marcados dentro del Word.' if draft else 'Word preparado. Revisa los datos reconocidos antes de utilizarlo.')
        st.download_button('Descargar borrador Word' if draft else 'Descargar Word', data=result[1],
                           file_name=f"{template_name(Path(selected))}_{'borrador' if draft else 'completado'}.docx",
                           mime='application/vnd.openxmlformats-officedocument.wordprocessingml.document')
else:
    st.info('Sube las fotos o pega el texto de referencia para preparar el Word automáticamente.')
