import tempfile,unittest
from pathlib import Path
from connections import Connections
class ConnectionsTests(unittest.TestCase):
 def test_portable_path_and_unknown_connector(self):
  class Runner:
   def status(self):return {}
  with tempfile.TemporaryDirectory() as folder:
   root=Path(folder);exe=root/'DeepSeek Harness.exe';exe.touch();runner=Runner();manager=Connections(root,runner)
   manager.configure('deepseek',str(exe));self.assertEqual(runner.deepseek,exe)
   restored=Connections(root,Runner());self.assertEqual(restored.paths['deepseek'],str(exe))
   with self.assertRaises(ValueError):manager.configure('doubao',str(exe))
   with self.assertRaises(ValueError):manager.configure('deepseek','relative.exe')
   manager.enabled=False
   with self.assertRaises(ValueError):manager.test('codex')
