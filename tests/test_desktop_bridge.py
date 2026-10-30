import tempfile,unittest
from pathlib import Path
from adapters import AgentRunner,AgentError

class DesktopBridgeTests(unittest.TestCase):
 def test_unverified_relay_text_is_not_attributed_to_original_model(self):
  with tempfile.TemporaryDirectory() as folder:
   runner=AgentRunner(Path(folder));events=[]
   def relay(*args,**kwargs):
    args[5]('text','UNVERIFIED_RELAY_REPLY');args[5]('status','调用外部工具');return {'text':'尚未发送，无法读取原软件回答。'}
   runner.run=relay
   with self.assertRaises(AgentError):runner._desktop_chat('qwen','synthetic',folder,None,lambda kind,value:events.append((kind,value)),{'mode':'critical','room':'test','provider':'qwen'})
   self.assertFalse(any(kind in ['text','delta'] for kind,value in events));self.assertTrue(events)
