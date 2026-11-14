import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from datetime import date as Date
from io import BytesIO
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch, Mock
from docx import Document
from automatic import suggest_fields, infer_missing_fields, prepare_word
from test_app import fixture


class AutomaticTests(unittest.TestCase):
    def test_labels_accents_and_multiline(self):
        text = 'DESTINATARIO:\nJosé Pérez\nCargo del destinatario: Jefe\nASUNTO: Revisión\nde equipos\nFecha: 14/11/2026\nInstrucciones: Revisar el equipo.\nInformar el resultado.'
        values, conflicts = suggest_fields(text, ['destinatario', 'cargo_destinatario', 'asunto', 'fecha', 'parrafo_instrucciones'])
        self.assertEqual(values['destinatario'], 'José Pérez')
        self.assertEqual(values['cargo_destinatario'], 'Jefe')
        self.assertEqual(values['asunto'], 'Revisión\nde equipos')
        self.assertEqual(values['parrafo_instrucciones'], 'Revisar el equipo.\nInformar el resultado.')
        self.assertFalse(conflicts)

    def test_references_do_not_invent_memo_data(self):
        text = '--- foto.jpg ---\nORDEN DE TRABAJO DE MANTENIMIENTO N° 087-2026-DIVMAAER\nFECHA DE PROGRAMACIÓN: 14/11/2026\nOFICIO N° 012-2026\n'
        values, _ = suggest_fields(text, ['referencia_orden', 'referencia_oficio', 'numero', 'fecha', 'destinatario'])
        self.assertIn('087-2026', values['referencia_orden'])
        self.assertIn('012-2026', values['referencia_oficio'])
        self.assertNotIn('numero', values)
        self.assertNotIn('fecha', values)
        self.assertNotIn('destinatario', values)

    def test_table_headings_are_not_document_numbers(self):
        for text in ('NUMERO\nHORA\n10:30', 'Numero: HORA', 'Número\nMODELO\nMI-17'):
            values, _ = suggest_fields(text, ['numero'])
            self.assertNotIn('numero', values)
        values, _ = suggest_fields('Número: 058-2026', ['numero'])
        self.assertEqual(values['numero'], '058-2026')

    def test_infers_draft_fields_without_reusing_work_order_number_or_date(self):
        text = (
            'ORDEN DE TRABAJO DE MANTENIMIENTO N° 087-2026-DIVMAAER\n'
            'TRABAJO A REALIZAR:\nInspección del sistema hidráulico\n'
            'Señor Juan Pérez\nJefe de mantenimiento\n'
            'FECHA DE PROGRAMACIÓN: 15/11/2026'
        )
        names = ['asunto', 'cargo_destinatario', 'destinatario', 'fecha', 'numero']
        explicit, _ = suggest_fields(text, names)
        with patch('automatic.date') as mocked_date:
            mocked_date.today.return_value = Date(2026, 11, 14)
            inferred, inferred_names, unresolved_names = infer_missing_fields(text, names, explicit)
        self.assertEqual(inferred['asunto'], 'Inspección del sistema hidráulico')
        self.assertEqual(inferred['destinatario'], 'Juan Pérez')
        self.assertEqual(inferred['cargo_destinatario'], 'Jefe de mantenimiento')
        self.assertEqual(inferred['fecha'], '14/11/2026')
        self.assertEqual(inferred['numero'], '[PENDIENTE: asignar número oficial]')
        self.assertNotIn('087-2026', inferred['numero'])
        self.assertEqual(inferred_names, {'asunto', 'destinatario', 'cargo_destinatario', 'fecha'})
        self.assertEqual(unresolved_names, {'numero'})

    def test_inference_waits_for_source_text(self):
        values, inferred, unresolved = infer_missing_fields(
            '', ['asunto', 'destinatario', 'fecha', 'numero'], {})
        self.assertFalse(values)
        self.assertFalse(inferred)
        self.assertFalse(unresolved)

    def test_conflicting_sources(self):
        values, conflicts = suggest_fields('Para: Ana\n--- otra.jpg ---\nPara: Luis', ['destinatario'])
        self.assertFalse(values)
        self.assertEqual(conflicts, ['destinatario'])
        values, conflicts = suggest_fields('Para: Ana\n--- otra.jpg ---\nPara: Ana', ['destinatario'])
        self.assertEqual(values, {'destinatario': 'Ana'})
        self.assertFalse(conflicts)

    def test_draft_for_unreadable_source(self):
        values = dict(destinatario='José', asunto='Equipo', entidad='Oficina', fecha='14/11/2026')
        data, draft = prepare_word(fixture(), values, incomplete_source=True)
        self.assertTrue(draft)
        self.assertIn('No se pudieron leer todas', Document(BytesIO(data)).paragraphs[0].text)

    def test_inferred_values_keep_word_marked_as_draft(self):
        values = dict(destinatario='Juan Pérez', asunto='Inspección', entidad='Oficina', fecha='14/11/2026')
        data, draft = prepare_word(fixture(), values, inferred_fields={'asunto'})
        self.assertTrue(draft)
        self.assertIn('propuestas automáticas', Document(BytesIO(data)).paragraphs[0].text)

    def test_streamlit_shows_inferred_fields_from_order_text(self):
        import core
        import streamlit as st
        from streamlit.testing.v1 import AppTest
        from core import save_template

        st.cache_resource.clear()
        names = ['asunto', 'cargo_destinatario', 'destinatario', 'fecha', 'numero']
        template = Document()
        for name in names:
            template.add_paragraph('{{ ' + name + ' }}')
        output = BytesIO()
        template.save(output)
        text = (
            'ORDEN DE TRABAJO DE MANTENIMIENTO N° 087-2026-DIVMAAER\n'
            'TRABAJO A REALIZAR:\nInspección del sistema hidráulico\n'
            'Señor Juan Pérez\nJefe de mantenimiento\n'
            'FECHA DE PROGRAMACIÓN: 15/11/2026'
        )
        with TemporaryDirectory() as directory, patch.object(core, 'DATA', Path(directory)):
            save_template('Orden', output.getvalue(), Path(directory))
            app = AppTest.from_file(str(Path(__file__).with_name('app.py')), default_timeout=30).run()
            app.text_area(key='ocr_text').set_value(text).run()
            self.assertFalse(app.exception)
            values = {area.label: area.value for area in app.text_area}
            self.assertEqual(values['asunto'], 'Inspección del sistema hidráulico')
            self.assertEqual(values['destinatario'], 'Juan Pérez')
            self.assertEqual(values['cargo_destinatario'], 'Jefe de mantenimiento')
            self.assertRegex(values['fecha'], r'^\d{2}/\d{2}/\d{4}$')
            self.assertEqual(values['numero'], '[PENDIENTE: asignar número oficial]')
            self.assertTrue(app.session_state['generated'][2])
            generated = Document(BytesIO(app.session_state['generated'][1]))
            generated_text = '\n'.join(paragraph.text for paragraph in generated.paragraphs)
            self.assertIn('[PENDIENTE: asignar número oficial]', generated_text)
            self.assertNotIn('087-2026', generated_text)
        st.cache_resource.clear()

    def test_upload_runs_once_and_failure_invalidates_previous_word(self):
        import core
        import streamlit as st
        from streamlit.testing.v1 import AppTest
        from core import save_template
        st.cache_resource.clear()
        with TemporaryDirectory() as directory, patch.object(core, 'DATA', Path(directory)):
            save_template('Oficio', fixture(), Path(directory))
            with patch('ocr.create_engine', return_value=Mock()), patch('ocr.extract_text') as extract:
                extract.return_value = 'Para: María\nAsunto: Equipo\nEntidad: Oficina\nFecha: 14/11/2026'
                app = AppTest.from_file(str(Path(__file__).with_name('app.py')), default_timeout=30).run()
                app.file_uploader(key='reference_photos').upload('foto.png', b'fake image').run()
                self.assertFalse(app.exception)
                self.assertEqual(extract.call_count, 1)
                self.assertFalse(app.session_state['generated'][2])
                app.run()
                self.assertEqual(extract.call_count, 1)
                extract.side_effect = RuntimeError('imagen dañada')
                app.button(key='retry_ocr').click().run()
                self.assertFalse(app.exception)
                self.assertFalse(app.get('download_button'))
                self.assertEqual(app.session_state['ocr_text'], '')
        st.cache_resource.clear()


if __name__ == '__main__':
    unittest.main()
