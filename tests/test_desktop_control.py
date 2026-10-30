import unittest,threading,time
from desktop_control import DesktopBroker
class DesktopControlTests(unittest.TestCase):
 def broker(self):
  self.enabled=True;self.calls=[]
  return DesktopBroker(lambda room:self.enabled,lambda tool,args:self.calls.append((tool,args)) or {'ok':True},timeout=.5)
 def test_disabled_cannot_observe_or_click(self):
  b=self.broker();self.enabled=False
  with self.assertRaises(ValueError):b.request('r','codex','windows',{})
  self.assertEqual(self.calls,[])
 def test_enter_waits_for_approval_and_approval_is_room_bound(self):
  b=self.broker();result=[]
  t=threading.Thread(target=lambda:result.append(b.request('r','codex','key',{'key':'ENTER'})));t.start()
  for _ in range(100):
   if b.pending():break
   time.sleep(.002)
  self.assertEqual(self.calls,[]);item=b.pending()[0]
  with self.assertRaises(ValueError):b.decide('other',item['id'],True)
  b.decide('r',item['id'],True);t.join();self.assertTrue(result[0]['ok'])
 def test_disable_while_waiting_prevents_late_action(self):
  b=self.broker();errors=[]
  def run():
   try:b.request('r','codex','key',{'key':'DELETE'})
   except ValueError as e:errors.append(str(e))
  t=threading.Thread(target=run);t.start()
  for _ in range(100):
   if b.pending():break
   time.sleep(.002)
  self.enabled=False;b.decide('r',b.pending()[0]['id'],True);t.join();self.assertEqual(self.calls,[]);self.assertTrue(errors)
