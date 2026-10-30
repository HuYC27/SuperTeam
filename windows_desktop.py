"""Desktop operations used by the product after broker authorization.

No credential stores, process memory or arbitrary commands are exposed as tools.
"""
import ctypes,os,json,subprocess,base64,io
from ctypes import wintypes as W

class WindowsDesktop:
    def __init__(self):self.shots={}
    def _window(self,args,foreground=False):
        user=ctypes.windll.user32;hwnd=int(args.get('hwnd',0))
        if not hwnd or not user.IsWindow(W.HWND(hwnd)) or not user.IsWindowVisible(W.HWND(hwnd)):raise ValueError('目标窗口不存在，请重新列出窗口')
        if foreground and int(user.GetForegroundWindow())!=hwnd:raise ValueError('焦点已变化，为避免操作到其他软件，请重新查看并激活目标窗口')
        return hwnd
    def _read(self,hwnd,focused=False):
        # This fixed script queries UI Automation, and never evaluates model text.
        script=r'''[Console]::OutputEncoding=New-Object System.Text.UTF8Encoding
Add-Type -AssemblyName UIAutomationClient
Add-Type -AssemblyName UIAutomationTypes
$argData=[Console]::In.ReadToEnd()|ConvertFrom-Json
if($argData.focused){
 $e=[System.Windows.Automation.AutomationElement]::FocusedElement
 if(-not $e){throw 'No focus'}
 @{password=$e.Current.IsPassword;name=$e.Current.Name}|ConvertTo-Json -Compress
 exit
}
$root=[System.Windows.Automation.AutomationElement]::FromHandle([IntPtr][long]$argData.hwnd)
$all=$root.FindAll([System.Windows.Automation.TreeScope]::Descendants,[System.Windows.Automation.Condition]::TrueCondition)
$rows=@();for($i=0;$i -lt [Math]::Min($all.Count,500);$i++){
 $e=$all.Item($i);try{if($e.Current.IsPassword -or $e.Current.IsOffscreen){continue}
 $name=$e.Current.Name;$value='';$pattern=$null
 if($e.TryGetCurrentPattern([System.Windows.Automation.ValuePattern]::Pattern,[ref]$pattern)){$value=$pattern.Current.Value}
 if($name -or $value){$rows+=@{name=$name;value=$value;type=$e.Current.ControlType.ProgrammaticName;automationId=$e.Current.AutomationId}}
 }catch{}
}
ConvertTo-Json -InputObject @($rows) -Depth 4 -Compress'''
        encoded=base64.b64encode(script.encode('utf-16le')).decode()
        p=subprocess.run(['powershell.exe','-NoProfile','-NonInteractive','-EncodedCommand',encoded],input=json.dumps({'hwnd':hwnd,'focused':focused}).encode(),capture_output=True,timeout=15,creationflags=subprocess.CREATE_NO_WINDOW)
        if p.returncode:raise ValueError('无法读取目标界面，请使用截图；密码框不能自动输入')
        raw=p.stdout.decode('utf-8-sig',errors='replace')
        try:return json.loads(raw)
        except ValueError:raise ValueError('目标界面没有返回可读取内容')
    def _input(self,entries):
        class Mouse(ctypes.Structure):_fields_=[('dx',W.LONG),('dy',W.LONG),('mouseData',W.DWORD),('dwFlags',W.DWORD),('time',W.DWORD),('dwExtraInfo',ctypes.c_size_t)]
        class Keyboard(ctypes.Structure):_fields_=[('wVk',W.WORD),('wScan',W.WORD),('dwFlags',W.DWORD),('time',W.DWORD),('dwExtraInfo',ctypes.c_size_t)]
        class Union(ctypes.Union):_fields_=[('mi',Mouse),('ki',Keyboard)]
        class Input(ctypes.Structure):_fields_=[('type',W.DWORD),('u',Union)]
        inputs=[]
        for typ,vk,scan,flags in entries:
            item=Input();item.type=typ
            if typ==1:item.u.ki=Keyboard(vk,scan,flags,0,0)
            else:item.u.mi=Mouse(0,0,scan,flags,0,0)
            inputs.append(item)
        array=(Input*len(inputs))(*inputs)
        if ctypes.windll.user32.SendInput(len(inputs),array,ctypes.sizeof(Input))!=len(inputs):raise ValueError('Windows 拒绝了输入；未自动提升权限')
    def execute(self,tool,args):
        if os.name!='nt':raise ValueError('电脑操控目前仅支持 Windows')
        user=ctypes.windll.user32
        if tool=='windows':
            rows=[];callback=ctypes.WINFUNCTYPE(W.BOOL,W.HWND,W.LPARAM)
            def visit(hwnd,_):
                if user.IsWindowVisible(hwnd):
                    title=ctypes.create_unicode_buffer(512);user.GetWindowTextW(hwnd,title,512)
                    if title.value:rows.append({'hwnd':int(hwnd),'title':title.value})
                return True
            user.EnumWindows(callback(visit),0)
            return {'content':[{'type':'text','text':json.dumps(rows,ensure_ascii=False)}]}
        hwnd=self._window(args,foreground=tool in ['click','type','key','scroll','screenshot'])
        if tool=='focus':
            user.ShowWindow(W.HWND(hwnd),9)
            if not user.SetForegroundWindow(W.HWND(hwnd)):raise ValueError('未能切换焦点，请用户手动点击目标窗口后继续')
        elif tool=='read_window':return {'content':[{'type':'text','text':json.dumps(self._read(hwnd),ensure_ascii=False)[:40000]}]}
        elif tool=='screenshot':
            from PIL import ImageGrab
            rect=W.RECT();user.GetWindowRect(W.HWND(hwnd),ctypes.byref(rect))
            image=ImageGrab.grab(bbox=(rect.left,rect.top,rect.right,rect.bottom),all_screens=True);original=image.size;image.thumbnail((1440,1000))
            self.shots[hwnd]={'rect':(rect.left,rect.top,rect.right,rect.bottom),'size':image.size,'scale':(original[0]/image.width,original[1]/image.height)}
            buf=io.BytesIO();image.save(buf,format='PNG')
            return {'content':[{'type':'text','text':f'窗口 {hwnd}，截图尺寸 {image.width}×{image.height}，点击使用截图像素坐标。'},{'type':'image','mimeType':'image/png','data':base64.b64encode(buf.getvalue()).decode()}]}
        elif tool=='click':
            shot=self.shots.get(hwnd)
            if not shot:raise ValueError('请先查看这个窗口的截图，再点击')
            x=float(args.get('x',-1));y=float(args.get('y',-1))
            if not 0<=x<shot['size'][0] or not 0<=y<shot['size'][1]:raise ValueError('坐标超出截图范围')
            rect=W.RECT();user.GetWindowRect(W.HWND(hwnd),ctypes.byref(rect))
            if tuple((rect.left,rect.top,rect.right,rect.bottom))!=shot['rect']:raise ValueError('窗口位置或大小已变化，请重新截图')
            user.SetCursorPos(round(rect.left+x*shot['scale'][0]),round(rect.top+y*shot['scale'][1]));self._input([(0,0,0,2),(0,0,0,4)])
        elif tool=='type':
            text=args.get('text','')
            if not isinstance(text,str) or not 0<len(text)<=12000:raise ValueError('输入文字须为 1–12000 字符')
            if self._read(hwnd,True).get('password'):raise ValueError('密码或验证码请用户自行输入')
            raw=text.encode('utf-16le');items=[]
            for i in range(0,len(raw),2):
                code=int.from_bytes(raw[i:i+2],'little');items.extend([(1,0,code,4),(1,0,code,6)])
            self._input(items)
        elif tool=='key':
            keys=str(args.get('key','')).upper().split('+');mapping={'CTRL':17,'SHIFT':16,'ALT':18,'ENTER':13,'TAB':9,'ESC':27,'ESCAPE':27,'BACKSPACE':8,'DELETE':46,'LEFT':37,'RIGHT':39,'UP':38,'DOWN':40,'HOME':36,'END':35,'PAGEDOWN':34,'PAGEUP':33,'A':65,'L':76,'S':83,'W':87}
            if not keys or any(k not in mapping for k in keys):raise ValueError('暂不支持这个组合键')
            codes=[mapping[k] for k in keys];self._input([(1,k,0,0) for k in codes]+[(1,k,0,2) for k in reversed(codes)])
        elif tool=='scroll':
            delta=max(-720,min(720,int(args.get('delta',0))))
            self._input([(0,0,(-delta)&0xffffffff,0x0800)])
        return {'content':[{'type':'text','text':'操作已完成；请重新读取界面核验结果。'}]}
