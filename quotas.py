"""Read-only account quota snapshots. Missing data never means a full allowance."""
import threading,time,subprocess,os,json
from pathlib import Path
from rpc import RpcProcess
from adapters import find_codex

class Quotas:
    def __init__(self,root):self.root=root;self.values={};self.lock=threading.Lock();self.refreshing=False
    def read(self):return {'providers':self.values,'refreshing':self.refreshing}
    def refresh(self):
        if not self.lock.acquire(blocking=False):return
        self.refreshing=True
        def run():
            rpc=None
            try:
                rpc=RpcProcess([find_codex(),'app-server'],cwd=str(self.root))
                rpc.call('initialize',{'clientInfo':{'name':'superteam','version':'0.4'}},timeout=15);rpc.send({'method':'initialized','params':{}})
                result=rpc.call('account/rateLimits/read',{},timeout=20)
                buckets=result.get('rateLimitsByLimitId') or {'default':result.get('rateLimits')}
                windows=[]
                for key,bucket in buckets.items():
                    if not isinstance(bucket,dict):continue
                    for slot in ['primary','secondary']:
                        win=bucket.get(slot)
                        if isinstance(win,dict) and isinstance(win.get('usedPercent'),(int,float)):
                            windows.append({'name':str(bucket.get('limitName') or key)+' · '+slot,'remaining':max(0,min(100,100-win['usedPercent'])),'windowMinutes':win.get('windowDurationMins'),'resetsAt':win.get('resetsAt')})
                self.values={**self.values,'codex':{'available':bool(windows),'windows':windows,'checkedAt':time.time(),'note':'原软件实时报告，多个窗口分别计算' if windows else '原软件未提供可显示的额度'}}
            except Exception:self.values={**self.values,'codex':{'available':False,'windows':[],'checkedAt':time.time(),'note':'暂无法读取，请在 Codex 中查看'}}
            finally:
                if rpc:rpc.close()
                try:
                    exe=Path(r'D:\Softwares\DeepSeek harness\DeepSeek Harness.exe')
                    p=subprocess.run([str(exe),'--expose-internals',str(self.root/'work/read_deepseek_balance.mjs')],env={**os.environ,'ELECTRON_RUN_AS_NODE':'1'},capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=40,creationflags=subprocess.CREATE_NO_WINDOW)
                    line=next(x for x in p.stdout.splitlines() if x.startswith('SUPERTEAM_BALANCE '))
                    data=json.loads(line.split(' ',1)[1])
                    self.values['deepseek']={'available':bool(data.get('ready')),'kind':'balance','wallets':data.get('wallets',[]),'checkedAt':time.time(),'note':'原软件账户余额'}
                except Exception:self.values['deepseek']={'available':False,'kind':'balance','note':'余额暂无法读取，请在原软件查看'}
                self.refreshing=False;self.lock.release()
        threading.Thread(target=run,daemon=True).start()
