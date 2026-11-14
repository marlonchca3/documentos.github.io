import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from io import BytesIO
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import Mock
from docx import Document
from PIL import Image
from core import fields, generate, save_template
from ocr import extract_text


def fixture():
    doc = Document()
    run = doc.add_paragraph().add_run('{{ destinatario }}')
    run.bold = True
    doc.add_table(rows=1, cols=1).cell(0, 0).text = '{{ asunto }}'
    doc.sections[0].header.paragraphs[0].text = '{{ entidad }}'
    doc.sections[0].footer.paragraphs[0].text = '{{ fecha }}'
    out = BytesIO()
    doc.save(out)
    return out.getvalue()


class WorkflowTests(unittest.TestCase):
    def test_fields_format_and_escaping(self):
        content = fixture()
        self.assertEqual(fields(content), ['asunto', 'destinatario', 'entidad', 'fecha'])
        result = generate(content, dict(asunto='A < B & C', destinatario='María', entidad='Oficina', fecha='13/11/2026'))
        doc = Document(BytesIO(result))
        self.assertEqual(doc.paragraphs[0].text, 'María')
        self.assertTrue(doc.paragraphs[0].runs[0].bold)
        self.assertEqual(doc.tables[0].cell(0, 0).text, 'A < B & C')
        self.assertEqual(doc.sections[0].header.paragraphs[0].text, 'Oficina')
        self.assertEqual(doc.sections[0].footer.paragraphs[0].text, '13/11/2026')

    def test_missing_and_invalid(self):
        with self.assertRaisesRegex(ValueError, 'Completa'):
            generate(fixture(), {'destinatario': ' '})
        with self.assertRaises(Exception):
            fields(b'not a docx')
        doc = Document()
        doc.add_paragraph('{{ persona.nombre }}')
        output = BytesIO()
        doc.save(output)
        with self.assertRaisesRegex(ValueError, 'simples'):
            fields(output.getvalue())

    def test_storage_no_overwrite(self):
        with TemporaryDirectory() as folder:
            root = Path(folder)
            first = save_template('../Oficio', fixture(), root)
            second = save_template('../Oficio', fixture(), root)
            self.assertNotEqual(first, second)
            self.assertEqual(first.parent, root)
            self.assertEqual(fields(first.read_bytes()), fields(second.read_bytes()))

    def test_ocr_adapter(self):
        data = BytesIO()
        Image.new('RGB', (20, 20), 'red').save(data, format='PNG')
        engine = Mock()
        engine.predict.return_value = [{'rec_texts': ['Señor', 'José']}]
        self.assertEqual(extract_text(engine, data.getvalue()), 'Señor\nJosé')
        self.assertEqual(engine.predict.call_args.args[0][0, 0].tolist(), [0, 0, 255])

    def test_streamlit_flow(self):
        from streamlit.testing.v1 import AppTest
        import core
        with TemporaryDirectory() as folder:
            original = core.DATA
            core.DATA = Path(folder)
            try:
                save_template('Oficio', fixture(), core.DATA)
                app = AppTest.from_file(str(Path(__file__).with_name('app.py')), default_timeout=30).run()
                self.assertFalse(app.exception)
                app.text_area(key='ocr_text').set_value('Destinatario: María\nAsunto: A < B & C\nEntidad: Oficina\nFecha: 14/11/2026').run()
                self.assertFalse(app.exception)
                result = app.session_state['generated']
                self.assertFalse(result[2])
                self.assertEqual(Document(BytesIO(result[1])).paragraphs[0].text, 'María')
                self.assertTrue(app.get('download_button'))
                next(a for a in app.text_area if a.label == 'asunto').set_value('Corregido').run()
                app.run()
                self.assertEqual(next(a for a in app.text_area if a.label == 'asunto').value, 'Corregido')
                self.assertEqual(Document(BytesIO(app.session_state['generated'][1])).tables[0].cell(0, 0).text, 'Corregido')
                next(a for a in app.text_area if a.label == 'asunto').set_value('').run()
                self.assertTrue(app.session_state['generated'][2])
                doc = Document(BytesIO(app.session_state['generated'][1]))
                self.assertIn('BORRADOR', doc.paragraphs[0].text)
                self.assertEqual(doc.tables[0].cell(0, 0).text, '[PENDIENTE: asunto]')
                app.text_area(key='ocr_text').set_value('Destinatario: Luis').run()
                self.assertEqual(next(a for a in app.text_area if a.label == 'destinatario').value, 'Luis')
                self.assertEqual(next(a for a in app.text_area if a.label == 'fecha').value, '')
                self.assertFalse(app.exception)
            finally:
                core.DATA = original


if __name__ == '__main__':
    unittest.main()
