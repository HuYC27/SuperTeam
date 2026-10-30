import tempfile
import threading
import unittest
from pathlib import Path
from adapters import parse_event, AgentError
from core import Store, ChatService


class AdapterTests(unittest.TestCase):
    def test_codex_reconnect_warning_is_not_terminal_failure(self):
        self.assertEqual(parse_event('codex', {'type':'error','message':'Reconnecting... 2/5 (request timed out)'}),('status','Reconnecting... 2/5 (request timed out)'))

    def test_codex_reply(self):
        self.assertEqual(parse_event('codex', {'type':'item.completed','item':{'type':'agent_message','text':'hello'}}), ('text','hello'))

    def test_deepseek_error_not_empty_success(self):
        with self.assertRaises(AgentError):
            parse_event('deepseek', {'type':'status','phase':'turn_end','reason':{'kind':'error','error':{'message':'missing login'}}})


class FakeRunner:
    def __init__(self): self.calls=[]
    def run(self, provider, prompt, session_id, cwd, cancel, on_event, **options):
        self.calls.append((provider,prompt,session_id))
        if cancel.is_set(): raise AgentError('已停止')
        return {'text':provider+' answer','session_id':session_id or provider+'-session'}


class RoomTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.store=Store(Path(self.tmp.name)/'history.db')
        self.runner=FakeRunner()
        self.service=ChatService(self.store,self.runner,Path(self.tmp.name))
    def tearDown(self): self.tmp.cleanup()
    def run_job(self,room,text='hello',target='all',rounds=1):
        job=self.service.submit(room,text,target,rounds)
        self.service.wait(job['id'],10)
        result=self.service.job(job['id'])
        self.assertEqual(result['status'],'completed',result)
        return result
    def test_private_isolation_and_continuity(self):
        a=self.store.create_room('A',['codex'])['id']
        b=self.store.create_room('B',['codex'])['id']
        self.run_job(a,'private-marker')
        self.run_job(a,'remember')
        self.run_job(b,'other')
        self.assertEqual(self.runner.calls[1][2],'codex-session')
        self.assertIsNone(self.runner.calls[2][2])
        self.assertNotIn('private-marker',self.runner.calls[2][1])
    def test_group_independent_then_review(self):
        room=self.store.create_room('group',['codex','deepseek'])['id']
        self.run_job(room,'各自提一个方案',rounds=2)
        self.assertEqual(len(self.runner.calls),4)
        self.assertNotIn('codex answer',self.runner.calls[1][1])
        reviewer=self.runner.calls[2]
        self.assertIn(('deepseek' if reviewer[0]=='codex' else 'codex')+' answer',reviewer[1])
    def test_invalid_target_does_not_write(self):
        room=self.store.create_room('private',['codex'])['id']
        with self.assertRaises(ValueError): self.service.submit(room,'x','deepseek',1)
        self.assertEqual(self.store.room(room)['messages'],[])
    def test_failed_member_preserves_other_reply(self):
        original=self.runner.run
        def fail(provider,*args,**options):
            if provider=='deepseek': raise AgentError('not signed in')
            return original(provider,*args,**options)
        self.runner.run=fail
        room=self.store.create_room('group',['codex','deepseek'])['id']
        job=self.service.submit(room,'test','all',1)
        self.service.wait(job['id'],10)
        self.assertEqual(self.service.job(job['id'])['status'],'failed')
        self.assertTrue(any(m['author']=='codex' for m in self.store.room(room)['messages']))

    def test_busy_room_rejects_and_stop_is_cancelled(self):
        entered=threading.Event()
        def blocking(provider,prompt,session_id,cwd,cancel,on_event,**options):
            entered.set()
            cancel.wait(5)
            raise AgentError('stopped')
        self.runner.run=blocking
        room=self.store.create_room('private',['codex'])['id']
        job=self.service.submit(room,'test','all',1)
        self.assertTrue(entered.wait(2))
        with self.assertRaises(ValueError): self.service.submit(room,'duplicate','all',1)
        self.service.cancel(job['id'])
        self.service.wait(job['id'],3)
        self.assertEqual(self.service.job(job['id'])['status'],'cancelled')
        self.assertEqual(len([m for m in self.store.room(room)['messages'] if m['author']=='user']),1)

if __name__=='__main__': unittest.main()

class DuplicateRoomNames(unittest.TestCase):
    def test_repeated_names_gain_next_available_number(self):
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            store=Store(Path(d)/'history.db')
            names=[store.create_room('讨论',['codex'])['name'] for _ in range(3)]
            self.assertEqual(names,['讨论','讨论（1）','讨论（2）'])
