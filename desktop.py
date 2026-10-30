"""Native Windows WebView2 host; the service survives closing the window."""
from pathlib import Path
import json,os,sys,time,subprocess,urllib.request

BUNDLE=Path(sys.executable).parent if getattr(sys,'frozen',False) else Path(__file__).resolve().parent
ROOT=Path(json.loads((BUNDLE/'app-root.json').read_text(encoding='utf-8'))['root']) if (BUNDLE/'app-root.json').exists() else BUNDLE
os.environ['SUPERTEAM_ROOT']=str(ROOT)

class WindowControls:
    def __init__(self, root=None, base_url=None):
        from native_services import NativeServices
        self._root = Path(root) if root is not None else ROOT
        self._base_url = base_url
        self._window = None
        self._maximized = False
        self._fullscreen = False
        self._closing = False
        self._children = []
        self._native = NativeServices(self._root, activate=self._activate,
                                      popout=lambda: self.popout(self._settings().get('standaloneChat', True)))

    def _settings(self):
        try:
            return json.loads((self._root/'data/preferences.json').read_text(encoding='utf-8'))
        except (OSError, ValueError):
            return {}

    def _activate(self):
        if self._window:
            self._window.restore()
            self._window.show()

    def minimize(self):
        self._window.minimize()

    def toggle_maximize(self):
        if self._fullscreen:
            self._window.toggle_fullscreen()
            self._fullscreen = False
        if self._maximized:
            self._window.restore()
        else:
            self._window.maximize()
        self._window.show()
        self._maximized = not self._maximized
        return {'ok':True,'maximized':self._maximized,'fullscreen':False}

    def toggle_fullscreen(self):
        self._window.toggle_fullscreen()
        self._fullscreen = not self._fullscreen
        self._window.show()
        return {'ok':True,'fullscreen':self._fullscreen,'maximized':False if self._fullscreen else self._maximized}

    def _confirm_close(self, reason):
        settings = self._settings()
        policy = settings.get('confirmClose', 'never')
        if policy == 'always' or (policy == 'shortcut' and reason == 'shortcut'):
            english = settings.get('language') == 'en'
            return self._window.create_confirmation_dialog('Close window?' if english else '关闭窗口？',
                'Close this window? Background tasks will continue.' if english else '关闭当前窗口？后台任务会继续运行。')
        return True

    def close(self, reason='button'):
        if not self._confirm_close(reason):
            return {'ok': False, 'cancelled': True}
        if self._settings().get('closeBehavior') == 'minimize':
            self._window.minimize()
        else:
            self._closing = True
            self._window.destroy()
        return {'ok': True}

    def _on_closing(self):
        if self._closing:
            return True
        # Native Alt+F4 and window-manager close requests enter here.
        if not self._confirm_close('shortcut'):
            return False
        if self._settings().get('closeBehavior') == 'minimize':
            self._window.minimize()
            return False
        return True

    def _on_closed(self):
        self._native.shutdown()

    def resize(self, width, height):
        if not self._maximized:
            self._window.resize(max(840, min(4000, int(width))), max(640, min(2400, int(height))))

    def capabilities(self):
        return self._native.capabilities()

    def choose_folder(self, initial=''):
        from native_services import failure
        try:
            import webview
            directory = self._native._path(initial, True) if initial else str(self._root)
            selected = self._window.create_file_dialog(webview.FileDialog.FOLDER, directory=directory)
            return {'ok': True, 'path': str(selected[0]) if selected else '', 'cancelled': not bool(selected)}
        except Exception as exc:
            return failure(exc)

    def choose_file(self):
        from native_services import failure
        try:
            import webview
            selected = self._window.create_file_dialog(webview.FileDialog.OPEN, allow_multiple=False)
            return {'ok': True, 'path': str(selected[0]) if selected else '', 'cancelled': not bool(selected)}
        except Exception as exc:
            return failure(exc)

    def open_file(self, path, destination='system'):
        return self._native.open_file(path, destination)

    def open_terminal(self, path, shell='powershell', location='panel'):
        return self._native.open_terminal(path, shell, location)

    def terminal_start(self, path, shell='powershell'):
        return self._native.terminal_start(path, shell)

    def terminal_write(self, text):
        return self._native.terminal_write(text)

    def terminal_read(self, cursor=0):
        return self._native.terminal_read(cursor)

    def terminal_stop(self):
        return self._native.terminal_stop()

    def notify(self, title='SuperTeam', body='A task needs your attention.', sound=False):
        return self._native.notify(title, body, sound)

    def set_popout_hotkey(self, chord):
        return self._native.set_popout_hotkey(chord)

    def popout(self, standalone=True):
        from native_services import failure
        try:
            import webview
            from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode
            base = self._base_url
            if not base:
                data = service_info()
                if not data:
                    return failure('The local chat service is unavailable')
                base = f"http://127.0.0.1:{data['port']}/#{data['token']}"
            parts = urlsplit(base)
            query = dict(parse_qsl(parts.query))
            query.update(popout='1', standalone='1' if standalone else '0')
            url = urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment))
            controls = WindowControls(root=self._root, base_url=base)
            # pywebview dispatches create_window from API/hotkey threads to the GUI backend.
            window = webview.create_window('SuperTeam', url=url, width=1000, height=800,
                min_size=(840, 640), text_select=True, background_color='#f8f9fa',
                frameless=True, easy_drag=False, shadow=True, js_api=controls)
            if window is None:
                return failure('The popout window could not be created')
            controls._window = window
            window.events.closing += controls._on_closing
            window.events.closed += controls._on_closed
            self._children.append(controls)
            return {'ok': True, 'standalone': bool(standalone)}
        except Exception as exc:
            return failure(exc)

def service_info():
    try:
        data=json.loads((ROOT/'data/runtime.json').read_text())
        with urllib.request.urlopen(f"http://127.0.0.1:{data['port']}/health",timeout=1) as response:
            if json.load(response).get('app')=='ai-chat-sandbox':return data
    except Exception:pass
    return None

def main():
    if '--desktop-mcp' in sys.argv:
        from desktop_mcp import serve
        serve(ROOT,sys.argv[sys.argv.index('--room')+1],sys.argv[sys.argv.index('--provider')+1]);return
    if '--server' in sys.argv:
        from native_instance import claim_instance
        if not claim_instance(ROOT,'server'):return
        import runpy
        runpy.run_module('server',run_name='__main__');return
    from native_instance import claim_instance
    if not claim_instance(ROOT,'window'):return
    data=service_info()
    if not data:
        command=[sys.executable,'--server'] if getattr(sys,'frozen',False) else [sys.executable,str(ROOT/'server.py')]
        (ROOT/'data').mkdir(exist_ok=True)
        with open(ROOT/'data/desktop-service.log','ab') as log:
            subprocess.Popen(command,cwd=ROOT,env=os.environ.copy(),stdout=log,stderr=log,creationflags=subprocess.CREATE_NO_WINDOW)
        for _ in range(100):
            time.sleep(.15);data=service_info()
            if data:break
    if not data:raise RuntimeError('本地服务未能启动，请查看 data/desktop-service.log')
    import webview
    base_url=f"http://127.0.0.1:{data['port']}/#{data['token']}"
    controls=WindowControls(base_url=base_url)
    window=webview.create_window('SuperTeam',f"http://127.0.0.1:{data['port']}/#{data['token']}",width=1380,height=920,min_size=(840,640),text_select=True,background_color='#f8f9fa',frameless=True,easy_drag=False,shadow=True,js_api=controls)
    controls._window=window
    window.events.closing+=controls._on_closing
    window.events.closed+=controls._on_closed
    def rounded():
        try:
            import ctypes
            from native_instance import own_window_handle
            hwnd=own_window_handle();value=ctypes.c_int(2)
            if not hwnd:return
            ctypes.windll.dwmapi.DwmSetWindowAttribute(ctypes.c_void_p(hwnd),33,ctypes.byref(value),4)
        except Exception:pass
    window.events.loaded+=rounded
    icon=ROOT/'ui/assets/superteam-v1.ico'
    if not icon.exists():icon=ROOT/'ui/assets/superteam.ico'
    webview.start(gui='edgechromium',private_mode=False,storage_path=str(ROOT/'data/webview'),icon=str(icon))

if __name__=='__main__':
    try:main()
    except Exception as exc:
        import ctypes
        ctypes.windll.user32.MessageBoxW(0,str(exc),'SuperTeam',0x10)
