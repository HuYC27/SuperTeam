from pathlib import Path
import subprocess
import sys
import unittest
from adapters import stop_process,parse_event

class RuntimeTests(unittest.TestCase):
    def test_workbuddy_result_is_verified_and_reasoning_not_exposed(self):
        self.assertEqual(parse_event('workbuddy',{'type':'result','subtype':'success','result':'22','session_id':'s'}),('text','22'))
        self.assertIsNone(parse_event('workbuddy',{'type':'assistant','message':{'content':[{'type':'thinking','thinking':'private'}]}}))
    def test_launcher_compiles_including_pyw_extension(self):
        path=Path(__file__).resolve().parents[1]/'launch.pyw'
        compile(path.read_text(encoding='utf-8'),str(path),'exec')
    def test_stop_terminates_actual_child_process(self):
        process=subprocess.Popen([sys.executable,'-c','import time; time.sleep(60)'],creationflags=subprocess.CREATE_NO_WINDOW)
        try:
            stop_process(process)
            process.wait(timeout=5)
            self.assertIsNotNone(process.returncode)
        finally:
            if process.poll() is None: process.kill();process.wait(timeout=5)

if __name__=='__main__': unittest.main()
