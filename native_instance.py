"""One GUI and one service per data root; never traverse WinForms objects."""
import os,hashlib,ctypes,time
from pathlib import Path
_handles=[]
def own_window_handle(pid=None):
    from ctypes import wintypes
    found=[];pid=pid or os.getpid()
    user=ctypes.windll.user32
    callback=ctypes.WINFUNCTYPE(wintypes.BOOL,wintypes.HWND,wintypes.LPARAM)
    def visit(hwnd,_):
        owner=wintypes.DWORD();user.GetWindowThreadProcessId(hwnd,ctypes.byref(owner))
        if owner.value==pid and user.IsWindowVisible(hwnd):found.append(hwnd)
        return True
    user.EnumWindows(callback(visit),0)
    return found[0] if found else None

def claim_instance(root,kind):
    if os.name!='nt':return True
    kernel=ctypes.WinDLL('kernel32',use_last_error=True)
    kernel.CreateMutexW.argtypes=[ctypes.c_void_p,ctypes.c_bool,ctypes.c_wchar_p]
    kernel.CreateMutexW.restype=ctypes.c_void_p
    key=hashlib.sha256(str(Path(root).resolve()).lower().encode()).hexdigest()[:24]
    handle=kernel.CreateMutexW(None,False,'Local\\SuperTeam-'+key+'-'+kind)
    error=ctypes.get_last_error()
    if not handle:raise ctypes.WinError(error)
    _handles.append(handle)
    marker=Path(root)/'data'/('native-'+kind+'.pid')
    if error==183:
        if kind=='window':
            try:
                hwnd=own_window_handle(int(marker.read_text()))
                if hwnd:
                    user=ctypes.windll.user32;user.ShowWindow(ctypes.c_void_p(hwnd),9);user.SetForegroundWindow(ctypes.c_void_p(hwnd))
            except (OSError,ValueError):pass
        return False
    marker.parent.mkdir(exist_ok=True);marker.write_text(str(os.getpid()))
    return True
