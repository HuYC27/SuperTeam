"""Minimal stdio MCP facade for the local, authenticated approval broker."""
import json,sys,urllib.request,os
from pathlib import Path

SCHEMA={
 'windows':{},
 'focus':{'hwnd':{'type':'integer'}},
 'screenshot':{'hwnd':{'type':'integer'}},
 'read_window':{'hwnd':{'type':'integer'}},
 'click':{'hwnd':{'type':'integer'},'x':{'type':'number'},'y':{'type':'number'},'description':{'type':'string'}},
 'type':{'hwnd':{'type':'integer'},'text':{'type':'string'}},
 'key':{'hwnd':{'type':'integer'},'key':{'type':'string'}},
 'scroll':{'hwnd':{'type':'integer'},'delta':{'type':'integer'}}}
DESCRIPTIONS={'windows':'列出可见窗口，选择明确目标。','focus':'激活目标窗口。','screenshot':'查看目标窗口。点击坐标使用这张截图的像素坐标。','read_window':'读取目标窗口的无障碍界面文字，不读取密码。','click':'点击截图坐标；需用户确认，description 必须说明目的及可能后果。','type':'向目标窗口当前输入焦点输入文字。不清空已有草稿，不得输入密码或验证码。','key':'按键，如 ENTER、TAB、CTRL+A。发送、删除等关键按键先确认。','scroll':'滚动目标窗口，delta 为正向下、负向上。'}
def serve(root,room,provider):
    for stream in (sys.stdin,sys.stdout):
        if hasattr(stream,'reconfigure'):stream.reconfigure(encoding='utf-8')
    for line in sys.stdin:
        try:
            request=json.loads(line);method=request.get('method');ident=request.get('id')
            if ident is None:continue
            if method=='initialize':result={'protocolVersion':'2024-11-05','capabilities':{'tools':{}},'serverInfo':{'name':'superteam-computer','version':'0.1'}}
            elif method=='tools/list':result={'tools':[{'name':name,'description':DESCRIPTIONS[name],'annotations':{'readOnlyHint':name in ['windows','screenshot','read_window'],'destructiveHint':name in ['click','type','key'],'openWorldHint':True},'inputSchema':{'type':'object','properties':props,'additionalProperties':False,'required':list(props)}} for name,props in SCHEMA.items()]}
            elif method=='tools/call':
                runtime=json.loads((Path(root)/'data/runtime.json').read_text(encoding='utf-8'));p=request.get('params',{})
                payload={'room':room,'provider':provider,'tool':p['name'],'arguments':p.get('arguments',{})}
                req=urllib.request.Request(f"http://127.0.0.1:{runtime['port']}/api/desktop-action",data=json.dumps(payload).encode(),headers={'Content-Type':'application/json','X-App-Token':runtime['token']})
                try:result=json.load(urllib.request.urlopen(req,timeout=135))
                except Exception as error:
                    message='操作未完成'
                    if hasattr(error,'read'):
                        try:message=json.loads(error.read()).get('error',message)
                        except Exception:pass
                    result={'isError':True,'content':[{'type':'text','text':message}]}
            elif method=='ping':result={}
            else:
                print(json.dumps({'jsonrpc':'2.0','id':ident,'error':{'code':-32601,'message':'Unknown method'}}),flush=True);continue
            print(json.dumps({'jsonrpc':'2.0','id':ident,'result':result},ensure_ascii=False),flush=True)
        except Exception:
            print(json.dumps({'jsonrpc':'2.0','id':request.get('id') if 'request' in locals() else None,'error':{'code':-32603,'message':'Local desktop tool failed'}}),flush=True)
if __name__=='__main__':
    base=Path(sys.executable).parent if getattr(sys,'frozen',False) else Path(__file__).parent
    marker=base/'app-root.json'
    root=Path(json.loads(marker.read_text(encoding='utf-8-sig'))['root']) if marker.exists() else Path(os.environ.get('SUPERTEAM_ROOT',str(base)))
    serve(root,sys.argv[1],sys.argv[2] if len(sys.argv)>2 else 'codex')
