"""Bounded installed-app discovery. Installation never implies a working bridge."""
from pathlib import Path
import os
import re
import subprocess,json,time,io,struct

KNOWN={'claude':'Claude','cursor':'Cursor','windsurf':'Windsurf','ollama':'Ollama','cherry':'Cherry Studio','trae':'Trae','lmstudio':'LM Studio','workbuddy':'WorkBuddy','doubao':'豆包','yuanbao':'元宝','qwen':'千问','kimi':'Kimi'}

def refresh_icons(runner):
    """Prefer vendor image assets and native ICO frames, never enlarged thumbnails."""
    from PIL import Image
    sources=[]
    packages=Path(os.environ.get('ProgramFiles','C:/Program Files'))/'WindowsApps'
    try:
        icons=sorted(packages.glob('OpenAI.Codex_*/app/resources/icon-chatgpt.ico'),key=lambda p:p.stat().st_mtime,reverse=True)
        if icons:sources.append(('codex',icons[0]))
    except OSError:pass
    sources.append(('deepseek',runner.deepseek.parent/'resources/icon.png'))
    folder=runner.root/'ui/assets';folder.mkdir(parents=True,exist_ok=True)
    for key,source in sources:
        try:
            with Image.open(source) as image:
                frame=image.ico.getimage(max(image.ico.sizes(),key=lambda s:s[0]*s[1])) if image.format=='ICO' else image
                if min(frame.size)<128:continue
                destination=folder/(key+'.png')
                if destination.exists():
                    with Image.open(destination) as old:
                        if old.size==frame.size and destination.stat().st_mtime>=source.stat().st_mtime:continue
                temporary=folder/(key+'.tmp');frame.save(temporary,format='PNG');temporary.replace(destination)
        except (OSError,ValueError):continue

def legacy_scan(runner):
    refresh_icons(runner)
    result=[]
    for key,name in [('codex','Codex'),('deepseek','DeepSeek Harness')]:
        installed=runner.status().get(key,{}).get('installed',False)
        if installed:result.append({'id':key,'name':name,'supported':True,'icon':'/assets/'+key+'.png','detail':'已有账号连接器，可直接加入'})
    if os.name!='nt':return result
    import winreg
    seen=set()
    for hive in [winreg.HKEY_CURRENT_USER,winreg.HKEY_LOCAL_MACHINE]:
        for branch in [r'Software\Microsoft\Windows\CurrentVersion\Uninstall',r'Software\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall']:
            try:base=winreg.OpenKey(hive,branch)
            except OSError:continue
            with base:
                for i in range(winreg.QueryInfoKey(base)[0]):
                    try:
                        with winreg.OpenKey(base,winreg.EnumKey(base,i)) as sub:
                            name=str(winreg.QueryValueEx(sub,'DisplayName')[0])
                            key=next((k for k,v in KNOWN.items() if re.sub(r'\W','',v.lower()) in re.sub(r'\W','',name.lower())),None)
                            if key and key not in seen:
                                seen.add(key);result.append({'id':key,'name':name,'supported':False,'icon':None,'detail':'已发现安装；尚无账号连接器，暂不能加入'})
                    except OSError:continue
    for app in result:
        if app['id']=='workbuddy':app.update(supported=True,detail='已验证账号文本连接，可加入聊天')
    return result

_cache={'time':0,'items':[]}
def inventory():
    if time.time()-_cache['time']<60:return _cache['items']
    script=r'''$items=@();$shell=New-Object -ComObject WScript.Shell
    foreach($base in @([Environment]::GetFolderPath('Programs'),[Environment]::GetFolderPath('CommonPrograms'))){
      Get-ChildItem -LiteralPath $base -Filter *.lnk -Recurse -ErrorAction SilentlyContinue | ForEach-Object {
        if($_.BaseName){
          $link=$shell.CreateShortcut($_.FullName);$items+=@{name=$_.BaseName;path=$link.TargetPath;source='开始菜单'}
        }
      }
    }
    foreach($key in @('HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\*','HKLM:\Software\Microsoft\Windows\CurrentVersion\Uninstall\*','HKLM:\Software\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall\*')){Get-ItemProperty $key -ErrorAction SilentlyContinue | Where-Object {$_.DisplayName} | ForEach-Object {$items+=@{name=$_.DisplayName;path=$_.InstallLocation;icon=$_.DisplayIcon;source='安装信息'}}}
    Get-AppxPackage | ForEach-Object {$items+=@{name=$_.Name;path=$_.InstallLocation;source='Windows 应用包'}}
    [Console]::OutputEncoding=[Text.Encoding]::UTF8;ConvertTo-Json -InputObject @($items) -Compress'''
    try:
        result=subprocess.run(['powershell.exe','-NoProfile','-NonInteractive','-Command',script],capture_output=True,timeout=30,creationflags=subprocess.CREATE_NO_WINDOW)
        items=json.loads(result.stdout.decode('utf-8-sig'))
    except (OSError,ValueError,subprocess.TimeoutExpired):items=[]
    _cache.update(time=time.time(),items=items);return items

def extract_icon(path,destination):
    from PIL import Image
    path=Path(path)
    try:
        if path.suffix.lower() in ['.ico','.png'] and path.exists():
            with Image.open(path) as image:
                frame=image.ico.getimage(max(image.ico.sizes(),key=lambda s:s[0]*s[1])) if image.format=='ICO' else image
                frame.save(destination,format='PNG');return True
        if path.is_dir():
            for candidate in [path/'app.ico',path/'icon.ico',path/'resources/icon.png']:
                if candidate.exists():return extract_icon(candidate,destination)
            assets=path/'assets'
            candidates=list(assets.glob('*256*png'))+list(assets.glob('Square150*png'))+list(assets.glob('icon.png'))
            if candidates:
                with Image.open(max(candidates,key=lambda p:p.stat().st_size)) as image:image.save(destination,format='PNG');return True
        if path.suffix.lower()=='.exe':
            import pefile
            pe=pefile.PE(str(path));frames={};groups=[]
            try:
                for kind in pe.DIRECTORY_ENTRY_RESOURCE.entries:
                    if kind.id==3:
                        for item in kind.directory.entries:
                            d=item.directory.entries[0].data.struct;frames[item.id]=pe.get_data(d.OffsetToData,d.Size)
                    if kind.id==14:
                        d=kind.directory.entries[0].directory.entries[0].data.struct;group=pe.get_data(d.OffsetToData,d.Size)
                        for i in range(struct.unpack_from('<H',group,4)[0]):
                            entry=group[6+i*14:20+i*14];groups.append((entry[0] or 256,entry[1] or 256,struct.unpack_from('<H',entry,12)[0]))
                for w,h,rid in sorted(groups,reverse=True):
                    raw=frames.get(rid)
                    if not raw:continue
                    header=struct.pack('<HHH',0,1,1)+struct.pack('<BBBBHHII',w if w<256 else 0,h if h<256 else 0,0,0,1,32,len(raw),22)
                    with Image.open(io.BytesIO(header+raw)) as image:image.save(destination,format='PNG');return True
            finally:pe.close()
    except Exception:return False
    return False

def scan(runner,query='',all_apps=False):
    result=legacy_scan(runner);result=[r for r in result if not query or query.lower() in r['name'].lower()];seen={r['id'] for r in result};folder=runner.root/'ui/assets'
    for item in inventory():
        if query and query.lower() not in (item['name']+' '+str(item.get('path',''))).lower():continue
        compact=re.sub(r'\W','',item['name'].lower())
        key=next((k for k,v in {**KNOWN,'codex':'Codex','deepseek':'DeepSeek'}.items() if k in compact or re.sub(r'\W','',v.lower()) in compact),None)
        if not key and not all_apps and not re.search(r'ChatGPT|Copilot|Gemini|\bAI\b|智能|大模型',item['name'],re.I):continue
        if not key:key='app-'+__import__('hashlib').sha256(item['name'].encode()).hexdigest()[:10]
        previous=next((r for r in result if r['id']==key),None)
        if previous and previous.get('path'):continue
        seen.add(key);icon=folder/('installed-'+key+'.png')
        rawpath=str(item.get('path') or '').strip(chr(34))
        iconpath=re.sub(r',-?\d+$','',str(item.get('icon') or '')).strip(chr(34))
        location=(Path(rawpath).parent if Path(rawpath).suffix.lower()=='.exe' else Path(rawpath)) if rawpath else Path(iconpath).parent
        if not rawpath or location.is_dir():
            if key=='ollama' and (location/'ollama app.exe').exists():rawpath=str(location/'ollama app.exe')
            elif key=='doubao' and (location/'Doubao.exe').exists():rawpath=str(location/'Doubao.exe')
        item['path']=rawpath
        if not icon.exists():
            for candidate in [str(location/'app.ico'),str(location/'icon.ico'),iconpath,rawpath]:
                if candidate and extract_icon(candidate,icon):break
        if previous:
            previous.update(path=item['path'],icon='/assets/'+icon.name if icon.exists() else previous.get('icon'));continue
        result.append({'id':key,'name':item['name'],'supported':False,'icon':'/assets/'+icon.name if icon.exists() else None,'path':item['path'],'detail':'已发现：'+item['source']+'；账号连接器尚未接通'})
    for app in result:
        if app['id']=='workbuddy':app.update(supported=True,detail='已验证账号文本连接，可加入聊天')
    return result
