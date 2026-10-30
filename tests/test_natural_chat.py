import unittest
import test_upgrade as upgrade

class NaturalChatTests(unittest.TestCase):
    setUp=upgrade.UpgradeTests.setUp
    tearDown=upgrade.UpgradeTests.tearDown
    def test_greeting_has_no_handoff_or_old_topic(self):
        self.store.message(self.rid,'user','旧话题：请分析 APP 设计')
        j=self.service.submit(self.rid,'你们好啊');self.service.wait(j['id'],5)
        self.assertEqual(len(self.runner.calls),2)
        self.assertNotIn('旧话题：请分析 APP 设计',self.runner.calls[0][1])
        self.assertNotIn('交接给成员名',self.runner.calls[0][1])
        self.assertEqual(self.service.job(j['id'])['kind'],'greeting')
        self.assertIn('codex actual result',self.runner.calls[1][1])
        self.assertEqual(self.service.job(j['id'])['handoffs'],[])
    def test_independent_solicitation_has_independent_results(self):
        j=self.service.submit(self.rid,'各提两条建议');self.service.wait(j['id'],5)
        self.assertEqual(len(self.runner.calls),2)
        for c in self.runner.calls:self.assertNotIn('actual result',c[1])
        self.assertEqual(self.service.job(j['id'])['strategy'],'parallel')
    def test_explicit_handoff_binds_message_and_current_results(self):
        j=self.service.submit(self.rid,'Codex 分析、DeepSeek 汇总');self.service.wait(j['id'],5)
        self.assertEqual([c[0] for c in self.runner.calls],['codex','deepseek'])
        self.assertIn('本轮已有回答',self.runner.calls[1][1])
        self.assertIn('codex actual result',self.runner.calls[1][1])
        task=self.service.job(j['id'])
        self.assertTrue(task['origin_message_id']);self.assertTrue(task['handoffs'])
        answers=[m for m in self.store.room(self.rid)['messages'] if m['author']!='user']
        self.assertTrue(all(m['execution_id']==j['id'] for m in answers))
