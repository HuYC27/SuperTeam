import unittest,tempfile,io,base64,zipfile,threading
from pathlib import Path
from PIL import Image
from core import Store,ChatService
from uploads import save_upload
from skill_library import SkillLibrary
from test_upgrade import Recorder

class DesktopUpgradeTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name);self.store=Store(self.root/'data/history.db');self.rid=self.store.create_room('test',['codex'])['id']
    def tearDown(self):self.tmp.cleanup()
    def test_bmp_and_tiff_keep_original_but_send_png(self):
        for fmt in ['BMP','TIFF','PNG','JPEG','WEBP']:
            raw=io.BytesIO();Image.new('RGB',(20,10),'red').save(raw,format=fmt)
            f=save_upload(self.store,self.root,self.rid,'picture.'+fmt.lower(),'image/'+fmt.lower(),base64.b64encode(raw.getvalue()).decode())
            record=self.store.attachment(f['id'],self.rid)
            self.assertEqual(Path(record['path']).read_bytes(),raw.getvalue())
            with Image.open(record['model_path']) as preview:self.assertEqual(preview.format,'PNG')
            runner=Recorder();service=ChatService(self.store,runner,self.root);job=service.submit(self.rid,'@Codex 看这张图片',attachments=[f['id']]);service.wait(job['id'],5)
            self.assertEqual(runner.calls[-1][2]['images'][-1]['mime'],'image/png')
    def test_skill_admission_and_explicit_provider_scope(self):
        buf=io.BytesIO()
        with zipfile.ZipFile(buf,'w') as z:z.writestr('repo-main/demo/SKILL.md','---\nname: demo\ndescription: synthetic\n---\nReply with DEMO_SKILL.')
        library=SkillLibrary(self.root,external_roots=[]);library.admit_zip(buf.getvalue(),'demo')
        self.assertIn('DEMO_SKILL',library.resolve('#demo hello','codex'))
        self.assertEqual(library.resolve('hello','codex'),'')
        skill=library.scan()[0];library.toggle(skill['id'],False)
        with self.assertRaises(ValueError):library.resolve('#demo hello','codex')
    def test_explicit_chat_archive_is_bounded_and_not_a_skill(self):
        from chat_archive import resolve_chats
        self.store.message(self.rid,'user','SYNTHETIC_ARCHIVE_42')
        reference=f'$[test]({self.rid})'
        self.assertIn('SYNTHETIC_ARCHIVE_42',resolve_chats(self.store,reference))
        self.assertEqual(resolve_chats(self.store,'$test'),'')
        self.assertEqual(SkillLibrary(self.root,external_roots=[]).resolve(reference,'codex'),'')
    def test_zip_traversal_rejected(self):
        buf=io.BytesIO()
        with zipfile.ZipFile(buf,'w') as z:z.writestr('repo-main/../outside/SKILL.md','bad')
        with self.assertRaises(ValueError):SkillLibrary(self.root,external_roots=[]).admit_zip(buf.getvalue())
        self.assertFalse((self.root/'outside').exists())
    def test_cancelled_late_result_cannot_commit_or_continue(self):
        entered=threading.Event();release=threading.Event()
        class Late(Recorder):
            def run(self,*a,**kw):entered.set();release.wait(3);return {'text':'STALE','session_id':'old'}
        rid=self.store.create_room('group',['codex','deepseek'])['id'];service=ChatService(self.store,Late(),self.root)
        task=service.submit(rid,'Codex 分析、DeepSeek 汇总');self.assertTrue(entered.wait(2));service.cancel(task['id']);release.set();service.wait(task['id'],4)
        self.assertFalse(any(m['author'] in ['codex','deepseek'] for m in self.store.room(rid)['messages']))
        self.assertEqual(len(service.job(task['id'])['steps']),1)
    def test_queued_new_topic_waits_and_excludes_previous_context(self):
        entered=threading.Event();release=threading.Event()
        class Blocking(Recorder):
            def run(self,*a,**kw):
                if not self.calls:entered.set();release.wait(3)
                return super().run(*a,**kw)
        runner=Blocking();service=ChatService(self.store,runner,self.root)
        old=service.dispatch(self.rid,'旧材料 FIRST_TOPIC');self.assertTrue(entered.wait(2))
        new=service.dispatch(self.rid,'这是全新的 SECOND_TOPIC',topic='new')
        self.assertEqual(new['status'],'queued');release.set();service.wait(old['id'],4);service.wait(new['id'],4)
        self.assertEqual(len(runner.calls),2);self.assertNotIn('FIRST_TOPIC',runner.calls[-1][1])
        self.assertIn('SECOND_TOPIC',runner.calls[-1][1])

class PresentationCompatibility(unittest.TestCase):
    def test_pptx_text_retains_slide_numbers(self):
        from uploads import extract_text
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'slides.pptx'
            with zipfile.ZipFile(path,'w') as z:
                z.writestr('ppt/slides/slide2.xml','<a:p xmlns:a="urn:test"><a:t>SECOND_SLIDE</a:t></a:p>')
                z.writestr('ppt/slides/slide1.xml','<a:p xmlns:a="urn:test"><a:t>FIRST_SLIDE</a:t></a:p>')
            text,note=extract_text(path)
            self.assertLess(text.index('FIRST_SLIDE'),text.index('SECOND_SLIDE'));self.assertIn('[第 2 页]',text)
