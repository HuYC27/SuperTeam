"""User-invoked native desktop services; never grants chat/agent permissions."""
from pathlib import Path
import codecs
import ctypes
import locale
import os
import queue
import re
import shutil
import subprocess
import threading
import time


def failure(message, supported=True):
    return {'ok': False, 'supported': supported, 'error': str(message)}


class NativeServices:
    def __init__(self, root, activate=None, popout=None, buffer_limit=262144):
        self.root = Path(root)
        self.activate = activate or (lambda: None)
        self.popout_callback = popout or (lambda: None)
        self._terminal = None
        self._terminal_lock = threading.RLock()
        self._output_lock = threading.Lock()
        self._output = ''
        self._output_end = 0
        self._buffer_limit = buffer_limit
        self._hotkey = None
        self._notifications = set()
        self._shutdown = threading.Event()

    def _shell(self, name):
        if name not in ('powershell', 'cmd', 'pwsh'):
            raise ValueError('Unsupported terminal shell')
        if os.name != 'nt':
            raise OSError('Windows terminals are unavailable on this platform')
        executable = shutil.which(name + '.exe')
        if not executable:
            raise OSError(name + ' is not installed')
        return executable

    def capabilities(self):
        shells = []
        for name in ('powershell', 'cmd', 'pwsh'):
            try:
                self._shell(name)
                shells.append(name)
            except (ValueError, OSError):
                pass
        return {'ok': True, 'platform': 'windows' if os.name == 'nt' else os.name,
                'shells': shells, 'globalHotkey': os.name == 'nt', 'notifications': os.name == 'nt',
                'terminal': bool(shells), 'vscode': bool(self._vscode()), 'terminalMode': 'pipe',
                'terminalNote': 'Interactive command input/output; full-screen TUI programs require a separate terminal window.'}

    @staticmethod
    def _path(value, directory=False):
        if not isinstance(value, str) or not value or value.startswith(('\\\\', '//')):
            raise ValueError('Choose an existing absolute local path')
        path = Path(value).expanduser()
        if not path.is_absolute():
            raise ValueError('An absolute local path is required')
        path = path.resolve(strict=True)
        if str(path).startswith(('\\\\', '//')):
            raise ValueError('Network paths are not supported')
        if directory and not path.is_dir():
            raise ValueError('Choose an existing directory')
        return str(path)

    def open_terminal(self, path, shell='powershell', location='panel'):
        if location == 'panel':
            return self.terminal_start(path, shell)
        if location != 'window':
            return failure('Unsupported terminal location')
        try:
            directory = self._path(path, True)
            executable = self._shell(shell)
            args = [executable, '/K'] if shell == 'cmd' else [executable, '-NoLogo', '-NoExit']
            subprocess.Popen(args, cwd=directory, creationflags=getattr(subprocess, 'CREATE_NEW_CONSOLE', 0), shell=False)
            return {'ok': True, 'location': 'window', 'path': directory, 'shell': shell}
        except (OSError, ValueError) as exc:
            return failure(exc, os.name == 'nt')

    def _append_output(self, text):
        with self._output_lock:
            self._output_end += len(text)
            self._output = (self._output + text)[-self._buffer_limit:]

    def terminal_start(self, path, shell='powershell'):
        with self._terminal_lock:
            if self._terminal and self._terminal.poll() is None:
                return failure('A panel terminal is already running; stop it before starting another')
            try:
                directory = self._path(path, True)
                executable = self._shell(shell)
                args = [executable, '/Q', '/K'] if shell == 'cmd' else [executable, '-NoLogo', '-NoProfile', '-NoExit', '-Command', '-']
                proc = subprocess.Popen(args, cwd=directory, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                        stderr=subprocess.STDOUT, bufsize=0, shell=False,
                                        creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
                self._terminal = proc
                self._terminal_encoding = locale.getencoding()
                with self._output_lock:
                    self._output = ''
                    self._output_end = 0
                threading.Thread(target=self._read_output, args=(proc,), daemon=True, name='native-terminal').start()
                return {'ok': True, 'running': True, 'location': 'panel', 'path': directory, 'shell': shell,
                        'mode': 'pipe', 'note': 'Use a separate terminal window for full-screen TUI programs.'}
            except (OSError, ValueError) as exc:
                return failure(exc, os.name == 'nt')

    def _read_output(self, proc):
        decoder = codecs.getincrementaldecoder(self._terminal_encoding)(errors='replace')
        try:
            while True:
                data = proc.stdout.read(1)
                if not data:
                    break
                self._append_output(decoder.decode(data))
            self._append_output(decoder.decode(b'', final=True))
        except (OSError, ValueError):
            pass
        finally:
            try:
                proc.stdout.close()
            except (OSError, ValueError):
                pass

    def terminal_write(self, text):
        if not isinstance(text, str) or len(text) > 65536 or '\0' in text:
            return failure('Terminal input must be text under 64 KiB without NUL characters')
        with self._terminal_lock:
            if not self._terminal or self._terminal.poll() is not None:
                return failure('The panel terminal is not running')
            try:
                data = text.encode(getattr(self, '_terminal_encoding', locale.getencoding()), errors='replace')
                try:
                    self._terminal.stdin.write(data)
                except TypeError:  # Text streams supplied by embedding callers.
                    self._terminal.stdin.write(text)
                self._terminal.stdin.flush()
                return {'ok': True}
            except (OSError, ValueError) as exc:
                return failure(exc)

    def terminal_read(self, cursor=0):
        try:
            cursor = max(0, int(cursor))
        except (TypeError, ValueError):
            return failure('Invalid terminal cursor')
        with self._output_lock:
            start = self._output_end - len(self._output)
            offset = min(len(self._output), max(0, cursor - start))
            return {'ok': True, 'text': self._output[offset:], 'cursor': self._output_end,
                    'truncated': cursor < start or cursor > self._output_end,
                    'running': bool(self._terminal and self._terminal.poll() is None)}

    def terminal_stop(self):
        with self._terminal_lock:
            proc, self._terminal = self._terminal, None
            if proc:
                try:
                    if proc.poll() is None:
                        proc.terminate()
                        try:
                            proc.wait(timeout=2)
                        except subprocess.TimeoutExpired:
                            proc.kill()
                    if proc.stdin:
                        proc.stdin.close()
                except (OSError, ValueError):
                    pass
            return {'ok': True}

    @staticmethod
    def _vscode():
        # Launch Code.exe directly: code.cmd would require unsafe cmd.exe quoting.
        candidates = [Path(os.environ.get('LOCALAPPDATA', ''))/'Programs/Microsoft VS Code/Code.exe',
                      Path(os.environ.get('ProgramFiles', 'C:/Program Files'))/'Microsoft VS Code/Code.exe']
        found = shutil.which('Code.exe')
        return found or next((str(path) for path in candidates if path.is_file()), None)

    def open_file(self, path, destination='system'):
        if destination not in ('system', 'vscode'):
            return failure('Unsupported file destination')
        try:
            path = self._path(path)
            if destination == 'vscode':
                executable = self._vscode()
                if not executable:
                    return failure('Visual Studio Code is not installed', False)
                subprocess.Popen([executable, '--', path], shell=False,
                                 creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
            elif os.name == 'nt':
                os.startfile(path)
            else:
                return failure('System file opening is unavailable on this platform', False)
            return {'ok': True, 'path': path, 'destination': destination}
        except (OSError, ValueError) as exc:
            return failure(exc)

    def set_popout_hotkey(self, chord):
        if not isinstance(chord, str) or (chord and not re.fullmatch(r'Ctrl\+Alt\+[A-Za-z]', chord)):
            return failure('Use Ctrl+Alt+ followed by one letter, or an empty value to disable')
        if not chord:
            if self._hotkey:
                self._hotkey.stop()
                self._hotkey = None
            return {'ok': True, 'chord': ''}
        if os.name != 'nt':
            return failure('Global shortcuts are supported on Windows only', False)
        if self._hotkey and self._hotkey.chord.lower() == chord.lower():
            return {'ok': True, 'chord': self._hotkey.chord}
        new_hotkey = _GlobalHotkey(chord, self.popout_callback)
        error = new_hotkey.start()
        if error:
            return failure(error)
        old, self._hotkey = self._hotkey, new_hotkey
        if old:
            old.stop()
        return {'ok': True, 'chord': chord}

    def notify(self, title='SuperTeam', body='A task needs your attention.', sound=False):
        if os.name != 'nt':
            return failure('Native notifications are supported on Windows only', False)
        if not isinstance(title, str) or not isinstance(body, str):
            return failure('Notification title and body must be text')
        if self._shutdown.is_set():
            return failure('The desktop window has closed')
        # Callers supply generic task events, never transcript text by default.
        ready, result = threading.Event(), {}
        thread = threading.Thread(target=_balloon_notification,
                                  args=(title[:63], body[:255], bool(sound), self.activate, ready, result, self._shutdown),
                                  daemon=True, name='native-notification')
        thread.start()
        if not ready.wait(3):
            return failure('Windows notification initialization timed out')
        return result

    def shutdown(self):
        self._shutdown.set()
        self.set_popout_hotkey('')
        self.terminal_stop()


class _GlobalHotkey:
    """Registration, message loop and unregister all run on the owning thread."""
    def __init__(self, chord, callback):
        self.chord, self.callback = chord, callback
        self.ready, self.stopped = threading.Event(), threading.Event()
        self.error, self.thread_id = None, None

    def start(self):
        self.thread = threading.Thread(target=self._run, daemon=True, name='native-hotkey')
        self.thread.start()
        if not self.ready.wait(3):
            self.stop()
            return 'Global shortcut registration timed out'
        return self.error

    def _run(self):
        from ctypes import wintypes
        user = ctypes.windll.user32
        self.thread_id = ctypes.windll.kernel32.GetCurrentThreadId()
        message = wintypes.MSG()
        user.PeekMessageW(ctypes.byref(message), None, 0, 0, 0)
        registered = user.RegisterHotKey(None, 1, 0x0002 | 0x0001 | 0x4000, ord(self.chord[-1].upper()))
        if not registered:
            self.error = 'This global shortcut is already in use or could not be registered'
        self.ready.set()
        if not registered:
            return
        try:
            while not self.stopped.is_set() and user.GetMessageW(ctypes.byref(message), None, 0, 0) > 0:
                if message.message == 0x0312:
                    # pywebview create_window dispatches child creation to its GUI thread.
                    threading.Thread(target=self.callback, daemon=True, name='native-popout').start()
        finally:
            user.UnregisterHotKey(None, 1)

    def stop(self):
        self.stopped.set()
        if self.thread_id:
            ctypes.windll.user32.PostThreadMessageW(self.thread_id, 0x0012, 0, 0)
        if hasattr(self, 'thread') and self.thread is not threading.current_thread():
            self.thread.join(timeout=2)


def _balloon_notification(title, body, sound, activate, ready, result, shutdown):
    """Windows notification-area balloon, clickable to restore this app only."""
    from ctypes import wintypes
    user, shell, kernel = ctypes.windll.user32, ctypes.windll.shell32, ctypes.windll.kernel32
    WNDPROC = ctypes.WINFUNCTYPE(ctypes.c_ssize_t, wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM)

    class WNDCLASS(ctypes.Structure):
        _fields_ = [('style', wintypes.UINT), ('lpfnWndProc', WNDPROC), ('cbClsExtra', ctypes.c_int),
                    ('cbWndExtra', ctypes.c_int), ('hInstance', wintypes.HINSTANCE), ('hIcon', wintypes.HICON),
                    ('hCursor', wintypes.HANDLE), ('hbrBackground', wintypes.HBRUSH), ('lpszMenuName', wintypes.LPCWSTR),
                    ('lpszClassName', wintypes.LPCWSTR)]

    class NOTIFYICONDATA(ctypes.Structure):
        _fields_ = [('cbSize', wintypes.DWORD), ('hWnd', wintypes.HWND), ('uID', wintypes.UINT), ('uFlags', wintypes.UINT),
                    ('uCallbackMessage', wintypes.UINT), ('hIcon', wintypes.HICON), ('szTip', wintypes.WCHAR*128),
                    ('dwState', wintypes.DWORD), ('dwStateMask', wintypes.DWORD), ('szInfo', wintypes.WCHAR*256),
                    ('uTimeoutOrVersion', wintypes.UINT), ('szInfoTitle', wintypes.WCHAR*64), ('dwInfoFlags', wintypes.DWORD),
                    ('guidItem', ctypes.c_byte*16), ('hBalloonIcon', wintypes.HICON)]

    user.DefWindowProcW.restype = ctypes.c_ssize_t
    user.DefWindowProcW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
    user.CreateWindowExW.restype = wintypes.HWND
    user.CreateWindowExW.argtypes = [wintypes.DWORD, wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.DWORD,
                                   ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
                                   wintypes.HWND, wintypes.HMENU, wintypes.HINSTANCE, ctypes.c_void_p]
    kernel.GetModuleHandleW.restype = wintypes.HMODULE
    user.LoadIconW.restype = wintypes.HICON
    user.LoadIconW.argtypes = [wintypes.HINSTANCE, ctypes.c_void_p]
    hwnd = None
    data = None
    name = 'SuperTeamNotification_' + str(threading.get_ident())

    @WNDPROC
    def callback(hwnd, message, wparam, lparam):
        if message == 0x8001 and (lparam & 0xFFFF) == 0x0405:
            threading.Thread(target=activate, daemon=True).start()
        return user.DefWindowProcW(hwnd, message, wparam, lparam)

    instance = kernel.GetModuleHandleW(None)
    definition = WNDCLASS(lpfnWndProc=callback, hInstance=instance, lpszClassName=name)
    try:
        if not user.RegisterClassW(ctypes.byref(definition)):
            raise OSError('Windows could not register the notification window')
        hwnd = user.CreateWindowExW(0, name, '', 0, 0, 0, 0, 0, None, None, instance, None)
        if not hwnd:
            raise OSError('Windows could not create the notification window')
        data = NOTIFYICONDATA(cbSize=ctypes.sizeof(NOTIFYICONDATA), hWnd=hwnd, uID=1,
                              uFlags=1|2|4|16, uCallbackMessage=0x8001,
                              hIcon=user.LoadIconW(None, ctypes.c_void_p(32512)), szTip='SuperTeam',
                              szInfo=body, szInfoTitle=title, dwInfoFlags=1|(0 if sound else 0x10), uTimeoutOrVersion=8000)
        if not shell.Shell_NotifyIconW(0, ctypes.byref(data)):
            raise OSError('Windows notification-area service is unavailable')
        result.update(ok=True, delivery='notification-area')
        ready.set()
        message = wintypes.MSG()
        deadline = time.monotonic()+10
        while time.monotonic() < deadline and not shutdown.is_set():
            while user.PeekMessageW(ctypes.byref(message), None, 0, 0, 1):
                user.TranslateMessage(ctypes.byref(message))
                user.DispatchMessageW(ctypes.byref(message))
            shutdown.wait(.05)
    except Exception as exc:
        result.update(failure(exc))
        ready.set()
    finally:
        if data is not None and hwnd:
            shell.Shell_NotifyIconW(2, ctypes.byref(data))
        if hwnd:
            user.DestroyWindow(ctypes.c_void_p(hwnd))
        user.UnregisterClassW(name, ctypes.c_void_p(instance))
