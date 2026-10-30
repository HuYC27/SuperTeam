"""Portable discovery and explicit connector lifecycle, without credential access."""
import json,os,shutil,threading,time
from pathlib import Path
class Connections:
 def __init__(self,root,runner):
  self.root=Path(root);self.runner=runner;self.enabled=True;self.cancel=threading.Event();self.lock=threading.Lock();self.tests={};self.paths=self.read();self.apply()
 def read(self):
  try:return json.loads((self.root/'data/connections.json').read_text(encoding='utf-8'))
  except (OSError,ValueError):return {}
 def apply(self):
  if self.paths.get('deepseek'):self.runner.deepseek=Path(self.paths['deepseek'])
  self.runner.workbuddy_cli=Path(self.paths['workbuddy']) if self.paths.get('workbuddy') else None
 def configure(self,provider,path):
  if provider not in ['deepseek','workbuddy']:raise ValueError('请选择支持的连接器')
  p=Path(path)
  if provider=='workbuddy' and p.suffix.lower()=='.exe':p=p.parent/'resources/app.asar.unpacked/cli/dist/codebuddy.js'
  expected='deepseek harness.exe' if provider=='deepseek' else 'codebuddy.js'
  if not p.is_absolute() or not p.is_file() or p.name.lower()!=expected:raise ValueError('请选择正确的本机程序文件：'+expected)
  self.paths[provider]=str(p.resolve());self.apply();folder=self.root/'data';folder.mkdir(exist_ok=True);temp=folder/'connections.tmp';temp.write_text(json.dumps(self.paths,ensure_ascii=False),encoding='utf-8');temp.replace(folder/'connections.json');return self.state()
 def discover(self):
  from discovery import inventory
  candidates=[]
  for item in inventory():
   raw=str(item.get('path') or '').strip(chr(34));p=Path(raw);base=p.parent if p.suffix.lower()=='.exe' else p
   if 'deepseek' in (item['name']+' '+raw).lower():candidates.append(('deepseek',base/'DeepSeek Harness.exe'))
   if 'workbuddy' in (item['name']+' '+raw).lower():
    candidates.append(('workbuddy',base/'resources/app.asar.unpacked/cli/dist/codebuddy.js'))
  for base in [Path(os.environ.get('LOCALAPPDATA',''))/'Programs',Path(os.environ.get('ProgramFiles','C:/Program Files'))]:
   for name in ['DeepSeek Harness','DeepSeek harness','WorkBuddy','WorkBuddyAI']:
    candidates.extend([('deepseek',base/name/'DeepSeek Harness.exe'),('workbuddy',base/name/'resources/app.asar.unpacked/cli/dist/codebuddy.js')])
  for provider,path in candidates:
   if path.is_file():self.configure(provider,str(path))
  return self.state()
 def state(self):
  return {'enabled':self.enabled,'providers':self.runner.status(),'paths':self.paths,'tests':dict(self.tests),'scope':'仅管理 SuperTeam 的连接；原软件窗口由用户管理'}
 def test(self,provider):
  if provider not in ['codex','deepseek','workbuddy']:raise ValueError('此软件尚未进入已支持名单')
  if not self.enabled:raise ValueError('请先启动连接')
  with self.lock:
   if any(x.get('status')=='running' for x in self.tests.values()):raise ValueError('已有接入检查正在运行')
   self.cancel=threading.Event();self.tests[provider]={'status':'running','started':time.time()}
  def run():
   try:
    folder=self.root/'work/connection-check';folder.mkdir(parents=True,exist_ok=True)
    answer=self.runner.run(provider,'只回复 SUPERTEAM_OK，不操作工具或文件。',None,folder,self.cancel,lambda *a:None,permission='read-only',mode='chat',control={'background':True,'mode':'off','speed':'fast','pluginsEnabled':False})
    ok='SUPERTEAM_OK' in answer.get('text','');self.tests[provider]={'status':'verified' if ok else 'failed','detail':'账号收发通过' if ok else '返回内容不符合测试要求','checked':time.time()}
   except Exception as e:self.tests[provider]={'status':'failed','detail':str(e)[:400],'checked':time.time()}
  threading.Thread(target=run,daemon=True).start();return self.state()
