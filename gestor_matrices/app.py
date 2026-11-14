from hashlib import sha256
from importlib.metadata import version
from pathlib import Path
import streamlit as st
from core import DATA, fields, generate, save_template, template_name
from ocr import create_engine, extract_text

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
st.info('El OCR extrae texto; asignarlo automáticamente a los campos requiere lógica adicional. Copia los datos revisados a los campos correspondientes. No se inventan datos.')
photos = st.file_uploader('Fotos de referencia', type=['png', 'jpg', 'jpeg', 'webp'], accept_multiple_files=True)
st.caption('Las fotos se procesan en memoria. La primera extracción puede descargar modelos y tardar varios minutos. Usa fotos orientadas correctamente. Una nueva extracción reemplaza el texto editable.')
if st.button('Extraer texto', disabled=not photos):
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
                    texts.append(f'--- {photo.name} ---\n{text}')
                except Exception as exc:
                    st.error(f'No se pudo procesar {photo.name}: {exc}')
            if texts:
                st.session_state['ocr_text'] = '\n\n'.join(texts)
        except Exception as exc:
            st.error(f'No se pudo iniciar PaddleOCR: {exc}')
            st.info('Comprueba la conexión para descargar modelos y las dependencias de requirements.txt.')
st.text_area('Texto extraído (editable)', key='ocr_text', height=250)

st.subheader('2. Completar y revisar la matriz')
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
values = {name: st.text_area(name, key=f'field:{identity}:{name}', height=85) for name in names}
missing = [name for name, value in values.items() if not value.strip()]
if missing:
    st.warning('Faltan datos. Completa: ' + ', '.join(missing))
if names:
    st.table([{'Campo': name, 'Valor': value or 'Pendiente'} for name, value in values.items()])
revision = sha256(repr((identity, values)).encode()).hexdigest()
reviewed = st.checkbox('He revisado los campos y confirmo que los datos son correctos', key=f'review:{revision}')
if st.button('Generar Word', disabled=bool(missing) or not reviewed):
    try:
        st.session_state['generated'] = (revision, generate(content, values))
    except Exception as exc:
        st.error(f'No se pudo generar el Word: {exc}')
result = st.session_state.get('generated')
if result and result[0] == revision and reviewed:
    st.download_button('Descargar Word', data=result[1], file_name=f'{template_name(Path(selected))}_completado.docx', mime='application/vnd.openxmlformats-officedocument.wordprocessingml.document')
