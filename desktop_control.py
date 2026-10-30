"""Room-scoped desktop broker. File access never grants desktop access."""
import threading,time,uuid

class DesktopBroker:
    def __init__(self,enabled,execute,timeout=120):
        self.enabled=enabled;self.execute=execute;self.timeout=timeout
        self.observations={};self.items={};self.lock=threading.RLock();self.action_lock=threading.Lock();self.history=[]
    def pending(self):
        with self.lock:return [{k:v for k,v in x.items() if k not in ['event','approved']} for x in self.items.values()]
    def decide(self,room,ident,approved):
        with self.lock:
            item=self.items.get(ident)
            if not item or item['room']!=room:raise ValueError('操作请求已过期或不属于当前聊天')
            item['approved']=approved is True;item['event'].set()
    def stop(self,room):
        with self.lock:
            for item in self.items.values():
                if item['room']==room:item['approved']=False;item['event'].set()
    def request(self,room,provider,tool,args):
        if not self.enabled(room):raise ValueError('此聊天未开启电脑操控，或已停止')
        if tool not in ['windows','focus','screenshot','click','type','key','scroll','read_window']:raise ValueError('不支持的电脑操作')
        key=str(args.get('key','')).upper()
        critical=tool=='click' or tool=='key' and key not in ['TAB','ESC','ESCAPE','LEFT','RIGHT','UP','DOWN','CTRL+A'] or tool=='type' and ('\n' in str(args.get('text','')) or '\r' in str(args.get('text','')))
        summary={'windows':'列出可见窗口','focus':'切换目标窗口','screenshot':'查看目标窗口截图','read_window':'读取目标窗口界面文字','click':'点击目标位置（点击可能触发提交）','type':'输入文字','key':'按键 '+key,'scroll':'滚动窗口'}[tool]
        if critical:
            item={'id':uuid.uuid4().hex,'room':room,'provider':provider,'action':tool,'summary':summary,'detail':str(args.get('description') or args.get('key') or '')[:300],'created':time.time(),'event':threading.Event(),'approved':False}
            with self.lock:self.items[item['id']]=item
            try:
                deadline=time.monotonic()+self.timeout
                while not item['event'].wait(.2):
                    if not self.enabled(room):raise ValueError('电脑操控已停止')
                    if time.monotonic()>deadline:raise ValueError('操作确认超时，未执行')
                if not item['approved']:raise ValueError('用户拒绝了这次操作，未执行')
            finally:
                with self.lock:self.items.pop(item['id'],None)
        if not self.enabled(room):raise ValueError('电脑操控已停止，未执行操作')
        with self.action_lock:
            if not self.enabled(room):raise ValueError('电脑操控已停止，未执行操作')
            result=self.execute(tool,args)
        with self.lock:
            if tool=='read_window':
                content='\n'.join(x.get('text','') for x in result.get('content',[]) if x.get('type')=='text')
                self.observations[(room,provider)]=content[-50000:]
            self.history.append({'room':room,'provider':provider,'summary':summary,'action':tool,'key':key,'detail':str(args.get('description',''))[:300],'created':time.time()});self.history=self.history[-60:]
            return result
