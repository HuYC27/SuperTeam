import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch
import urllib.request
import urllib.error
import server


class HttpTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        with patch.object(server,'ROOT',Path(self.tmp.name)):
            self.httpd,self.token,self.service=server.make_server(discover_models=False)
        self.base='http://127.0.0.1:'+str(self.httpd.server_port)
        self.thread=threading.Thread(target=self.httpd.serve_forever,daemon=True)
        self.thread.start()
    def tearDown(self):
        self.httpd.shutdown();self.httpd.server_close();self.thread.join();self.tmp.cleanup()
    def test_no_token_rejected(self):
        with self.assertRaises(urllib.error.HTTPError) as result: urllib.request.urlopen(self.base+'/api/state')
        self.assertEqual(result.exception.code,403)
    def test_foreign_origin_rejected(self):
        req=urllib.request.Request(self.base+'/api/state',headers={'X-App-Token':self.token,'Origin':'https://example.com'})
        with self.assertRaises(urllib.error.HTTPError) as result: urllib.request.urlopen(req)
        self.assertEqual(result.exception.code,403)
    def test_default_rooms_and_create_export(self):
        headers={'X-App-Token':self.token,'Content-Type':'application/json'}
        req=urllib.request.Request(self.base+'/api/state',headers=headers)
        with urllib.request.urlopen(req) as response: state=json.load(response)
        self.assertEqual(len(state['rooms']),3)
        req=urllib.request.Request(self.base+'/api/rooms',data=json.dumps({'name':'test','members':['codex']}).encode(),headers=headers)
        with urllib.request.urlopen(req) as response: room=json.load(response)
        req=urllib.request.Request(self.base+'/api/export?id='+room['id'],headers=headers)
        with urllib.request.urlopen(req) as response: exported=json.load(response)
        self.assertIn('# test',exported['text'])
    def test_avatar_is_validated_and_saved_as_square(self):
        import io,base64
        from PIL import Image
        root=Path(self.tmp.name);(root/'ui/assets').mkdir(parents=True)
        out=io.BytesIO();Image.new('RGB',(100,100),'green').save(out,format='PNG')
        headers={'X-App-Token':self.token,'Content-Type':'application/json'}
        req=urllib.request.Request(self.base+'/api/avatar',data=json.dumps({'data':base64.b64encode(out.getvalue()).decode()}).encode(),headers=headers)
        with urllib.request.urlopen(req) as response:self.assertTrue(json.load(response)['ok'])
        with Image.open(root/'ui/assets/avatar.png') as image:self.assertEqual(image.size,(512,512))
        invalid=urllib.request.Request(self.base+'/api/avatar',data=b'{"data":"not an image"}',headers=headers)
        with self.assertRaises(urllib.error.HTTPError):urllib.request.urlopen(invalid)

if __name__=='__main__': unittest.main()
