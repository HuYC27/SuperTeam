"""Validated application preferences; no provider credentials are read here."""
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import threading

ENUMS={
    'backgroundAI':('deepseek','codex','workbuddy'),'language':('zh-CN','en'),'defaultPermission':('workspace-write','read-only','danger-full-access'),
    'fileDestination':('system','vscode'),'agentEnvironment':('windows',),'terminalShell':('powershell','cmd','pwsh'),
    'terminalLocation':('panel','window'),'archiveDays':(0,7,30,90),'speed':('fast','balanced','thorough'),
    'followupBehavior':('queue','steer'),'completionNotifications':('background','always','never'),
    'confirmClose':('never','shortcut','always'),'theme':('light','dark','system')}
BOOL_DEFAULTS={'memoryEnabled':True,'fullView':True,'launchAtLogin':False,'showBottomPanel':True,'homepageSuggestions':True,
    'pluginsEnabled':True,'showPredictions':False,'plainTextComposer':True,'showContextUsage':False,
    'standaloneChat':True,'permissionNotifications':True,'questionNotifications':True,
    'dotNotifications':False,'notificationSound':False}
_LOCK=threading.RLock()


def defaults(root):
    return {**{key:values[0] for key,values in ENUMS.items()},**BOOL_DEFAULTS,
            'chatFolder':str(Path(root).resolve()/'work'/'rooms'),'popoutHotkey':'',
            'memoryContextChars':1600,'userPreferences':'','customPrompt':'','backgroundModel':'','theme':'light','accent':'#000000','font':16,'sidebar':288,'speed':'fast'}


def validate(value):
    if not isinstance(value,dict):raise ValueError('设置必须是对象')
    for key,choices in ENUMS.items():
        if key in value and (type(value[key]) is not type(choices[0]) or value[key] not in choices):raise ValueError('设置值无效: '+key)
    for key in BOOL_DEFAULTS:
        if key in value and type(value[key]) is not bool:raise ValueError('设置必须为开关: '+key)
    for key,low,high in [('font',14,24),('sidebar',210,480)]:
        if key in value and (type(value[key]) is not int or not low<=value[key]<=high):raise ValueError('设置范围无效: '+key)
    if 'accent' in value and (not isinstance(value['accent'],str) or not re.fullmatch(r'#[0-9a-fA-F]{6}',value['accent'])):raise ValueError('主题颜色无效')
    if 'popoutHotkey' in value and (not isinstance(value['popoutHotkey'],str) or (value['popoutHotkey'] and not re.fullmatch(r'Ctrl\+Alt\+[A-Za-z]',value['popoutHotkey']))):raise ValueError('快捷键应为 Ctrl+Alt+字母')
    for key,limit in [('userPreferences',4000),('customPrompt',6000),('backgroundModel',200)]:
        if key in value and (not isinstance(value[key],str) or len(value[key])>limit):raise ValueError('偏好或提示词过长: '+key)
    if 'memoryContextChars' in value and (type(value['memoryContextChars']) is not int or not 600<=value['memoryContextChars']<=6000):raise ValueError('记忆上下文预算需为600–6000字符')
    if 'chatFolder' in value:
        folder=value['chatFolder']
        if not isinstance(folder,str) or not folder or len(folder)>2048 or '\x00' in folder or '\n' in folder or not Path(folder).is_absolute() or folder.startswith(('\\\\','//')):raise ValueError('请选择绝对本地文件夹路径')
        if Path(folder).exists() and not Path(folder).is_dir():raise ValueError('聊天位置必须是文件夹')
    return value


def set_launch_at_login(enabled,root):
    if os.name!='nt':raise ValueError('开机启动仅支持 Windows')
    import winreg
    executable=Path(sys.executable).resolve()
    if not getattr(sys,'frozen',False) and executable.name.lower()=='python.exe' and executable.with_name('pythonw.exe').exists():executable=executable.with_name('pythonw.exe')
    args=[str(executable)] if getattr(sys,'frozen',False) else [str(executable),str(Path(root).resolve()/'desktop.py')]
    command=subprocess.list2cmdline(args)
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER,r'Software\Microsoft\Windows\CurrentVersion\Run') as key:
        if enabled:winreg.SetValueEx(key,'SuperTeam',0,winreg.REG_SZ,command)
        else:
            try:winreg.DeleteValue(key,'SuperTeam')
            except FileNotFoundError:pass


class AppSettings:
    def __init__(self,root):
        self.root=Path(root);self.path=self.root/'data/preferences.json'
    def read(self):
        with _LOCK:
            try:
                raw=json.loads(self.path.read_text(encoding='utf-8-sig'))
                if not isinstance(raw,dict):raw={}
            except (OSError,ValueError):raw={}
            # Invalid legacy values fall back without destroying unrelated keys.
            result=defaults(self.root)
            for key,value in raw.items():
                try:validate({key:value})
                except (ValueError,TypeError):continue
                result[key]=value
            return result
    def update(self,updates):
        validate(updates)
        if len(json.dumps(updates,ensure_ascii=False).encode('utf-8'))>256*1024:raise ValueError('设置内容过大')
        with _LOCK:
            before=self.read();result={**before,**updates}
            validate(result)
            self.path.parent.mkdir(parents=True,exist_ok=True)
            temporary=self.path.with_suffix('.json.tmp')
            launch_changed=False
            try:
                temporary.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
                if 'launchAtLogin' in updates and updates['launchAtLogin']!=before['launchAtLogin']:
                    set_launch_at_login(updates['launchAtLogin'],self.root);launch_changed=True
                temporary.replace(self.path)
            except OSError as exc:
                if launch_changed:
                    try:set_launch_at_login(before['launchAtLogin'],self.root)
                    except OSError:pass
                raise ValueError('无法保存设置：'+str(exc)) from exc
            finally:
                temporary.unlink(missing_ok=True)
            return result
    def info(self):
        try:release=json.loads((self.root/'data/release.json').read_text(encoding='utf-8-sig'))
        except (OSError,ValueError):release={}
        try:notices=json.loads((self.root/'data/third-party-licenses.json').read_text(encoding='utf-8'))
        except (OSError,ValueError):notices=[]
        return {'version':release.get('version','development'),'release':release,
            'capabilities':{'agentEnvironment':{'windows':True,'wsl':False,'note':'仅运行本机 Windows 代理；尚未接入 WSL'},
                'speed':{'supported':True,'mode':'reasoningEffort','note':'调整 Codex/DeepSeek/WorkBuddy 推理深度及回答策略；不承诺服务端优先级或响应速度'},
                'plugins':{'supported':True,'scope':'SuperTeam skills','note':'控制 SuperTeam 的 #/$ 技能解析，不修改成员软件的全局扩展或 MCP 配置'},
                'launchAtLogin':{'supported':os.name=='nt'},
                'importExport':{'supported':True,'note':'JSON 保存文字和文件元信息；不复制附件文件、登录信息、会话凭证或电脑权限'},
                'native':{'requiredFor':['chooseFolder','openFolder','openFile','openTerminal','notifications','popoutHotkey'],'note':'桌面能力由 pywebview.api.capabilities 返回，浏览器内不可用'}},
            'licenses':[{'name':'Python','license':'PSF License','url':'https://docs.python.org/3/license.html'},
                {'name':'pywebview','license':'BSD-3-Clause','url':'https://github.com/r0x0r/pywebview/blob/master/LICENSE'},
                {'name':'Microsoft WebView2 Runtime','license':'Microsoft Software License Terms','url':'https://www.microsoft.com/en-us/legal/terms-of-use'}]+[n for n in notices if n.get('name','').lower() not in ['pywebview','python']]}


class OpenRoomLeases:
    """Keep all recently polled panes open across concurrent clients."""
    def __init__(self,clock=None,ttl=30):
        import time
        self.clock=clock or time.monotonic;self.ttl=ttl;self.rooms={};self.lock=threading.Lock()
    def touch(self,rooms):
        with self.lock:
            now=self.clock();self.rooms={rid:stamp for rid,stamp in self.rooms.items() if now-stamp<self.ttl}
            for rid in list(rooms)[:16]:
                if isinstance(rid,str) and re.fullmatch(r'[a-f0-9]{32}',rid):self.rooms[rid]=now
            return list(self.rooms)
