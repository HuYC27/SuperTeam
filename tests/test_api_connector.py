import json,tempfile,threading,unittest
from pathlib import Path
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from api_connector import APIConnector
class APITests(unittest.TestCase):
 def test_local_roundtrip_and_redacted_key(self):
  seen=[]
  class Handler(BaseHTTPRequestHandler):
   def log_message(self,*args):pass
   def do_POST(self):
    seen.append(json.loads(self.rfile.read(int(self.headers['Content-Length']))));self.send_response(200);self.end_headers();self.wfile.write(b'{"choices":[{"message":{"content":"API_OK"}}]}')
  server=ThreadingHTTPServer(('127.0.0.1',0),Handler);threading.Thread(target=server.serve_forever,daemon=True).start()
  try:
   with tempfile.TemporaryDirectory() as folder:
    api=APIConnector(folder);api.save('api',{'base_url':f'http://127.0.0.1:{server.server_port}/v1','model':'fixture','key':'synthetic-key'})
    self.assertNotIn('synthetic-key',api.path.read_text());self.assertNotIn('secret',api.public()['api']);self.assertTrue(api.public()['api']['has_key'])
    result=api.run('api','hello',threading.Event(),lambda *a:None,test=True);self.assertEqual(result['text'],'API_OK');self.assertEqual(seen[0]['max_tokens'],32)
    api.save('api',{'base_url':f'http://127.0.0.1:{server.server_port}/v1','model':'fixture'});self.assertTrue(api.public()['api']['has_key'])
    with self.assertRaises(ValueError):api.save('api',{'base_url':'http://example.com','model':'x'})
    with self.assertRaises(ValueError):api.run('api','image',threading.Event(),lambda *a:None,images=[{}])
  finally:server.shutdown();server.server_close()

 def test_image_generation_uses_separate_model_and_returns_png(self):
  import base64,io
  from PIL import Image
  from unittest.mock import patch
  with tempfile.TemporaryDirectory() as folder:
   api=APIConnector(folder);api.save('doubao',{'base_url':'https://ark.cn-beijing.volces.com/api/v3','model':'chat','image_model':'image-test'})
   buf=io.BytesIO();Image.new('RGB',(4,4),'red').save(buf,format='PNG')
   with patch.object(api,'request',return_value={'data':[{'b64_json':base64.b64encode(buf.getvalue()).decode()}]}) as request:
    raw=api.generate('doubao','test image');self.assertTrue(raw.startswith(b'\x89PNG'));self.assertEqual(request.call_args.args[2]['model'],'image-test');self.assertEqual(request.call_args.args[1],'/images/generations')
