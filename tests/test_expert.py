import tempfile,unittest
from pathlib import Path
from core import Store,ChatService

class ExpertTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name);self.store=Store(self.root/'history.db');self.calls=[];self.reply='UNIQUE_RESULT_918'
  owner=self
  class Runner:
   def run(self,provider,prompt,*args,**kwargs):
    owner.calls.append((provider,prompt));return {'text':owner.reply if len(owner.calls)==1 else '补充结论。'}
  self.service=ChatService(self.store,Runner(),self.root)
  self.rid=self.store.create_room('expert',['codex','deepseek','workbuddy'])['id']
 def tearDown(self):self.tmp.cleanup()
 def send(self,text):
  j=self.service.submit(self.rid,text);self.assertTrue(self.service.wait(j['id'],5));return self.service.job(j['id'])
 def test_complete_answer_still_has_two_group_participants(self):
  self.send('请实现 Python 脚本');self.assertEqual([p for p,_ in self.calls],['codex','deepseek'])
 def test_leader_selects_only_needed_peer_and_metadata_is_hidden(self):
  self.reply='脚本已经实现。\n<superteam-route>{"next":[{"member":"deepseek","task":"复核统计假设"}]}</superteam-route>'
  job=self.send('请实现 Python 脚本')
  self.assertEqual([p for p,_ in self.calls],['codex','deepseek']);self.assertIn('复核统计假设',self.calls[1][1]);self.assertIn('脚本已经实现',self.calls[1][1])
  self.assertNotIn('superteam-route',''.join(m['text'] for m in self.store.room(self.rid)['messages']))
  self.assertEqual(job['status'],'completed')
 def test_invalid_or_self_route_keeps_the_selected_second_member(self):
  self.reply='完成。<superteam-route>{"next":[{"member":"other","task":"x"},{"member":"codex","task":"x"}]}</superteam-route>'
  self.send('请实现 Python 脚本');self.assertEqual(len(self.calls),2)
 def test_greeting_has_two_members_without_task_handoff(self):
  self.reply='你好<superteam-route>{"next":[{"member":"deepseek","task":"打招呼"}]}</superteam-route>'
  self.send('你好');self.assertEqual(len(self.calls),2)
 def test_explicit_assignments_still_run_requested_members(self):
  self.send('Codex 实现脚本，DeepSeek 汇总结果');self.assertEqual([p for p,_ in self.calls],['codex','deepseek'])
 def test_all_remains_independent(self):
  self.send('@全体成员 各提两条建议');self.assertEqual(set(p for p,_ in self.calls),{'codex','deepseek','workbuddy'})
  self.assertTrue(all('UNIQUE_RESULT_918' not in prompt for _,prompt in self.calls))

 def test_economy_mode_invites_at_most_one_peer(self):
  self.reply='已实现主体。<superteam-route>{"next":[{"member":"deepseek","task":"必要复核"},{"member":"workbuddy","task":"可选润色"}]}</superteam-route>'
  self.send('请实现 Python 脚本');self.assertEqual([p for p,_ in self.calls],['codex','deepseek'])

 def test_explicit_specialist_uses_one_member_but_all_mention_overrides(self):
  self.store.update_settings(self.rid,{'conversation':'specialist','cycles':3})
  job=self.send('请实现 Python 脚本');self.assertEqual(len(self.calls),1);self.assertEqual(job['rounds'],1)
  self.calls.clear();j=self.service.submit(self.rid,'@全体成员 检查方案',rounds=2);self.assertTrue(self.service.wait(j['id'],5));self.assertEqual(len(self.calls),6)

 def test_review_is_two_members_and_second_gets_real_answer_and_checklist(self):
  self.store.update_settings(self.rid,{'conversation':'review','cycles':3})
  job=self.send('请实现 Python 脚本');self.assertEqual(len(self.calls),2);self.assertEqual(job['rounds'],1)
  self.assertIn('UNIQUE_RESULT_918',self.calls[1][1]);self.assertIn('交叉核对',self.calls[1][1]);self.assertIn('未经核验',self.calls[1][1])
  self.assertFalse(job['expert'])

 def test_discussion_runs_selected_rounds_and_later_calls_see_prior_answers(self):
  self.store.update_settings(self.rid,{'conversation':'discussion','cycles':2})
  job=self.send('请实现 Python 脚本');self.assertEqual(len(self.calls),6);self.assertEqual(job['rounds'],2)
  self.assertIn('UNIQUE_RESULT_918',self.calls[1][1]);self.assertIn('多轮讨论',self.calls[-1][1])

 def test_review_greeting_is_not_a_verification_task(self):
  self.store.update_settings(self.rid,{'conversation':'review'})
  self.send('你好');self.assertEqual(len(self.calls),2)
  self.assertTrue(all('交叉核对：检查' not in prompt for _,prompt in self.calls))

 def test_explicit_discussion_round_limit_is_not_increased(self):
  self.store.update_settings(self.rid,{'conversation':'discussion','cycles':3})
  job=self.service.submit(self.rid,'请实现 Python 脚本',rounds=1);self.assertTrue(self.service.wait(job['id'],5));self.assertEqual(len(self.calls),3)
