import importlib
import json
import os
from pathlib import Path
import subprocess
import tempfile
import threading
import unittest
from unittest.mock import patch
import urllib.error
import urllib.request

from core import Store
import server


class FileLibraryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.store = Store(self.root / 'data/history.db')
        self.visible = self.store.create_room('Visible', ['codex'])['id']
        self.hidden = self.store.create_room('Hidden', ['deepseek'])['id']
        self.deleted = self.store.create_room('Deleted', ['codex'])['id']
        self.store.set_visibility(self.hidden, 'hidden')
        self.store.set_visibility(self.deleted, 'deleted')

    def library(self, **kwargs):
        return importlib.import_module('file_library').FileLibrary(self.store, self.root, **kwargs)

    def output(self, room, provider, name='same.txt'):
        path = self.store.room_folder(room, self.root) / provider / 'outputs' / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text('generated fixture', encoding='utf-8')
        return path

    def upload(self, room, aid='upload-one'):
        # No attachment bytes need exist: the index reads public metadata only.
        return self.store.add_attachment(room, aid, 'same.txt', 'text/plain', 'file',
            str(self.root / 'private-original.txt'), 20, 'PRIVATE BODY',
            'private extractor note', str(self.root / 'private-preview.png'))

    def test_collects_visible_hidden_uploads_and_outputs_excludes_deleted(self):
        for room, provider in [(self.visible, 'codex'), (self.hidden, 'deepseek'), (self.deleted, 'codex')]:
            self.upload(room, room)
            self.output(room, provider)
        result = self.library().snapshot()
        self.assertEqual({r['id'] for r in result['rooms']}, {self.visible, self.hidden})
        self.assertEqual(len(result['files']), 4)
        self.assertEqual({f['room'] for f in result['files']}, {self.visible, self.hidden})
        self.assertEqual({f['source'] for f in result['files']}, {'uploads', 'outputs'})
        self.assertEqual({f['room_name'] for f in result['files']}, {'Visible', 'Hidden'})

    def test_same_names_have_stable_unique_keys_and_no_private_paths_or_bodies(self):
        self.upload(self.visible)
        self.output(self.visible, 'codex')
        self.output(self.hidden, 'deepseek')
        library = self.library()
        first = library.snapshot()['files']
        self.assertEqual(len({f['key'] for f in first}), 3)
        self.assertEqual([f['key'] for f in first], [f['key'] for f in library.snapshot()['files']])
        serialized = json.dumps(first)
        self.assertNotIn(str(self.root).replace('\\', '\\\\'), serialized)
        self.assertNotIn('PRIVATE BODY', serialized)
        self.assertNotIn('private extractor note', serialized)
        for item in first:
            self.assertTrue({'name', 'size', 'created', 'kind', 'mime', 'room', 'room_name', 'source', 'artifact'} <= item.keys())
            if item['artifact']:
                self.assertFalse(Path(item['path']).is_absolute())
                self.assertEqual(item['path'].split('/')[1], 'outputs')
            else:
                self.assertEqual(item['id'], 'upload-one')
                self.assertNotIn('path', item)
                self.assertNotIn('model_path', item)

    def test_custom_room_folder_and_nested_outputs_are_supported(self):
        custom = self.root / 'custom-chat-folder'
        with self.store.connect() as db:
            db.execute('UPDATE rooms SET work_folder=? WHERE id=?', (str(custom), self.visible))
        self.output(self.visible, 'codex', 'nested/figure.png')
        # A file outside outputs must never enter the results library.
        (custom / 'codex/secret.txt').write_text('private', encoding='utf-8')
        items = self.library().snapshot()['files']
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]['path'], 'codex/outputs/nested/figure.png')
        self.assertEqual(items[0]['kind'], 'image')
        self.assertEqual(items[0]['mime'], 'image/png')

    def link_directory(self, link, target):
        try:
            link.symlink_to(target, target_is_directory=True)
        except OSError:
            if os.name != 'nt':
                self.skipTest('Directory symlinks unavailable')
            # Windows junctions do not require Developer Mode or elevation.
            completed = subprocess.run(['cmd', '/c', 'mklink', '/J', str(link), str(target)], capture_output=True)
            if completed.returncode:
                self.skipTest('Directory junctions unavailable')

    def test_rejects_linked_output_root_and_nested_directory(self):
        outside = self.root / 'outside'
        outside.mkdir()
        (outside / 'secret.txt').write_text('outside', encoding='utf-8')
        base = self.store.room_folder(self.visible, self.root)
        (base / 'codex').mkdir(parents=True)
        self.link_directory(base / 'codex/outputs', outside)
        normal = self.output(self.hidden, 'deepseek')
        self.link_directory(normal.parent / 'escaped', outside)
        items = self.library().snapshot()['files']
        self.assertEqual([(f['room'], f['name']) for f in items], [(self.hidden, 'same.txt')])

    def test_rejects_linked_room_ancestor(self):
        outside = self.root / 'outside'
        (outside / 'room/codex/outputs').mkdir(parents=True)
        (outside / 'room/codex/outputs/secret.txt').write_text('outside', encoding='utf-8')
        self.link_directory(self.root / 'linked-parent', outside)
        with self.store.connect() as db:
            db.execute('UPDATE rooms SET work_folder=? WHERE id=?', (str(self.root / 'linked-parent/room'), self.visible))
        self.assertEqual(self.library().snapshot()['files'], [])

    def test_rejects_linked_provider_directory(self):
        outside = self.root / 'outside'
        (outside / 'outputs').mkdir(parents=True)
        (outside / 'outputs/secret.txt').write_text('outside', encoding='utf-8')
        base = self.store.room_folder(self.visible, self.root)
        base.mkdir(parents=True)
        self.link_directory(base / 'codex', outside)
        self.assertEqual(self.library().snapshot()['files'], [])

    def test_bounds_total_files_and_scanned_directory_entries(self):
        self.output(self.visible, 'codex', 'one.txt')
        self.output(self.visible, 'codex', 'two.txt')
        with self.assertRaisesRegex(ValueError, '文件.*上限'):
            self.library(max_files=1).snapshot()
        with self.assertRaisesRegex(ValueError, '扫描.*上限'):
            self.library(max_entries=1).snapshot()

    def test_bounds_uploads_and_rooms_before_full_metadata_loading(self):
        self.upload(self.visible, 'one')
        self.upload(self.hidden, 'two')
        with self.assertRaisesRegex(ValueError, '文件.*上限'):
            self.library(max_files=1).snapshot()
        with self.assertRaisesRegex(ValueError, '会话.*上限'):
            self.library(max_rooms=1).snapshot()


class FileLibraryHttpTests(unittest.TestCase):
    def test_library_endpoint_uses_existing_auth_and_keeps_room_artifacts(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch.object(server, 'ROOT', Path(directory)):
                httpd, token, service = server.make_server(discover_models=False)
            thread = threading.Thread(target=httpd.serve_forever, daemon=True)
            thread.start()
            try:
                base = 'http://127.0.0.1:' + str(httpd.server_port)
                for headers in [{}, {'X-App-Token': token, 'Origin': 'https://example.com'}]:
                    request = urllib.request.Request(base + '/api/library', headers=headers)
                    with self.assertRaises(urllib.error.HTTPError) as denied:
                        urllib.request.urlopen(request)
                    self.assertEqual(denied.exception.code, 403)
                room = service.store.list_rooms()[0]
                output = service.store.room_folder(room['id'], Path(directory)) / room['members'][0] / 'outputs/report.txt'
                output.parent.mkdir(parents=True)
                output.write_text('fixture', encoding='utf-8')
                request = urllib.request.Request(base + '/api/library', headers={'X-App-Token': token})
                with urllib.request.urlopen(request) as response:
                    result = json.load(response)
                self.assertEqual(len(result['files']), 1)
                self.assertEqual(result['files'][0]['room'], room['id'])
                request = urllib.request.Request(base + '/api/room?id=' + room['id'], headers={'X-App-Token': token})
                with urllib.request.urlopen(request) as response:
                    self.assertEqual(json.load(response)['artifacts'][0]['path'], result['files'][0]['path'])
                # Room artifacts and the global library share the same allowlist,
                # including results beyond the former per-room 100-file cutoff.
                for index in range(105):
                    (output.parent / f'result-{index}.txt').write_text('fixture', encoding='utf-8')
                request = urllib.request.Request(base + '/api/library', headers={'X-App-Token': token})
                with urllib.request.urlopen(request) as response:
                    files = json.load(response)['files']
                self.assertEqual(len(files), 106)
                from urllib.parse import urlencode
                request = urllib.request.Request(base + '/api/artifact?' + urlencode({
                    'room': files[-1]['room'], 'path': files[-1]['path']}), headers={'X-App-Token': token})
                with urllib.request.urlopen(request) as response:
                    self.assertEqual(response.read(), b'fixture')
                request=urllib.request.Request(base+'/api/artifact?'+urlencode({'room':files[-1]['room'],'path':files[-1]['path'],'text':1}),headers={'X-App-Token':token})
                with urllib.request.urlopen(request) as response:self.assertEqual(json.load(response)['text'],'fixture')
            finally:
                httpd.shutdown()
                httpd.server_close()
                thread.join()


if __name__ == '__main__':
    unittest.main()
