"""User-configured OpenAI-compatible chat endpoints; Windows DPAPI secrets."""
import base64,ctypes,json,os,urllib.request,urllib.error,threading
_LOCK=threading.RLock()
def locked(fn):
 def call(*args,**kwargs):
  with _LOCK:return fn(*args,**kwargs)
 return call
from pathlib import Path
from urllib.parse import urlsplit
class Blob(ctypes.Structure):
 _fields_=[('size',ctypes.c_ulong),('data',ctypes.POINTER(ctypes.c_ubyte))]
def crypt(data,decrypt=False):
 if os.name!='nt':raise ValueError('密钥加密需要 Windows')
 buffer=ctypes.create_string_buffer(data);source=Blob(len(data),ctypes.cast(buffer,ctypes.POINTER(ctypes.c_ubyte)));out=Blob()
 fn=ctypes.windll.crypt32.CryptUnprotectData if decrypt else ctypes.windll.crypt32.CryptProtectData
 if not fn(ctypes.byref(source),None,None,None,None,1,ctypes.byref(out)):raise ValueError('本机密钥加解密失败')
 try:return ctypes.string_at(out.data,out.size)
 finally:ctypes.windll.kernel32.LocalFree(out.data)
class NoRedirect(urllib.request.HTTPRedirectHandler):
 def redirect_request(self,*args,**kwargs):raise ValueError('接口发生重定向，已阻止发送密钥；请填写最终服务地址')
class APIConnector:
 def __init__(self,root):self.path=Path(root)/'data/api-connections.json'
 def read(self):
  try:return json.loads(self.path.read_text(encoding='utf-8'))
  except (OSError,ValueError):return {}
 def public(self):return {p:{k:v for k,v in c.items() if k!='secret'}|{'has_key':bool(c.get('secret'))} for p,c in self.read().items()}
 @locked
 def save(self,provider,body):
  if provider not in ['api','doubao','qwen','codex','deepseek','workbuddy']:raise ValueError('未知成员')
  data=self.read();old=data.get(provider,{})
  if body.get('remove'):data.pop(provider,None)
  else:
   base=str(body.get('base_url','')).strip().rstrip('/');url=urlsplit(base)
   if url.scheme not in ['https','http'] or not url.hostname or url.username or url.password or url.query or url.fragment:raise ValueError('请输入有效的接口地址，不要包含密钥或查询参数')
   if url.scheme=='http' and url.hostname not in ['localhost','127.0.0.1','::1']:raise ValueError('远程接口必须使用 HTTPS')
   model=str(body.get('model','')).strip()
   if not model or len(model)>250:raise ValueError('请输入模型 ID')
   if base.endswith('/chat/completions'):base=base[:-17].rstrip('/')
   key=body.get('key','');secret=base64.b64encode(crypt(key.encode())).decode() if key else old.get('secret','')
   if key and len(key)>4096:raise ValueError('密钥长度无效')
   data[provider]={'base_url':base,'model':model,'enabled':bool(body.get('enabled',True)),'vision':bool(body.get('vision',False)),'secret':secret,'image_model':str(body.get('image_model',old.get('image_model','')))[:250],'verified':old.get('verified',False) if not key and old.get('model')==model and old.get('base_url')==base else False}
  self.path.parent.mkdir(exist_ok=True,parents=True);temp=self.path.with_suffix('.tmp');temp.write_text(json.dumps(data,ensure_ascii=False),encoding='utf-8');temp.replace(self.path);return self.public()
 def enabled(self,provider):return self.read().get(provider,{}).get('enabled',False)
 def request(self,config,route,body=None,timeout=45):
  key=crypt(base64.b64decode(config['secret']),True).decode() if config.get('secret') else ''
  headers={'Content-Type':'application/json'}
  if key:headers['Authorization']='Bearer '+key
  req=urllib.request.Request(config['base_url']+route,data=json.dumps(body,ensure_ascii=False).encode() if body is not None else None,headers=headers)
  try:
   with urllib.request.build_opener(NoRedirect()).open(req,timeout=timeout) as response:
    raw=response.read(8*1024*1024+1)
    if len(raw)>8*1024*1024:raise ValueError('接口响应过大')
    return json.loads(raw)
  except urllib.error.HTTPError as e:raise ValueError('API 请求失败 HTTP '+str(e.code)+'；请检查地址、模型、密钥和余额') from None
  except urllib.error.URLError:raise ValueError('无法连接 API 服务，请检查网络和服务地址') from None
 def models(self,provider):
  config=self.read().get(provider)
  if not config:raise ValueError('请先保存 API 配置')
  result=self.request(config,'/models');return [{'id':x['id'],'name':x['id']} for x in result.get('data',[]) if isinstance(x,dict) and isinstance(x.get('id'),str)][:200]
 def run(self,provider,prompt,cancel,on_event,images=None,model='',test=False):
  config=self.read().get(provider)
  if not config or not config.get('enabled'):raise ValueError('请先启用 API 配置')
  if images and not config.get('vision'):raise ValueError('此 API 未启用图片输入，请先确认模型支持视觉')
  prompt+='\n当前为 API 文本/图片通道，没有本地执行工具。不得声称已操作电脑、修改文件或完成未执行的动作。'
  content=[{'type':'text','text':prompt}]
  for image in images or []:
   path=Path(image.get('model_path') or image['path'])
   if path.stat().st_size>20*1024*1024:raise ValueError('单张图片最多20MB')
   content.append({'type':'image_url','image_url':{'url':'data:'+image.get('mime','image/png')+';base64,'+base64.b64encode(path.read_bytes()).decode()}})
  if cancel.is_set():raise ValueError('已停止')
  on_event('status','正在请求配置的 API 服务')
  result=self.request(config,'/chat/completions',{'model':model or config['model'],'messages':[{'role':'user','content':content if images else prompt}],'max_tokens':32 if test else 2048,'stream':False})
  if cancel.is_set():raise ValueError('已停止')
  try:text=result['choices'][0]['message']['content']
  except (KeyError,IndexError,TypeError):raise ValueError('接口未返回兼容的聊天结果') from None
  if not isinstance(text,str) or not text.strip():raise ValueError('接口返回了空回答')
  if isinstance(result.get('usage'),dict):on_event('usage',{**result['usage'],'input_tokens':result['usage'].get('prompt_tokens',0),'output_tokens':result['usage'].get('completion_tokens',0)})
  self.mark_verified(provider,config)
  on_event('text',text);return {'text':text,'session_id':None}

 def generate(self,provider,prompt):
  config=self.read().get(provider)
  if not config or not config.get('enabled') or not config.get('image_model'):raise ValueError('请先设置并启用图片生成模型')
  if not isinstance(prompt,str) or not prompt.strip() or len(prompt)>4000:raise ValueError('图片描述需要1–4000个字符')
  payload={'model':config['image_model'],'prompt':prompt,'response_format':'url','size':'2K' if 'volces.com' in config['base_url'] else '1024x1024','stream':False}
  if 'volces.com' in config['base_url']:payload['watermark']=True
  else:payload['n']=1
  result=self.request(config,'/images/generations',payload,timeout=120)
  if len(result.get('data',[]))!=1:raise ValueError('服务未返回单张图片')
  item=result['data'][0]
  if item.get('b64_json'):raw=base64.b64decode(item['b64_json'],validate=True)
  else:
   import socket,ipaddress
   url=item.get('url','');parts=urlsplit(url)
   if parts.scheme!='https' or not parts.hostname or parts.username or parts.password:raise ValueError('服务返回的图片地址无效')
   if any(not ipaddress.ip_address(info[4][0]).is_global for info in socket.getaddrinfo(parts.hostname,443)):raise ValueError('禁止下载私有网络图片地址')
   with urllib.request.build_opener(NoRedirect()).open(url,timeout=45) as response:raw=response.read(20*1024*1024+1)
  if len(raw)>20*1024*1024:raise ValueError('生成图片超过20MB')
  from PIL import Image
  import io
  with Image.open(io.BytesIO(raw)) as image:
   if image.width*image.height>40000000:raise ValueError('图片像素超过上限')
   image.load();output=io.BytesIO();image.convert('RGB').save(output,format='PNG');return output.getvalue()

 @locked
 def mark_verified(self,provider,original):
  current=self.read();value=current.get(provider,{})
  if any(value.get(k)!=original.get(k) for k in ['base_url','model','secret']):return
  value['verified']=True
  temp=self.path.with_suffix('.verified.tmp');temp.write_text(json.dumps(current,ensure_ascii=False),encoding='utf-8');temp.replace(self.path)
