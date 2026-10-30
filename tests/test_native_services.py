import io
import json
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import native_services
from desktop import WindowControls


class NativeServicesTests(unittest.TestCase):
    def test_invalid_shell_and_path_never_start_process(self):
        with tempfile.TemporaryDirectory() as folder:
            service = native_services.NativeServices(Path(folder))
            with patch('native_services.subprocess.Popen') as launch:
                self.assertFalse(service.open_terminal(folder, 'cmd & whoami', 'window')['ok'])
                self.assertFalse(service.open_terminal(str(Path(folder)/'missing'), 'cmd', 'window')['ok'])
                launch.assert_not_called()

    def test_window_terminal_uses_argument_list_and_cwd(self):
        with tempfile.TemporaryDirectory(prefix='native & ') as folder:
            service = native_services.NativeServices(Path(folder))
            with patch.object(service, '_shell', return_value='C:/Windows/System32/cmd.exe'), patch('native_services.subprocess.Popen') as launch:
                result = service.open_terminal(folder, 'cmd', 'window')
                self.assertTrue(result['ok'])
                args, kwargs = launch.call_args
                self.assertEqual(args[0], ['C:/Windows/System32/cmd.exe', '/K'])
                self.assertEqual(kwargs['cwd'], str(Path(folder).resolve()))
                self.assertFalse(kwargs.get('shell', False))

    def test_terminal_buffer_reports_cursor_and_lost_output(self):
        service = native_services.NativeServices(Path.cwd(), buffer_limit=8)
        service._append_output('abcdef')
        first = service.terminal_read(0)
        self.assertEqual(first['text'], 'abcdef')
        service._append_output('ghijkl')
        result = service.terminal_read(first['cursor'])
        self.assertEqual(result['text'], 'ghijkl')
        self.assertFalse(result['truncated'])
        stale = service.terminal_read(0)
        self.assertEqual(stale['text'], 'efghijkl')
        self.assertTrue(stale['truncated'])
        self.assertEqual(stale['cursor'], 12)

    def test_terminal_writes_stdin_and_stops_only_owned_process(self):
        service = native_services.NativeServices(Path.cwd())
        proc = Mock(stdin=io.StringIO())
        proc.poll.return_value = None
        service._terminal = proc
        self.assertTrue(service.terminal_write('echo hello\n')['ok'])
        self.assertEqual(proc.stdin.getvalue(), 'echo hello\n')
        self.assertTrue(service.terminal_stop()['ok'])
        proc.terminate.assert_called_once()
        self.assertIsNone(service._terminal)

    def test_file_path_is_not_executed_as_a_shell_command(self):
        with tempfile.TemporaryDirectory() as folder:
            file = Path(folder)/'name & calc.txt'
            file.write_text('synthetic')
            service = native_services.NativeServices(Path(folder))
            with patch.object(native_services.os, 'startfile', create=True) as start:
                self.assertTrue(service.open_file(str(file))['ok'])
                start.assert_called_once_with(str(file.resolve()))
            self.assertFalse(service.open_file(str(file), 'shell')['ok'])

    @unittest.skipUnless(native_services.os.name == 'nt', 'Windows shells only')
    def test_installed_shells_execute_synthetic_unicode_command_in_panel(self):
        # Hidden pipes only; no real chat, visible console, notification, or hotkey.
        with tempfile.TemporaryDirectory() as folder:
            service = native_services.NativeServices(Path(folder))
            for shell in service.capabilities()['shells']:
                with self.subTest(shell=shell):
                    try:
                        self.assertTrue(service.terminal_start(folder, shell)['ok'])
                        marker = 'native_\u4e2d\u6587_77'
                        self.assertTrue(service.terminal_write('echo '+marker+'\n')['ok'])
                        deadline = time.monotonic()+6
                        while time.monotonic() < deadline:
                            result = service.terminal_read(0)
                            if marker in result['text']:
                                break
                            time.sleep(.05)
                        self.assertIn(marker, result['text'])
                        self.assertTrue(result['running'])
                        self.assertFalse(service.terminal_start(folder, shell)['ok'])
                    finally:
                        service.terminal_stop()

    @unittest.skipUnless(native_services.os.name == 'nt', 'Windows ctypes structures only')
    def test_notification_uses_quiet_balloon_and_removes_owned_icon(self):
        import threading
        fake = Mock()
        fake.user32.RegisterClassW.return_value = 1
        fake.user32.CreateWindowExW.return_value = 2
        fake.user32.LoadIconW.return_value = 3
        fake.kernel32.GetModuleHandleW.return_value = 4
        flags = []
        def icon(action, pointer):
            if action == 0:
                flags.append(pointer._obj.dwInfoFlags)
            return 1
        fake.shell32.Shell_NotifyIconW.side_effect = icon
        ready, shutdown, result = threading.Event(), threading.Event(), {}
        shutdown.set()
        with patch('native_services.ctypes.windll', fake):
            native_services._balloon_notification('SuperTeam', 'Task complete', False,
                                                 lambda: None, ready, result, shutdown)
        self.assertTrue(ready.is_set())
        self.assertTrue(result['ok'], result)
        self.assertTrue(flags[0] & 0x10)
        self.assertEqual([call.args[0] for call in fake.shell32.Shell_NotifyIconW.call_args_list], [0, 2])
        fake.user32.DestroyWindow.assert_called_once()

    def test_failed_replacement_does_not_remove_working_hotkey(self):
        service = native_services.NativeServices(Path.cwd())
        previous = Mock(chord='Ctrl+Alt+A')
        service._hotkey = previous
        with patch('native_services._GlobalHotkey') as factory:
            factory.return_value.start.return_value = 'already in use'
            self.assertFalse(service.set_popout_hotkey('Ctrl+Alt+B')['ok'])
            previous.stop.assert_not_called()
            self.assertIs(service._hotkey, previous)

    def test_hotkey_owning_thread_unregisters_without_touching_desktop(self):
        import threading
        fake_user = Mock()
        fake_user.RegisterHotKey.return_value = 1
        fake_user.GetMessageW.return_value = 0
        fake_ctypes = Mock()
        fake_ctypes.windll.user32 = fake_user
        fake_ctypes.windll.kernel32.GetCurrentThreadId.return_value = 42
        # Only replace actual OS calls; wintypes/MSG allocations remain real.
        with patch('native_services.ctypes.windll', fake_ctypes.windll):
            hotkey = native_services._GlobalHotkey('Ctrl+Alt+Q', lambda: None)
            self.assertIsNone(hotkey.start())
            hotkey.thread.join(1)
            fake_user.UnregisterHotKey.assert_called_once_with(None, 1)

    def test_no_platform_support_is_explicit(self):
        service = native_services.NativeServices(Path.cwd())
        with patch('native_services.os.name', 'posix'):
            self.assertFalse(service.notify('SuperTeam', 'Task complete')['supported'])
            self.assertFalse(service.set_popout_hotkey('Ctrl+Alt+N')['supported'])

    def test_hotkey_validation_does_not_register_invalid_chord(self):
        service = native_services.NativeServices(Path.cwd())
        for invalid in ('Alt+F4', 'Ctrl+Alt+1', 'Ctrl+Alt+NN', 'Ctrl+Alt+N;shutdown'):
            self.assertFalse(service.set_popout_hotkey(invalid)['ok'])
        self.assertTrue(service.set_popout_hotkey('')['ok'])

    def test_close_confirmation_obeys_setting_and_reason(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder); (root/'data').mkdir()
            controls = WindowControls(root=root)
            controls._window = Mock()
            controls._window.create_confirmation_dialog.return_value = False
            (root/'data/preferences.json').write_text(json.dumps({'confirmClose':'shortcut'}))
            self.assertFalse(controls.close('shortcut')['ok'])
            controls._window.destroy.assert_not_called()
            self.assertTrue(controls.close()['ok'])
            controls._window.destroy.assert_called_once()

    def test_popout_uses_existing_service_and_own_controls(self):
        controls = WindowControls(root=Path.cwd(), base_url='http://127.0.0.1:1234/#testtoken')
        class Event:
            def __iadd__(self, callback):
                return self
        window=Mock()
        window.events.closing=Event()
        window.events.closed=Event()
        with patch.dict('sys.modules', {'webview': Mock(create_window=Mock(return_value=window))}) as modules:
            result=controls.popout(True)
            self.assertTrue(result['ok'])
            kwargs=modules['webview'].create_window.call_args.kwargs
            self.assertIn('?popout=1&standalone=1#testtoken', kwargs['url'])
            self.assertIsNot(kwargs['js_api'], controls)
            self.assertIs(kwargs['js_api']._window, window)


if __name__ == '__main__':
    unittest.main()

class WindowSizingTests(unittest.TestCase):
    def test_maximize_restore_is_independent_of_fullscreen(self):
        controls=WindowControls();controls._window=Mock()
        controls.toggle_maximize();controls._window.maximize.assert_called_once();controls._window.toggle_fullscreen.assert_not_called()
        controls.toggle_maximize();controls._window.restore.assert_called_once()
        controls.toggle_fullscreen();self.assertTrue(controls._fullscreen);controls._window.toggle_fullscreen.assert_called_once()
        controls.toggle_fullscreen();self.assertFalse(controls._fullscreen)
