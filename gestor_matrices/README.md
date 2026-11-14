# Gestor de matrices Word

Aplicación local de Streamlit para guardar y seleccionar matrices de memorándums,
oficios, informes y otros documentos, extraer texto de fotos en español, revisarlo,
completar campos y descargar un Word generado con docxtpl.

## Ejecución

Desde la raíz del repositorio, con el entorno existente:

```bash
.venv/bin/python -m streamlit run gestor_matrices/app.py --server.address 127.0.0.1
```

Abre http://localhost:8501. Si necesitas instalar un entorno nuevo (Python 3.12):

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r gestor_matrices/requirements.txt
.venv/bin/python -m streamlit run gestor_matrices/app.py --server.address 127.0.0.1
```

Versiones verificadas en el entorno: Python 3.12.3, Streamlit 1.67.0,
PaddleOCR 3.7.0, PaddlePaddle 3.3.1, docxtpl 0.20.2 y python-docx 1.2.0.
No se modifica el código fuente de PaddleOCR ni los requisitos del repositorio principal.

## Uso

1. En Word, escribe campos como `{{ destinatario }}`, `{{ asunto }}`,
   `{{ fecha }}` y `{{ cuerpo }}`. Aplica el estilo deseado al campo completo.
2. Sube el .docx, dale un nombre y pulsa **Guardar matriz**. Selecciónalo en la barra lateral.
3. Sube fotos PNG, JPEG o WebP: el OCR se ejecuta automáticamente una vez por conjunto de fotos.
4. Los campos identificables se rellenan y el Word se prepara automáticamente.
5. Descarga el Word. Si faltan datos, la descarga se llama **borrador** e incluye
   un aviso visible y marcas `[PENDIENTE: nombre_del_campo]` dentro del documento.
6. Puedes corregir el texto o los campos: el Word se actualiza automáticamente.
   No hay que marcar una casilla ni pulsar un botón de generación.

El llenado usa reglas locales, sin API de pago: reconoce etiquetas como `Para:`,
`Destinatario:`, `Asunto:`, `Fecha:`, `Cargo del destinatario:`, `Designación:` e
`Instrucciones:`, además del nombre de cada campo con espacios en lugar de guiones
bajos. Admite valores en la línea siguiente y párrafos para asunto e instrucciones.
También propone un asunto a partir del campo de trabajo/actividad y reconoce
destinatario y cargo cuando aparecen juntos en el encabezado. Si la fuente no trae
fecha del documento, propone la fecha actual como fecha de emisión. Estas propuestas
se identifican en pantalla y el Word queda marcado como borrador para revisión.
Reconoce referencias completas de órdenes de trabajo y oficios, incluso si vienen
precedidas por «Referencia:» o «Ref.», y conserva el texto tal como se leyó.
Nunca reutiliza el número de una orden como número de un memorándum: si no encuentra
el número oficial, lo deja marcado para completar. Si las fuentes contienen valores
contradictorios, el campo queda pendiente. No redacta designaciones o instrucciones
que no estén explícitas en la fuente; otros datos que no se puedan inferir se dejan pendientes.
Cambiar fotos o texto inicia un nuevo llenado. Las correcciones manuales de campos
se conservan en las demás interacciones. Un fallo al leer fotos nuevas invalida el
resultado anterior; si solo falla alguna foto, el resultado se marca como borrador.

## Plantillas, formato y almacenamiento

Se admiten campos simples de texto en el cuerpo, tablas, encabezados y pies.
No se admiten expresiones, bucles, filtros, objetos anidados ni inserción de imágenes
mediante campos. Los campos ausentes se marcan en el borrador; escribe «No aplica» solo cuando
corresponda. Las matrices sin campos generan una copia automáticamente.

docxtpl renderiza sobre el documento original, conservando estilos, tablas y estructura
hasta donde permite Word. Textos largos o saltos de línea pueden cambiar la paginación;
revisa el Word final. Evita dar estilos distintos a fragmentos de una misma etiqueta.
El contenido XML se escapa para admitir caracteres como `&` y `<`.

Las matrices persisten en `gestor_matrices/data/matrices/`, con un identificador único
para que nombres repetidos no sobrescriban archivos. El nombre se normaliza para
usarlo como archivo. Las fotos, el texto OCR y el Word generado permanecen en memoria
durante la sesión; el texto y los campos no se guardan al cerrar la sesión.
Para retirar una matriz, elimina su archivo local con la aplicación detenida.

`.gitignore` excluye el directorio de datos, documentos y fotos dentro de esta carpeta,
y `.venv`. Guarda los archivos privados en `data/` si los copias manualmente al proyecto.
La aplicación está pensada para uso local; no incluye autenticación ni separación de
matrices por usuario.

## OCR y verificación

Se utiliza la API PaddleOCR 3.x: `PaddleOCR(lang='es', ocr_version='PP-OCRv5',
device='cpu', ...)`, `predict()` y `rec_texts`. El modelo se carga bajo demanda y se
reutiliza; las inferencias simultáneas se serializan. Las fotos respetan la orientación
EXIF; el enderezado automático está desactivado. Límite: 20 MB y 25 megapíxeles por foto.
La primera extracción requiere conexión para descargar modelos a la caché de PaddleX.
Antes de importar PaddleOCR se establece `PADDLE_PDX_EAGER_INIT=False`: la aplicación
solo usa inferencia y no necesita inicializar anticipadamente los repositorios de
entrenamiento de PaddleX. Esto evita su registro repetido al reintentar una importación.
Tras desplegar esta corrección en Streamlit Cloud, usa **Reboot app** una vez si el
proceso ya mostraba `PDX has already been initialized`; recargar el navegador no
elimina el estado de Python en el servidor. Los errores originales se registran con
su traceback para distinguir fallos de dependencias, descarga e inicialización.
Si falla la descarga o inicialización, se muestra el error y se permite pegar
texto o completar campos manualmente. No se requiere una API de pago ni un servicio remoto para inferencia.

```bash
.venv/bin/python -m unittest discover -s gestor_matrices -v
```

Las pruebas verifican formato Word, escape XML, guardado sin sobrescritura,
reconocimiento de campos, fuentes contradictorias, borradores, conservación de
correcciones, carga automática de fotos e invalidación de documentos anteriores.

Referencias de API:
- https://www.paddleocr.ai/main/en/version3.x/pipeline_usage/OCR.html
- https://docxtpl.readthedocs.io/en/latest/

También se ejecutó una prueba real con una imagen sintética: el OCR devolvió
«Documento para el señor José» correctamente. Se desactiva `enable_mkldnn` en
la configuración porque PaddlePaddle 3.3.1 produjo un error de oneDNN
(`ConvertPirAttribute2RuntimeAttribute`) con la optimización activada en este equipo.
La prueba descargó sus modelos a `/tmp/gestor-matrices-models`; la ejecución normal
utiliza la caché predeterminada. Para reutilizar esos modelos mientras existan:

```bash
PADDLE_PDX_CACHE_HOME=/tmp/gestor-matrices-models .venv/bin/python -m streamlit run gestor_matrices/app.py --server.address 127.0.0.1
```

El reconocimiento de una imagen sintética no garantiza precisión en fotos reales:
revisa nombres, números, fechas y acentos antes de generar el documento.

## Dependencias de Streamlit Community Cloud

El archivo `packages.txt` en la raíz del repositorio instala `libgl1` y
`libglib2.0-0`, que aportan `libGL.so.1` y `libgthread-2.0.so.0` respectivamente
para OpenCV, utilizado por PaddleOCR. Debe mantenerse en la raíz aunque
el punto de entrada sea `gestor_matrices/app.py`. Esta biblioteca es una dependencia
del sistema y no se instala mediante `requirements.txt`.

Al actualizar `packages.txt` en GitHub, Streamlit Cloud reconstruye el entorno.
Si continúa mostrando el error anterior, revisa los registros de instalación y usa
**Manage app → Reboot app** tras completar la reconstrucción.

Referencia: https://docs.streamlit.io/knowledge-base/dependencies/libgl

### OCR en servidores con recursos limitados

Se selecciona explícitamente `PP-OCRv5_mobile_det` en lugar del detector de servidor.
Se conserva el reconocedor latino para español, se limita la detección a 960 píxeles
por lado máximo, se usan dos hilos de CPU y lotes de reconocimiento de una línea.
Esto reduce el consumo de recursos; el texto muy pequeño puede perder precisión.
Se omite la comprobación previa de conectividad a proveedores de modelos, pero se
mantiene la descarga normal cuando los modelos no están en caché.
