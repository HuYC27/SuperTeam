import unittest
from desktop import WindowControls
class NativeBridgeTests(unittest.TestCase):
 def test_bridge_exposes_only_commands_not_native_window_graph(self):
  controls=WindowControls()
  public=[name for name in dir(controls) if not name.startswith('_') and not callable(getattr(controls,name))]
  self.assertEqual(public,[], 'Native window must never be traversed by pywebview JS bridge')
