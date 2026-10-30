import unittest
import test_upgrade as upgrade
from context_search import retrieve
from friendly import explain_error

class SuperTeamTests(unittest.TestCase):
    setUp=upgrade.UpgradeTests.setUp
    tearDown=upgrade.UpgradeTests.tearDown
    def test_feedback_is_room_bound_and_reaches_next_answer(self):
        mid=self.store.message(self.rid,'codex','先进行小样本验证')
        self.store.react(self.rid,mid,'accepted')
        j=self.service.submit(self.rid,'@DeepSeek 继续');self.service.wait(j['id'],5)
        self.assertIn('用户采纳',self.runner.calls[-1][1])
        self.assertIn('先进行小样本验证',self.runner.calls[-1][1])
        other=self.store.create_room('other',['codex'])['id']
        with self.assertRaises(ValueError):self.store.react(other,mid,'supported')
    def test_two_handoff_cycles_are_bounded(self):
        self.store.update_settings(self.rid,{'conversation':'handoff'})
        j=self.service.submit(self.rid,'分析并实现',rounds=2)
        self.service.wait(j['id'],5)
        self.assertEqual(len(self.runner.calls),4)
        self.assertIn('第 2 / 2 轮',self.runner.calls[-1][1])
    def test_hidden_rooms_preserve_history_and_restore(self):
        self.store.message(self.rid,'user','保留资料')
        self.store.set_visibility(self.rid,'hidden')
        self.assertEqual(self.store.room(self.rid)['messages'][0]['text'],'保留资料')
        self.store.set_visibility(self.rid,'visible')
        self.assertEqual(self.store.room(self.rid)['visibility'],'visible')
    def test_single_mention_normalizes_three_cycles_to_one(self):
        self.store.update_settings(self.rid,{'cycles':3})
        j=self.service.submit(self.rid,'@Codex 直接回答');self.service.wait(j['id'],5)
        self.assertEqual(len(self.runner.calls),1)
        self.assertEqual(self.service.job(j['id'])['rounds'],1)
        self.assertIn('第 1 / 1 轮',self.runner.calls[0][1])
    def test_task_outputs_are_bound_to_message_ids(self):
        j=self.service.submit(self.rid,'@全体成员 给建议');self.service.wait(j['id'],5)
        task=self.service.job(j['id']);messages=self.store.room(self.rid)['messages']
        ids={m['id'] for m in messages if m['author']!='user'}
        self.assertEqual({s['message_id'] for s in task['steps']},ids)
    def test_parallel_setting_reports_actual_trigger(self):
        self.store.update_settings(self.rid,{'conversation':'parallel'})
        j=self.service.submit(self.rid,'分析');self.service.wait(j['id'],5)
        self.assertNotIn('@全体',self.service.job(j['id'])['reason'])
    def test_search_does_not_return_unrelated_adopted_answer(self):
        self.assertEqual(retrieve([{'id':1,'author':'codex','text':'先检查数据','reaction':'accepted'}],'NONEXISTENT981'),[])
    def test_friendly_errors_do_not_mislabel_network_as_quota(self):
        self.assertIn('不在线',explain_error('ConnectionError'))
        self.assertNotIn('额度',explain_error('ConnectionError'))
        self.assertIn('休息',explain_error('insufficient_quota'))

if __name__=='__main__':unittest.main()
