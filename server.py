"""Loopback-only app server, no external Python dependencies."""
import json
import os
from pathlib import Path
import secrets
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs
from core import Store, ChatService
from adapters import AgentRunner
from app_settings import AppSettings
from uploads import save_upload
from workflow import PROFILES
from urllib.parse import quote
import mimetypes
import base64,io
from discovery import scan
from context_search import retrieve
from skill_library import SkillLibrary
from quotas import Quotas
from file_library import FileLibrary
import re

ROOT=Path(os.environ.get('SUPERTEAM_ROOT',str(Path(__file__).resolve().parent)))


def make_server(port=0,discover_models=True,auth_token=None):
    root=ROOT
    preferences=AppSettings(root)
    from app_settings import OpenRoomLeases
    open_room_leases=OpenRoomLeases()
    store=Store(root/'data'/'history.db')
    existing=store.list_rooms()
    for name,members in [('Codex',['codex']),('DeepSeek',['deepseek']),('双 AI 讨论室',['codex','deepseek'])]:
        if not any(r['name']==name and r['members']==members for r in existing): store.create_room(name,members,preferences=preferences.read())
    runner=AgentRunner(root)
    from connections import Connections
    connections=Connections(root,runner)
    service=ChatService(store,runner,root)
    from memory_agent import MemoryWorker,task_tag
    memory=service.memory;memory.bootstrap_feedback(store);memory_worker=MemoryWorker(memory,store,runner,root)
    service.on_complete=lambda job:memory_worker.schedule(job['room']) if not service.active() else None
    skills=SkillLibrary(root);quotas=Quotas(root);file_library=FileLibrary(store,root)
    from desktop_control import DesktopBroker
    from windows_desktop import WindowsDesktop
    desktop_device=WindowsDesktop()
    def computer_enabled(rid):
        try:return store.room(rid)['settings'].get('computer')=='critical' and any(j['room']==rid and j['status']=='running' for j in service.active())
        except ValueError:return False
    desktop=DesktopBroker(computer_enabled,desktop_device.execute)
    token=auth_token or secrets.token_urlsafe(32)
    catalog_path=root/'data/model-catalog.json'
    try:catalog=json.loads(catalog_path.read_text(encoding='utf-8'))
    except (OSError,ValueError):catalog={'codex':[{'id':'','name':'跟随 Codex 默认模型'}],'deepseek':[{'id':'deepseek-flash','name':'DeepSeek Flash'},{'id':'deepseek-v4-pro','name':'DeepSeek V4 Pro'}],'source':{}}
    model_lock=threading.Lock()
    def refresh_models():
        if not model_lock.acquire(blocking=False):return
        try:fresh=runner.models()
        finally:model_lock.release()
        if str(fresh.get('source',{}).get('codex','')).startswith('无法') and len(catalog.get('codex',[]))>1:fresh['codex']=catalog['codex']
        catalog.update(fresh)
        catalog_path.write_text(json.dumps(fresh,ensure_ascii=False),encoding='utf-8')
    if discover_models:
        threading.Thread(target=refresh_models,daemon=True).start()
        threading.Thread(target=connections.discover,daemon=True).start()
        def model_monitor():
            while True:
                time.sleep(1800)
                if connections.enabled:refresh_models()
        threading.Thread(target=model_monitor,daemon=True).start()
    def artifacts(rid):
        return file_library.artifacts(rid)

    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*args): pass
        def reply(self,data,status=200,content_type='application/json; charset=utf-8',filename=None):
            body=json.dumps(data,ensure_ascii=False).encode('utf-8') if isinstance(data,(dict,list)) else data
            self.send_response(status)
            self.send_header('Content-Type',content_type)
            self.send_header('Content-Length',str(len(body)))
            self.send_header('Cache-Control','no-store')
            self.send_header('X-Content-Type-Options','nosniff')
            self.send_header('Content-Security-Policy',"default-src 'self'; style-src 'self'; script-src 'self'; img-src 'self' blob:; connect-src 'self'; frame-ancestors 'self'")
            if filename:self.send_header('Content-Disposition',"attachment; filename*=UTF-8''"+quote(filename))
            self.end_headers()
            try: self.wfile.write(body)
            except (BrokenPipeError,ConnectionResetError): pass
        def allowed(self,api=False):
            expected=f'127.0.0.1:{self.server.server_port}'
            if self.headers.get('Host')!=expected: return False
            origin=self.headers.get('Origin')
            if origin and origin!=f'http://{expected}': return False
            if api and not secrets.compare_digest(self.headers.get('X-App-Token',''),token): return False
            return True
        def do_GET(self):
            parsed=urlparse(self.path)
            api=parsed.path.startswith('/api/')
            if not self.allowed(api): return self.reply({'error':'本地访问验证失败'},403)
            q=parse_qs(parsed.query)
            try:
                if parsed.path=='/favicon.ico':return self.reply(b'',204,content_type='image/x-icon')
                if parsed.path=='/health': return self.reply({'app':'ai-chat-sandbox','version':'0.4','name':'SuperTeam'})
                if parsed.path=='/api/state':
                    with service.lock:
                        protected=[j['room'] for j in service.active()]+open_room_leases.touch(q.get('activeRoom',[]))
                        prefs=preferences.read();protected.extend(prefs.get(k) for k in ('currentRoom','lastRoom') if isinstance(prefs.get(k),str))
                        store.autoarchive(prefs['archiveDays'],protected)
                    from api_connector import APIConnector
                    api_configs=APIConnector(root).public()
                    for provider,config in api_configs.items():
                        if config.get('enabled'):catalog[provider]=[{'id':config['model'],'name':config['model'],'images':config.get('vision',False)}]
                    return self.reply({'apiProviders':api_configs,'rooms':store.list_rooms(),'jobs':service.active(),'providers':runner.status(),'models':catalog,'profiles':PROFILES,'desktop':desktop.pending(),'desktopHistory':desktop.history[-6:],'avatar':('/assets/avatar.png?v='+str((root/'ui/assets/avatar.png').stat().st_mtime_ns)) if (root/'ui/assets/avatar.png').exists() else '/assets/user.svg'})
                if parsed.path=='/api/room':
                    rid=q.get('id',[''])[0];room=store.room(rid);room['artifacts']=artifacts(rid);return self.reply(room)
                if parsed.path=='/api/library':return self.reply(file_library.snapshot())
                if parsed.path=='/api/search':
                    room=store.room(q.get('room',[''])[0]);return self.reply({'hits':retrieve(room['messages'],q.get('q',[''])[0],20)})
                if parsed.path=='/api/memory':
                    data={**memory.state(),'job':memory_worker.status()}
                    if q.get('room'):data['summary']=memory.summary(q['room'][0])
                    return self.reply(data)
                if parsed.path=='/api/api-config':
                    from api_connector import APIConnector
                    return self.reply({'configs':APIConnector(root).public()})
                if parsed.path=='/api/connections':return self.reply(connections.state())
                if parsed.path=='/api/preferences':
                    return self.reply(preferences.read())
                if parsed.path=='/api/settings-info':return self.reply(preferences.info())
                if parsed.path=='/api/export-json':
                    data=store.export_chat(q.get('id',[''])[0]);return self.reply({'name':data['room']['name']+'.json','text':json.dumps(data,ensure_ascii=False,indent=2)})
                if parsed.path=='/api/archive':return self.reply({'rooms':[{'id':r['id'],'name':r['name'],'updated':r['updated'],'preview':(r.get('last_message') or '')[:180]} for r in store.list_rooms()]})
                if parsed.path=='/api/skills':return self.reply({'skills':skills.scan(),'folder':str(skills.folder)})
                if parsed.path=='/api/skill':return self.reply(skills.content(q.get('id',[''])[0]))
                if parsed.path=='/api/contacts':
                    path=root/'data/contacts.json'
                    return self.reply({'ids':json.loads(path.read_text()) if path.exists() else ['doubao','workbuddy','qwen']})
                if parsed.path=='/api/quotas':return self.reply(quotas.read())
                if parsed.path=='/api/discover':return self.reply({'apps':scan(runner,q.get('query',q.get('q',['']))[0],q.get('all',['0'])[0]=='1')})
                if parsed.path=='/api/models':return self.reply(catalog)
                if parsed.path=='/api/file':
                    item=store.attachment(q.get('id',[''])[0],q.get('room',[''])[0]);path=Path((item.get('model_path') if q.get('preview') else None) or item['path'])
                    if not path.exists():raise ValueError('附件文件已移走')
                    return self.reply(path.read_bytes(),content_type=('image/png' if q.get('preview') and item.get('model_path') else item['mime']) if item['kind']=='image' else 'application/octet-stream',filename=item['name'])
                if parsed.path=='/api/preview':
                    item=store.attachment(q.get('id',[''])[0],q.get('room',[''])[0]);return self.reply({'name':item['name'],'text':item['text'][:40000],'note':item['note']})
                if parsed.path=='/api/artifact':
                    rid=q.get('room',[''])[0];relative=q.get('path',[''])[0];allowed=artifacts(rid)
                    if relative not in {a['path'] for a in allowed}:raise ValueError('成果文件不存在或不属于当前会话')
                    base=store.room_folder(rid,root).resolve();path=(base/relative).resolve()
                    if not path.is_relative_to(base) or path.stat().st_size>100*1024*1024:raise ValueError('文件路径或大小无效')
                    if q.get('text'):
                        from uploads import extract_text
                        text,note=extract_text(path);return self.reply({'text':text[:40000],'note':note})
                    return self.reply(path.read_bytes(),content_type=(mimetypes.guess_type(path.name)[0] or 'application/octet-stream') if q.get('preview') else 'application/octet-stream',filename=path.name)
                if parsed.path=='/api/job': return self.reply(service.job(q.get('id',[''])[0]))
                if parsed.path=='/api/export':
                    room=store.room(q.get('id',[''])[0])
                    text='# '+room['name']+'\n\n'+'\n\n'.join('## '+m['author']+(' · 用户采纳' if m.get('reaction')=='accepted' else ' · 用户支持' if m.get('reaction')=='supported' else '')+'\n\n'+m['text'] for m in room['messages'])
                    return self.reply({'name':room['name']+'.md','text':text})
                files={'/':('index.html','text/html; charset=utf-8'),'/refinements.js':('refinements.js','text/javascript; charset=utf-8'),'/refinements.css':('refinements.css','text/css; charset=utf-8'),'/desktop-ui.js':('desktop-ui.js','text/javascript; charset=utf-8'),'/desktop-ui.css':('desktop-ui.css','text/css; charset=utf-8'),'/superteam.js':('superteam.js','text/javascript; charset=utf-8'),'/app.js':('app.js','text/javascript; charset=utf-8'),'/style.css':('style.css','text/css; charset=utf-8')}
                files.update({'/'+name:(name,'text/javascript; charset=utf-8' if name.endswith('.js') else 'text/css; charset=utf-8') for name in ['workspace-controls.js','workspace-controls.css','workspace-layout.js','workspace-layout.css','file-library.js','file-library.css','settings-page.js','settings-page.css','i18n.js']})
                if parsed.path in files:
                    name,mime=files[parsed.path]
                    return self.reply((root/'ui'/name).read_bytes(),content_type=mime)
                if parsed.path.startswith('/assets/'):
                    name=parsed.path.removeprefix('/assets/');path=root/'ui/assets'/name
                    if name not in ['codex.png','deepseek.png','user.svg','group.svg','avatar.png','file-word.png','file-code.png','file-text.png','file-pdf.png','file-sheet.png','file-ppt.png','file-image.png','file-archive.png','file-audio.png','file-video.png','file-generic.png','superteam-logo.png','superteam-v1.png'] and not re.fullmatch(r'installed-[a-z0-9-]+\.png',name):raise ValueError('图片不存在')
                    return self.reply(path.read_bytes(),content_type=mimetypes.guess_type(name)[0] or 'image/png')
                self.reply({'error':'不存在'},404)
            except (ValueError,TypeError) as exc: self.reply({'error':str(exc)},400)
        def do_POST(self):
            if not self.allowed(True): return self.reply({'error':'本地访问验证失败'},403)
            try:
                length=int(self.headers.get('Content-Length','0'))
                if length<1 or length>72*1024*1024: raise ValueError('请求大小无效，单个文件最多 50 MB')
                body=json.loads(self.rfile.read(length))
                if not isinstance(body,dict): raise ValueError('请求格式错误')
                if self.path=='/api/rooms': return self.reply(store.create_room(body.get('name'),body.get('members'),body.get('settings'),preferences=preferences.read()))
                if self.path=='/api/api-config':
                    from api_connector import APIConnector
                    endpoint=APIConnector(root);provider=body.get('provider','api');action=body.get('action','save')
                    if action=='save':return self.reply({'configs':endpoint.save(provider,body)})
                    if action=='models':return self.reply({'models':endpoint.models(provider)})
                    if action=='image':
                        rid=body.get('room');store.room(rid);prompt=body.get('prompt','');raw=endpoint.generate(provider,prompt)
                        file=save_upload(store,root,rid,'生成图片-'+str(int(time.time()))+'.png','image/png',base64.b64encode(raw).decode())
                        with store.connect() as db:db.execute("UPDATE attachments SET note='API generated image' WHERE id=?",(file['id'],))
                        store.message(rid,'user',prompt);store.message(rid,provider,'图片已生成。',attachments=[file['id']]);return self.reply({'file':file})
                    if action=='test':return self.reply(endpoint.run(provider,'只回复 API_OK。',threading.Event(),lambda *a:None,test=True))
                    raise ValueError('未知 API 操作')
                if self.path=='/api/connections':
                    action=body.get('action')
                    if action=='scan':return self.reply(connections.discover())
                    if action=='configure':return self.reply(connections.configure(body.get('provider'),body.get('path','')))
                    if action=='test':return self.reply(connections.test(body.get('provider')))
                    if action=='models':
                        threading.Thread(target=refresh_models,daemon=True).start();return self.reply({'refreshing':True})
                    if action=='toggle':
                        connections.enabled=not connections.enabled
                        if not connections.enabled:
                            memory_worker.stop();connections.cancel.set()
                            for job in service.active():service.cancel(job['id'])
                        return self.reply(connections.state())
                    raise ValueError('未知连接操作')
                if self.path=='/api/send' and not connections.enabled:raise ValueError('连接未运行，请点击左下角电源启动')
                if self.path=='/api/send': return self.reply(service.dispatch(body.get('room'),body.get('text'),body.get('target','auto'),body.get('rounds'),body.get('attachments'),body.get('policy',{'queue':'queue','steer':'steer'}[preferences.read()['followupBehavior']]),body.get('topic','continue')))
                if self.path=='/api/open-data':os.startfile(str(root/'data'));return self.reply({'ok':True})
                if self.path=='/api/open-file':
                    rid=body.get('room');store.room(rid)
                    if body.get('artifact'):
                        base=store.room_folder(rid,root).resolve();path=(base/body.get('path','')).resolve()
                        if not path.is_relative_to(base) or not path.is_file():raise ValueError('成果文件不存在')
                    else:path=Path(store.attachment(body.get('id'),rid)['path'])
                    from native_services import NativeServices
                    opened=NativeServices(root).open_file(str(path),preferences.read()['fileDestination'])
                    if not opened.get('ok'):raise ValueError(opened.get('error','无法打开文件'))
                    return self.reply(opened)
                if self.path=='/api/memory' and body.get('action')=='refresh' and not connections.enabled:raise ValueError('连接未运行')
                if self.path=='/api/memory':
                    action=body.get('action')
                    if action=='save':memory.save_preference(body.get('key'),body.get('text'),manual=True)
                    elif action=='delete':
                        with store.connect() as db:cutoff=db.execute('SELECT COALESCE(MAX(id),0) FROM messages').fetchone()[0]
                        memory.delete(body.get('key'),cutoff)
                    elif action=='refresh':return self.reply({'job':memory_worker.schedule(body.get('room'),force=True)})
                    elif action=='stop':memory_worker.stop()
                    else:raise ValueError('记忆操作无效')
                    return self.reply({**memory.state(),'job':memory_worker.status()})
                if self.path=='/api/backup':
                    import sqlite3
                    folder=root/'backups';folder.mkdir(exist_ok=True);path=folder/('history-'+time.strftime('%Y%m%d-%H%M%S')+'.db')
                    with store.connect() as source:
                        with sqlite3.connect(path) as destination:source.backup(destination)
                    return self.reply({'path':str(path),'note':'已备份聊天记录；附件仍在原目录'})
                if self.path=='/api/open-skills':os.startfile(str(skills.folder));return self.reply({'ok':True})
                if self.path=='/api/preferences':
                    saved=preferences.update(body)
                    if not saved.get('memoryEnabled',True):memory_worker.stop()
                    return self.reply(saved)
                if self.path=='/api/import-chat':return self.reply(store.import_chat(body.get('data'),preferences=preferences.read()))
                if self.path=='/api/desktop-action':
                    rid=body.get('room','');provider=body.get('provider','')
                    if not any(j['room']==rid and provider in j['order'] for j in service.active()):raise ValueError('没有匹配的正在运行的任务')
                    return self.reply(desktop.request(rid,provider,body.get('tool'),body.get('arguments',{})))
                if self.path=='/api/desktop-verify':
                    import re as _re
                    raw=desktop.observations.get((body.get('room'),body.get('provider')),'')
                    try:
                        elements=json.loads(raw)
                        raw='\n'.join(str(e.get('name',''))+' '+str(e.get('value','')) for e in elements)
                    except (ValueError,TypeError):pass
                    answer=str(body.get('reply',''))
                    started=max((j['started'] for j in service.active() if j['room']==body.get('room') and body.get('provider') in j['order'] and j['status']=='running'),default=float('inf'))
                    events=[e for e in desktop.history if e['room']==body.get('room') and e['provider']==body.get('provider') and e['created']>=started]
                    last_read=max((e['created'] for e in events if e.get('action')=='read_window'),default=0)
                    sent=max((e['created'] for e in events if e.get('action')=='key' and e.get('key') in ['ENTER','CTRL+ENTER'] or e.get('action')=='click' and '发送' in e.get('detail','')),default=0)
                    verified=bool(sent and last_read>=sent and answer.strip()) and _re.sub(r'\s+','',answer) in _re.sub(r'\s+','',raw)
                    return self.reply({'verified':verified})
                if self.path=='/api/desktop-decision':
                    desktop.decide(body.get('room'),body.get('id'),body.get('approved'));return self.reply({'ok':True})
                if self.path=='/api/desktop-stop':
                    rid=body.get('room');store.update_settings(rid,{'computer':'off'});desktop.stop(rid)
                    for job in service.active():
                        if job['room']==rid:service.cancel(job['id'])
                    return self.reply({'ok':True})
                if self.path=='/api/contacts':
                    ident=body.get('id','')
                    if not any(a['id']==ident for a in scan(runner)):raise ValueError('请先扫描并选择已安装的软件')
                    path=root/'data/contacts.json'
                    ids=json.loads(path.read_text()) if path.exists() else ['doubao','workbuddy','qwen']
                    if ident not in ids:ids.append(ident)
                    path.write_text(json.dumps(ids),encoding='utf-8');return self.reply({'ids':ids})
                if self.path=='/api/open-ai':
                    app=next((a for a in scan(runner) if a['id']==body.get('id')),None)
                    if not app or not app.get('path'):raise ValueError('未找到可打开的安装位置')
                    path=Path(app['path'])
                    if path.is_file():os.startfile(str(path))
                    elif (path/'AppxManifest.xml').exists():
                        import xml.etree.ElementTree as ET,subprocess
                        manifest=ET.parse(path/'AppxManifest.xml');entry=next(e for e in manifest.iter() if e.tag.endswith('}Application'))
                        family=path.name.split('_')[0]+'_'+path.name.split('_')[-1]
                        subprocess.Popen(['explorer.exe','shell:AppsFolder'+chr(92)+family+'!'+entry.attrib['Id']],creationflags=subprocess.CREATE_NO_WINDOW)
                    else:raise ValueError('请从系统开始菜单打开该软件')
                    return self.reply({'ok':True})
                if self.path=='/api/skill-copy':return self.reply(skills.copy_shared(body.get('id')))
                if self.path=='/api/skill-toggle':return self.reply(skills.toggle(body.get('id'),bool(body.get('enabled'))))
                if self.path=='/api/skill-remove':return self.reply(skills.remove(body.get('id')))
                if self.path=='/api/skill-download':return self.reply(skills.download(body.get('url','')))
                if self.path=='/api/quotas-refresh':quotas.refresh();return self.reply(quotas.read())
                if self.path=='/api/avatar':
                    from PIL import Image
                    data=body.get('data','')
                    if not isinstance(data,str) or len(data)>8*1024*1024:raise ValueError('头像过大')
                    try:
                        raw=base64.b64decode(data,validate=True)
                        with Image.open(io.BytesIO(raw)) as im:
                            if im.width*im.height>25000000:raise ValueError('头像像素过大')
                            if im.width!=im.height:raise ValueError('请先裁剪为正方形')
                            temporary=root/'ui/assets/avatar.tmp'
                            im.convert('RGBA').resize((512,512)).save(temporary,format='PNG');temporary.replace(root/'ui/assets/avatar.png')
                    except Exception as exc:raise ValueError('头像图片无效，请重新选择') from exc
                    return self.reply({'ok':True})
                if self.path=='/api/visibility':
                    rid=body.get('room')
                    if any(j['room']==rid for j in service.active()):raise ValueError('请先停止正在回复的成员，再隐藏或删除聊天')
                    return self.reply(store.set_visibility(rid,body.get('value')))
                if self.path=='/api/react':
                    rid=body.get('room');result=store.react(rid,body.get('message'),body.get('value',''))
                    message=next(m for m in result['messages'] if m['id']==int(body.get('message',0)))
                    origin=next((m['text'] for m in reversed(result['messages']) if m['author']=='user' and m['id']<message['id']),'')
                    memory.feedback(rid,message['id'],message['author'],task_tag(origin),body.get('value',''))
                    return self.reply(result)
                if self.path=='/api/upload':return self.reply(save_upload(store,root,body.get('room'),body.get('name'),body.get('mime'),body.get('data')))
                if self.path=='/api/settings':
                    rid=body.get('room')
                    if any(j['room']==rid for j in service.active()):raise ValueError('请等当前回复结束后再修改模型或权限')
                    updates=body.get('settings',{})
                    if not isinstance(updates,dict) or not isinstance(updates.get('models',{}),dict):raise ValueError('设置格式无效')
                    for provider,model in updates.get('models',{}).items():
                        if model not in {m['id'] for m in catalog.get(provider,[])}:raise ValueError('请选择本机支持的模型')
                    return self.reply(store.update_settings(rid,updates))
                if self.path=='/api/workspace-path':
                    path=store.room_folder(body.get('room'),root);path.mkdir(parents=True,exist_ok=True)
                    return self.reply({'path':str(path)})
                if self.path=='/api/open-workspace':
                    rid=body.get('room');path=store.room_folder(rid,root);path.mkdir(parents=True,exist_ok=True)
                    from native_services import NativeServices
                    opened=NativeServices(root).open_file(str(path),preferences.read()['fileDestination'])
                    if not opened.get('ok'):raise ValueError(opened.get('error','无法打开目录'))
                    return self.reply(opened)
                if self.path=='/api/cancel': return self.reply(service.cancel(body.get('id')))
                if self.path=='/api/shutdown':
                    memory_worker.stop()
                    active=service.active()
                    for job in active: service.cancel(job['id'])
                    self.reply({'ok':True})
                    def shutdown():
                        deadline=time.monotonic()+20
                        for job in active: service.wait(job['id'],max(0,deadline-time.monotonic()))
                        self.server.shutdown()
                    threading.Thread(target=shutdown,daemon=True).start()
                    return
                self.reply({'error':'不存在'},404)
            except (ValueError,TypeError) as exc: self.reply({'error':str(exc)},400)
    httpd=ThreadingHTTPServer(('127.0.0.1',port),Handler)
    httpd.daemon_threads=True
    return httpd,token,service


if __name__=='__main__':
    instance_path=ROOT/'data/instance.json'
    try:instance=json.loads(instance_path.read_text(encoding='utf-8'))
    except (OSError,ValueError):instance={}
    try:server,token,service=make_server(port=instance.get('port',0),auth_token=instance.get('token'))
    except OSError:server,token,service=make_server(auth_token=instance.get('token'))
    runtime={'port':server.server_port,'token':token,'pid':os.getpid()}
    instance_path.write_text(json.dumps({'port':server.server_port,'token':token}),encoding='utf-8')
    (ROOT/'data'/'runtime.json').write_text(json.dumps(runtime),encoding='utf-8')
    try: server.serve_forever(poll_interval=.25)
    finally:
        server.server_close()
        runtime_path=ROOT/'data'/'runtime.json'
        if runtime_path.exists() and json.loads(runtime_path.read_text())['pid']==os.getpid(): runtime_path.unlink()

