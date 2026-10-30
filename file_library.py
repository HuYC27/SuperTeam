"""Read-only, bounded metadata index across visible and archived chats."""
import hashlib
import json
import mimetypes
import os
from pathlib import Path
import stat


IMAGE_SUFFIXES = {'.png', '.jpg', '.jpeg', '.webp', '.gif', '.bmp', '.avif',
                  '.tif', '.tiff', '.ico', '.heic', '.heif'}


def _linked(path):
    """Reject Windows junctions/reparse points as well as Unix symlinks."""
    info = path.lstat()
    return stat.S_ISLNK(info.st_mode) or bool(
        getattr(info, 'st_file_attributes', 0) & getattr(stat, 'FILE_ATTRIBUTE_REPARSE_POINT', 0))


def _safe_path(path, base=None):
    # Checking only the leaf or folder.resolve() misses a linked outputs root,
    # provider directory, room directory or ancestor of a custom work folder.
    absolute = path.absolute()
    for part in (absolute, *absolute.parents):
        if _linked(part):
            return False
    return base is None or absolute.resolve().is_relative_to(base.resolve())


class FileLibrary:
    def __init__(self, store, root, *, max_rooms=1000, max_files=5000, max_entries=20000):
        self.store = store
        self.root = Path(root)
        self.max_rooms = max_rooms
        self.max_files = max_files
        self.max_entries = max_entries

    def _append(self, files, item):
        if len(files) >= self.max_files:
            raise ValueError('文件库文件数量超过上限，请先整理文件后再试')
        files.append(item)

    def _outputs(self, room, budget):
        base = self.store.room_folder(room['id'], self.root)
        try:
            if not _safe_path(base):
                return
        except (OSError, RuntimeError):
            return
        for provider in room['members']:
            # Providers normally come from validated Store records. Keep corrupt
            # or hand-edited database values from becoming filesystem paths.
            if not isinstance(provider, str) or provider not in ('codex', 'deepseek', 'workbuddy', 'doubao', 'qwen'):
                continue
            folder = base / provider / 'outputs'
            try:
                if not _safe_path(folder, base) or not folder.is_dir():
                    continue
            except (OSError, RuntimeError):
                continue
            pending = [(folder, 0)]
            while pending:
                current, depth = pending.pop()
                try:
                    if not _safe_path(current, folder):
                        continue
                    with os.scandir(current) as entries:
                        for entry in entries:
                            budget[0] += 1
                            if budget[0] > self.max_entries:
                                raise ValueError('文件库扫描数量超过上限，请先整理成果目录后再试')
                            path = Path(entry.path)
                            try:
                                if not _safe_path(path, folder):
                                    continue
                                info = path.stat()
                                if stat.S_ISDIR(info.st_mode):
                                    if depth >= 32:
                                        raise ValueError('成果目录层级超过上限，请先整理目录后再试')
                                    pending.append((path, depth + 1))
                                elif stat.S_ISREG(info.st_mode):
                                    yield {'name': path.name, 'provider': provider,
                                        'kind': 'image' if path.suffix.lower() in IMAGE_SUFFIXES else 'file',
                                        'mime': mimetypes.guess_type(path.name)[0] or 'application/octet-stream',
                                        'path': path.relative_to(base).as_posix(),
                                        'size': info.st_size, 'created': info.st_mtime}
                            except (OSError, RuntimeError):
                                # Concurrently removed or inaccessible output files
                                # are omitted without exposing local error paths.
                                continue
                except (OSError, RuntimeError):
                    continue

    def artifacts(self, rid):
        """Existing room artifact field contract, sharing the safe scanner."""
        room = self.store.room(rid)
        files = []
        for item in self._outputs(room, [0]):
            self._append(files, item)
        return sorted(files, key=lambda item: (-item['created'], item['path']))

    def snapshot(self):
        # Read minimal room fields rather than loading every chat transcript.
        with self.store.connect() as db:
            rooms = [dict(row) for row in db.execute(
                "SELECT id,name,members FROM rooms WHERE visibility IN ('visible','hidden') ORDER BY created,id LIMIT ?",
                (self.max_rooms + 1,))]
            if len(rooms) > self.max_rooms:
                raise ValueError('文件库会话数量超过上限，请先整理会话后再试')
            count = db.execute("SELECT COUNT(*) FROM attachments JOIN rooms ON rooms.id=attachments.room "
                "WHERE rooms.visibility IN ('visible','hidden')").fetchone()[0]
            if count > self.max_files:
                raise ValueError('文件库文件数量超过上限，请先整理文件后再试')
        files = []
        budget = [0]
        for room in rooms:
            room['members'] = json.loads(room['members'])
            common = {'room': room['id'], 'room_name': room['name']}
            # This public Store API strips original/model paths and extracted
            # attachment text. The explicit field allowlist also omits notes.
            for attachment in self.store.attachments(room['id'], public=True):
                self._append(files, {
                    **{key: attachment[key] for key in ('id', 'name', 'size', 'created', 'kind', 'mime')},
                    **common, 'key': 'uploads:' + room['id'] + ':' + attachment['id'],
                    'source': 'outputs' if attachment.get('note')=='API generated image' else 'uploads', 'artifact': False})
            for output in self._outputs(room, budget):
                identity = json.dumps([room['id'], output['path']], ensure_ascii=False).encode('utf-8')
                self._append(files, {**output, **common,
                    'key': 'outputs:' + hashlib.sha256(identity).hexdigest(),
                    'source': 'outputs', 'artifact': True})
        files.sort(key=lambda item: (-item['created'], item['key']))
        return {'files': files, 'rooms': [{'id': room['id'], 'name': room['name']} for room in rooms]}
