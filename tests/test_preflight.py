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
        self.assertEqual(duration, 15)
        self.assertEqual(ast.literal_eval(audio['seconds']), duration)
        self.assertEqual(shots, [(frame - 1) / fps for frame, _ in events])
        self.assertEqual(len(events), 20)
        self.assertTrue(all(1 <= frame <= fps * duration for frame, _ in events))
        self.assertTrue(all(actor in (0, 1) for _, actor in events))


class CinematicTimeline(unittest.TestCase):
    def test_reciprocal_firefight(self):
        events = ast.literal_eval(module_assignments('render.py')['SHOT_EVENTS'])
        self.assertEqual({actor for _,actor in events}, {0,1})
        self.assertTrue(all(a != b for (_,a),(_,b) in zip(events,events[1:])))
        self.assertTrue(all(a < b for (a,_),(b,_) in zip(events,events[1:])))
        src = (ROOT/'render.py').read_text()
        self.assertIn('Beam_to_actor_',src)
        self.assertIn('head = min(1.0,(dt+1)/4)',src)
        self.assertIn('hit = shot+3',src)
        self.assertIn('Impact_actor_',src)
        self.assertIn('other_x, other_y = path_position',src)

    def test_camera_cuts_cover_all_frames(self):
        render = module_assignments('render.py')
        cuts = ast.literal_eval(render['CAMERA_SHOTS'])
        self.assertEqual(cuts[0][0], 1)
        self.assertEqual(cuts[-1][1], 360)
        self.assertTrue(all(a[1] + 1 == b[0] for a,b in zip(cuts, cuts[1:])))
        self.assertTrue(all(start <= end and 20 <= lens <= 60
                            for start,end,_,_,_,_,lens in cuts))

    def test_actor_paths_cover_15_seconds(self):
        render = module_assignments('render.py')
        paths = ast.literal_eval(render['ACTOR_PATHS'])
        self.assertEqual(len(paths), 2)
        self.assertTrue(all(len(path) >= 12 for path in paths))
        for path in paths:
            self.assertEqual(path[0][0], 1)
            self.assertEqual(path[-1][0], 360)
            self.assertTrue(all(a[0] < b[0] for a,b in zip(path, path[1:])))


class PolyHavenChannels(unittest.TestCase):
    def resolve(self, data, channel):
        tree = ast.parse((ROOT / 'render.py').read_text())
        material = next(node for node in tree.body
                        if isinstance(node, ast.FunctionDef)
                        and node.name == 'ph_material')
        urls = next(node for node in material.body
                    if isinstance(node, ast.FunctionDef) and node.name == 'urls')
        namespace = {'data': data, 'asset': 'fixture'}
        exec(compile(ast.Module(body=[urls], type_ignores=[]),
                     'render.py', 'exec'), namespace)
        return namespace['urls'](channel)

    def test_actual_api_capitalization_and_all_candidates(self):
        maps = {
            'Diffuse': {'2k': {'jpg': {'url': '2k.jpg'},
                               'png': {'url': '2k.png'}},
                        '1k': {'jpg': {'url': '1k.jpg'}}},
            'Rough': {'1k': {'png': {'url': 'rough.png'}}},
            'nor_gl': {'1k': {'png': {'url': 'normal.png'}}},
        }
        self.assertEqual(self.resolve(maps, 'diff'),
                         ['2k.jpg', '2k.png', '1k.jpg'])
        self.assertEqual(self.resolve(maps, 'rough'), ['rough.png'])
        self.assertEqual(self.resolve(maps, 'nor_gl'), ['normal.png'])

    def test_missing_required_channel_is_explicit(self):
        with self.assertRaisesRegex(RuntimeError, 'Texture maps available'):
            self.resolve({'Diffuse': {}}, 'nor_gl')


if __name__ == '__main__':
    unittest.main()
