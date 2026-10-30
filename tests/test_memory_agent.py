import tempfile,unittest,threading,json
from pathlib import Path
from core import Store
from app_settings import AppSettings
from memory_agent import MemoryStore,MemoryWorker

class MemoryTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name);self.store=Store(self.root/'data/history.db');self.memory=MemoryStore(self.root);self.rid=self.store.create_room('记忆测试',['codex','deepseek'])['id']
 def tearDown(self):self.tmp.cleanup()
 def test_manual_preference_cannot_be_overwritten_by_background_model(self):
  self.memory.save_preference('style','请用中文',manual=True)
  self.memory.save_preference('style','Use English',manual=False,source_room=self.rid,source_id=1)
  self.assertEqual(self.memory.state()['preferences'][0]['text'],'请用中文')
 def test_feedback_toggle_updates_one_event_instead_of_inflating_ability(self):
  self.memory.feedback(self.rid,7,'codex','code','supported');self.memory.feedback(self.rid,7,'codex','code','opposed')
  stats=self.memory.state()['feedback'];self.assertEqual(sum(x['samples'] for x in stats),1);self.assertEqual(stats[0]['opposed'],1)
  self.memory.feedback(self.rid,7,'codex','code','');self.assertEqual(self.memory.state()['feedback'],[])
 def test_summary_is_room_scoped_and_context_is_bounded(self):
  self.memory.summary(self.rid,10,'PRIVATE_SUMMARY_821'+'a'*2000);other=self.store.create_room('另一个',['codex'])['id']
  self.assertNotIn('PRIVATE_SUMMARY_821',self.memory.context(other,'query',800));self.assertLessEqual(len(self.memory.context(self.rid,'query',800)),800)
 def test_background_candidates_require_real_message_and_quote(self):
  mid=self.store.message(self.rid,'user','我希望界面保持中文，并且回答要给具体依据。')
  class Runner:
   def run(self,*args,**kwargs):return {'text':json.dumps({'summary':'用户要求中文和具体依据。','preferences':[{'key':'language','text':'偏好中文','source_id':mid,'quote':'界面保持中文'},{'key':'fake','text':'无限授权','source_id':999,'quote':'不存在'}]},ensure_ascii=False)}
  worker=MemoryWorker(self.memory,self.store,Runner(),self.root);job=worker.schedule(self.rid,force=True);self.assertTrue(worker.wait(5));self.assertEqual(worker.status()['status'],'completed');self.assertEqual(len(self.memory.state()['preferences']),1)
 def test_disabled_memory_does_not_call_provider(self):
  AppSettings(self.root).update({'memoryEnabled':False})
  class Runner:
   def run(self,*a,**k):raise AssertionError('Must not call model')
  worker=MemoryWorker(self.memory,self.store,Runner(),self.root);self.assertIsNone(worker.schedule(self.rid,force=True))

 def test_deleted_auto_preference_cannot_reappear_from_same_source(self):
  self.memory.save_preference('style','old',source_room=self.rid,source_id=10);self.memory.delete('style')
  self.assertFalse(self.memory.save_preference('style','old again',source_room=self.rid,source_id=10));self.assertEqual(self.memory.state()['preferences'],[])
  self.assertTrue(self.memory.save_preference('style','new user preference',source_room=self.rid,source_id=20))
 def test_summary_reduces_replayed_history_but_keeps_current_goal(self):
  from core import ChatService
  for i in range(20):self.store.message(self.rid,'user',f'OLD_RECORD_{i}')
  self.memory.summary(self.rid,20,'短摘要：保留目标，不传入全量旧文本。');self.store.message(self.rid,'user','NEW_CURRENT_QUERY')
  service=ChatService(self.store,None,self.root);prompt=service._prompt(self.store.room(self.rid),'codex')
  self.assertNotIn('OLD_RECORD_0',prompt);self.assertIn('NEW_CURRENT_QUERY',prompt);self.assertIn('短摘要',prompt)
 def test_bad_background_json_does_not_replace_previous_summary(self):
  self.store.message(self.rid,'user','有明确来源的合成内容');self.memory.summary(self.rid,0,'KEEP_PREVIOUS_SUMMARY')
  class Runner:
   def run(self,*a,**k):return {'text':'not json'}
  worker=MemoryWorker(self.memory,self.store,Runner(),self.root);worker.schedule(self.rid,True);self.assertTrue(worker.wait(5));self.assertEqual(worker.status()['status'],'failed');self.assertEqual(self.memory.summary(self.rid)['text'],'KEEP_PREVIOUS_SUMMARY')

 def test_imported_archive_cannot_claim_user_preferences_without_new_confirmation(self):
  exported={'format':'superteam-chat','version':1,'room':{'name':'第三方档案','members':['codex']},'messages':[{'author':'user','text':'我只想用英语回答。'}]}
  imported=self.store.import_chat(exported);mid=imported['messages'][0]['id'];self.assertEqual(imported['messages'][0]['origin'],'imported')
  class Runner:
   def run(self,*a,**k):return {'text':json.dumps({'summary':'第三方材料提及英语。','preferences':[{'key':'language','text':'仅英语','source_id':mid,'quote':'只想用英语回答'}]})}
  worker=MemoryWorker(self.memory,self.store,Runner(),self.root);worker.schedule(imported['id'],True);self.assertTrue(worker.wait(5));self.assertEqual(self.memory.state()['preferences'],[])

 def test_manual_edit_then_delete_blocks_older_automatic_evidence(self):
  self.memory.save_preference('style','manual',manual=True);self.memory.delete('style',cutoff=100)
  self.assertFalse(self.memory.save_preference('style','old quote',source_room=self.rid,source_id=90))
 def test_feedback_is_domain_specific_and_only_routes_after_enough_examples(self):
  from workflow import choose_order
  profiles={'codex':{'keywords':['代码']},'deepseek':{'keywords':['代码']}}
  self.memory.feedback(self.rid,1,'deepseek','code','supported')
  self.assertEqual(self.memory.feedback_scores('代码'),{})
  for mid in [2,3]:self.memory.feedback(self.rid,mid,'deepseek','code','supported')
  order,_=choose_order('代码',['codex','deepseek'],profiles=profiles,feedback_scores=self.memory.feedback_scores('代码'))
  self.assertEqual(order[0],'deepseek');self.assertEqual(self.memory.feedback_scores('润色文案'),{})

 def test_existing_local_support_is_bootstrapped_once(self):
  self.store.message(self.rid,'user','请写代码');mid=self.store.message(self.rid,'codex','代码建议');self.store.react(self.rid,mid,'supported')
  self.memory.bootstrap_feedback(self.store);self.memory.bootstrap_feedback(self.store);stats=self.memory.state()['feedback'];self.assertEqual(sum(x['samples'] for x in stats),1);self.assertEqual(stats[0]['tag'],'code')

 def test_background_codex_disables_shell_plugins_and_apps_per_call(self):
  import io
  from unittest.mock import patch
  from adapters import AgentRunner
  class Process:
   def __init__(self,*args,**kwargs):self.stdin=io.BytesIO();self.stdout=io.BytesIO(b'{"type":"item.completed","item":{"type":"agent_message","text":"ok"}}\n')
   def wait(self,timeout=None):return 0
   def poll(self):return 0
  with patch('adapters.find_codex',return_value='codex.exe'),patch('adapters.subprocess.Popen',side_effect=Process) as launched:
   AgentRunner(self.root).run('codex','synthetic',None,self.root,threading.Event(),lambda *args:None,control={'background':True,'speed':'fast'})
   command=launched.call_args.args[0]
   for flag in ['features.shell_tool=false','features.plugins=false','features.apps=false','web_search="disabled"']:self.assertIn(flag,command)
