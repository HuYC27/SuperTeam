"""Double-click launcher. Reuses a running local service."""
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import urllib.request
import webbrowser

ROOT=Path(__file__).resolve().parent
RUNTIME=ROOT/'data'/'runtime.json'

def running():
    try:
        info=json.loads(RUNTIME.read_text(encoding='utf-8'))
        with urllib.request.urlopen(f"http://127.0.0.1:{info['port']}/health",timeout=1) as response:
            if json.load(response).get('app')=='ai-chat-sandbox': return info
    except Exception: pass
    return None

def main():
    manifest=ROOT/'data/release.json'
    native=Path(json.loads(manifest.read_text(encoding='utf-8'))['executable']) if manifest.exists() else ROOT/'SuperTeam.exe'
    if native.exists():
        subprocess.Popen([str(native)],cwd=ROOT,creationflags=subprocess.CREATE_NO_WINDOW);return
    info=running()
    if not info:
        (ROOT/'data').mkdir(exist_ok=True)
        with open(ROOT/'data'/'server.log','ab') as log:
            subprocess.Popen([sys.executable,str(ROOT/'server.py')],cwd=ROOT,stdout=log,stderr=log,
                             creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
        for _ in range(80):
            time.sleep(.15)
            info=running()
            if info: break
    if not info: raise RuntimeError('服务启动失败，请查看 data/server.log')
    url=f"http://127.0.0.1:{info['port']}/#{info['token']}"
    browser=None
    if os.name=='nt':
        import winreg
        for hive in [winreg.HKEY_LOCAL_MACHINE,winreg.HKEY_CURRENT_USER]:
            for app in ['msedge.exe','chrome.exe']:
                try:
                    key_path=chr(92).join(['SOFTWARE','Microsoft','Windows','CurrentVersion','App Paths',app])
                    with winreg.OpenKey(hive,key_path) as key:
                        value=winreg.QueryValue(key,None)
                        if Path(value).exists(): browser=value;break
                except OSError: pass
            if browser: break
    if browser:
        subprocess.Popen([browser,'--app='+url,'--window-size=1380,900'],creationflags=subprocess.CREATE_NO_WINDOW)
    else: webbrowser.open(url)

if __name__=='__main__':
    try: main()
    except Exception as exc:
        if os.name=='nt':
            import ctypes
            ctypes.windll.user32.MessageBoxW(0,str(exc),'SuperTeam',0x10)
        else: raise
