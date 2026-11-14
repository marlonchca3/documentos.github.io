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
3. Opcionalmente sube fotos PNG, JPEG o WebP y pulsa **Extraer texto**.
4. Revisa y corrige el texto editable. Cada nueva extracción reemplaza ese texto.
5. Copia los datos correspondientes a los campos, revisa la tabla y confirma la revisión.
6. Pulsa **Generar Word** y **Descargar Word**. Si falta un dato, se indica cuál y
   se bloquea la generación. Cambiar valores invalida la descarga anterior.

El OCR extrae texto: **asignarlo automáticamente a los campos requiere lógica adicional**,
como reglas específicas por tipo de documento. Esta aplicación deja esa asignación
al usuario y nunca completa datos por su cuenta.

## Plantillas, formato y almacenamiento

Se admiten campos simples de texto en el cuerpo, tablas, encabezados y pies.
No se admiten expresiones, bucles, filtros, objetos anidados ni inserción de imágenes
mediante campos. Todos los campos detectados son obligatorios; escribe un valor
explícito como «No aplica» solo cuando corresponda. Las matrices sin campos generan
una copia previa confirmación.

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
Si falla la descarga o inicialización, se muestra el error sin impedir completar campos
manualmente. No se requiere una API de pago ni un servicio remoto para inferencia.

```bash
.venv/bin/python -m unittest discover -s gestor_matrices -v
```

Las cinco pruebas verifican campos en cuerpo/tablas/encabezado/pie, negrita y escape XML,
datos faltantes, archivos inválidos y expresiones no admitidas, guardado sin sobrescritura,
el adaptador OCR con resultados simulados y el flujo de revisión/generación de Streamlit.

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
