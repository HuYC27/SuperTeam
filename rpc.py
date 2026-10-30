"""Small stdio JSON-RPC transport for the locally installed application."""
import json
import queue
import subprocess
import tempfile
import threading
import time

class RpcError(RuntimeError): pass

class RpcProcess:
    def __init__(self,command,cwd=None,env=None,cancel=None,notify=None):
        self.cancel=cancel or threading.Event();self.notify=notify or (lambda event:None)
        self.queue=queue.Queue();self.seq=0;self.pending={};self.stderr=tempfile.TemporaryFile()
        self.proc=subprocess.Popen(command,cwd=cwd,env=env,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=self.stderr,
                                   creationflags=subprocess.CREATE_NO_WINDOW)
        def reader():
            try:
                for line in self.proc.stdout:
                    try:self.queue.put(json.loads(line))
                    except (ValueError,UnicodeError):pass
            finally:self.queue.put(None)
        self.reader=threading.Thread(target=reader,daemon=True);self.reader.start()
    def send(self,message):
        self.proc.stdin.write((json.dumps(message,ensure_ascii=False)+'\n').encode('utf-8'));self.proc.stdin.flush()
    def call(self,method,params=None,timeout=240):
        self.seq+=1;rid=self.seq;self.send({'jsonrpc':'2.0','id':rid,'method':method,'params':params or {}})
        deadline=time.monotonic()+timeout
        while time.monotonic()<deadline:
            if self.cancel.is_set():raise RpcError('已停止')
            if rid in self.pending:message=self.pending.pop(rid)
            else:
                try:message=self.queue.get(timeout=.12)
                except queue.Empty:continue
            if message is None:raise RpcError('本机 AI 服务提前退出，请检查原软件登录状态。')
            if 'method' in message:
                self.notify(message)
                if 'id' in message:
                    self.send({'id':message['id'],'error':{'code':-32601,'message':'Interactive approval is unavailable in this connector'}})
                continue
            if message.get('id')!=rid:
                self.pending[message.get('id')]=message;continue
            if 'error' in message:raise RpcError(str(message['error'].get('message','本机服务请求失败')))
            return message.get('result',{})
        raise RpcError('本轮等待超过时限，已停止。')
    def close(self):
        from adapters import stop_process
        if not self.proc.stdin.closed:
            try:self.proc.stdin.close()
            except OSError:pass
        try:self.proc.wait(timeout=2)
        except subprocess.TimeoutExpired:stop_process(self.proc)
        self.reader.join(timeout=2);self.proc.stdout.close();self.stderr.close()

