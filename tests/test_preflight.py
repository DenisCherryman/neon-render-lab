"""Offline regression checks; no Blender import or network access."""
import ast
import io
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock
from urllib.request import Request

ROOT = Path(__file__).resolve().parents[1]


def module_assignments(filename):
    tree = ast.parse((ROOT / filename).read_text())
    return {
        node.targets[0].id: node.value
        for node in tree.body
        if isinstance(node, ast.Assign)
        and isinstance(node.targets[0], ast.Name)
    }


class Downloads(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        tree = ast.parse((ROOT / 'render.py').read_text())
        functions = ast.Module(body=[
            node for node in tree.body
            if isinstance(node, ast.FunctionDef)
            and node.name in ('fetch', 'download_first')
        ], type_ignores=[])
        self.ns = {'os': os, 'Request': Request, 'ASSET_DIR': self.tmp.name}
        exec(compile(functions, 'render.py', 'exec'), self.ns)
        self.path = os.path.join(self.tmp.name, 'texture')

    def response(self, payload, length=None):
        response = io.BytesIO(payload)
        response.headers = {}
        if length is not None:
            response.headers['Content-Length'] = str(length)
        return response

    def test_truncated_response_never_publishes(self):
        self.ns['urlopen'] = Mock(return_value=self.response(b'bad', 100))
        with self.assertRaises(RuntimeError):
            self.ns['fetch']('https://example.invalid/map', self.path)
        self.assertFalse(os.path.exists(self.path))
        self.assertFalse(os.path.exists(self.path + '.part'))

    def test_invalid_download_preserves_existing_file(self):
        Path(self.path).write_bytes(b'previous')
        self.ns['urlopen'] = Mock(return_value=self.response(b'invalid'))
        validator = Mock(side_effect=RuntimeError('decode failed'))
        with self.assertRaises(RuntimeError):
            self.ns['fetch']('https://example.invalid/map', self.path, validator)
        self.assertEqual(Path(self.path).read_bytes(), b'previous')
        self.assertFalse(os.path.exists(self.path + '.part'))

    def test_bad_cache_and_first_candidate_try_next_candidate(self):
        Path(self.path).write_bytes(b'corrupt')
        self.ns['validate_texture'] = Mock(
            side_effect=[RuntimeError('bad cache'), None]
        )
        self.ns['urlopen'] = Mock(side_effect=[
            OSError('first candidate unavailable'),
            self.response(b'valid image payload'),
        ])
        result = self.ns['download_first'](
            ['https://example.invalid/2k', 'https://example.invalid/1k'],
            'texture',
        )
        self.assertEqual(result, self.path)
        self.assertEqual(Path(self.path).read_bytes(), b'valid image payload')

    def test_exhausted_candidates_raise(self):
        self.ns['validate_texture'] = Mock()
        self.ns['urlopen'] = Mock(side_effect=OSError('offline'))
        with self.assertRaisesRegex(RuntimeError, 'Required texture failed'):
            self.ns['download_first'](['https://example.invalid/map'], 'texture')
        self.assertFalse(os.path.exists(self.path))


class Timeline(unittest.TestCase):
    def test_audio_matches_all_visual_shots(self):
        render = module_assignments('render.py')
        audio = module_assignments('make_audio.py')
        fps = ast.literal_eval(render['FPS'])
        duration = ast.literal_eval(render['DURATION'])
        events = ast.literal_eval(render['SHOT_EVENTS'])
        # Evaluate only the checked-in arithmetic shot-time expression.
        shots = eval(compile(ast.Expression(audio['shots']), 'shots', 'eval'),
                     {'__builtins__': {}}, {})
        self.assertEqual(fps, 24)
        self.assertEqual(duration, 10)
        self.assertEqual(ast.literal_eval(audio['seconds']), duration)
        self.assertEqual(shots, [(frame - 1) / fps for frame, _ in events])
        self.assertEqual(len(events), 12)
        self.assertTrue(all(1 <= frame <= fps * duration for frame, _ in events))
        self.assertTrue(all(actor in (0, 1) for _, actor in events))


if __name__ == '__main__':
    unittest.main()
