import base64
import tempfile
import io
import threading
import unittest
from pathlib import Path
from core import Store,ChatService
from uploads import save_upload
from workflow import choose_order,resolve_target

class Recorder:
    def __init__(self):self.calls=[]
    def run(self,provider,prompt,session_id,cwd,cancel,on_event,**options):
        self.calls.append((provider,prompt,options))
        return {'text':provider+' actual result','session_id':provider+'-id'}

class UpgradeTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
        self.store=Store(self.root/'history.db');self.runner=Recorder();self.service=ChatService(self.store,self.runner,self.root)
        self.rid=self.store.create_room('group',['codex','deepseek'])['id']
    def tearDown(self):self.tmp.cleanup()
    def test_default_handoff_reads_first_reply(self):
        self.store.update_settings(self.rid,{'conversation':'handoff'})
        j=self.service.submit(self.rid,'请实现一个 Python 数据处理脚本')
        self.service.wait(j['id'],5)
        self.assertEqual(self.service.job(j['id'])['status'],'completed')
        self.assertEqual([c[0] for c in self.runner.calls],['codex','deepseek'])
        self.assertIn('codex actual result',self.runner.calls[1][1])
    def test_mention_everyone_independent_snapshot(self):
        j=self.service.submit(self.rid,'@全体成员 各自独立建议')
        self.service.wait(j['id'],5)
        self.assertEqual(len(self.runner.calls),2)
        for c in self.runner.calls:self.assertNotIn('actual result',c[1])
    def test_explicit_mention_only_one_member(self):
        j=self.service.submit(self.rid,'@DeepSeek 分析这个思路')
        self.service.wait(j['id'],5)
        self.assertEqual([c[0] for c in self.runner.calls],['deepseek'])
    def test_room_settings_forwarded(self):
        self.store.update_settings(self.rid,{'permission':'workspace-write','models':{'codex':'selected-model'}})
        j=self.service.submit(self.rid,'@Codex hello');self.service.wait(j['id'],5)
        self.assertEqual(self.runner.calls[0][2]['model'],'selected-model')
        self.assertEqual(self.runner.calls[0][2]['permission'],'workspace-write')
    def test_file_content_and_room_binding(self):
        upload=save_upload(self.store,self.root,self.rid,'notes.txt','text/plain',base64.b64encode('专用验证文字'.encode()).decode())
        j=self.service.submit(self.rid,'@Codex 读文件',attachments=[upload['id']]);self.service.wait(j['id'],5)
        self.assertIn('专用验证文字',self.runner.calls[0][1])
        other=self.store.create_room('other',['codex'])['id']
        with self.assertRaises(ValueError):self.service.submit(other,'read',attachments=[upload['id']])
    def test_fake_image_rejected(self):
        with self.assertRaises(ValueError):save_upload(self.store,self.root,self.rid,'fake.png','image/png',base64.b64encode(b'not an image').decode())
    def test_older_unseen_images_have_explicit_omission_notice(self):
        from PIL import Image
        raw=io.BytesIO();Image.new('RGB',(2,2),'white').save(raw,format='PNG');encoded=base64.b64encode(raw.getvalue()).decode()
        ids=[save_upload(self.store,self.root,self.rid,f'image{i}.png','image/png',encoded)['id'] for i in range(8)]
        first=self.service.submit(self.rid,'@Codex 读第一组',attachments=ids[:4]);self.service.wait(first['id'],5)
        second=self.service.submit(self.rid,'@DeepSeek 读全部图片',attachments=ids[4:]);self.service.wait(second['id'],5)
        self.assertIn('较早图片未附带',self.runner.calls[-1][1])
        self.assertTrue(any('较早图片未附带' in m['text'] for m in self.store.room(self.rid)['messages'] if m['author']=='system'))
    def test_mode_is_per_room_and_controls_prompt(self):
        self.store.update_settings(self.rid,{'mode':'work'})
        j=self.service.submit(self.rid,'@Codex 回答');self.service.wait(j['id'],5)
        self.assertIn('详实认真',self.runner.calls[0][1])
        second=self.store.create_room('chat',['codex'])['id']
        self.assertEqual(self.store.room(second)['settings']['mode'],'chat')
    def test_explanation_routes_to_deepseek_first(self):
        order,_=choose_order('解释训练集和测试集为什么要隔离',['codex','deepseek'])
        self.assertEqual(order[0],'deepseek')
    def test_custom_strengths_change_order(self):
        order,_=choose_order('请编程实现 Python 脚本',['codex','deepseek'],roles={'codex':'文献分析','deepseek':'Python 编程、代码实现'})
        self.assertEqual(order[0],'deepseek')
    def test_permission_change_rebinds_backend_session(self):
        seen=[]
        original=self.runner.run
        def record(provider,prompt,sid,*args,**kwargs):
            seen.append(sid);return original(provider,prompt,sid,*args,**kwargs)
        self.runner.run=record
        a=self.service.submit(self.rid,'@Codex hello');self.service.wait(a['id'],5)
        self.store.update_settings(self.rid,{'permission':'workspace-write'})
        b=self.service.submit(self.rid,'@Codex continue');self.service.wait(b['id'],5)
        self.assertEqual(seen,[None,None])

if __name__=='__main__':unittest.main()
