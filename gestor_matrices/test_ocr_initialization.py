"""Regresión: configurar PaddleX antes de importar, también tras un fallo."""
import builtins
import os
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from ocr import create_engine


class InitializationTests(unittest.TestCase):
    def test_retry_configures_paddlex_before_import(self):
        original_import = builtins.__import__
        constructor = Mock(return_value=object())
        attempts = []

        def import_module(name, *args, **kwargs):
            if name == 'paddleocr':
                self.assertEqual(os.environ['PADDLE_PDX_EAGER_INIT'], 'False')
                attempts.append(name)
                if len(attempts) == 1:
                    raise ImportError('dependencia no disponible')
                return SimpleNamespace(PaddleOCR=constructor)
            return original_import(name, *args, **kwargs)

        with patch.dict(os.environ, {'PADDLE_PDX_EAGER_INIT': 'True'}):
            with patch('builtins.__import__', side_effect=import_module):
                with self.assertRaisesRegex(ImportError, 'dependencia no disponible'):
                    create_engine()
                self.assertIs(create_engine(), constructor.return_value)
        self.assertEqual(len(attempts), 2)
        self.assertEqual(constructor.call_args.kwargs['lang'], 'es')
        self.assertFalse(constructor.call_args.kwargs['enable_mkldnn'])


if __name__ == '__main__':
    unittest.main()
