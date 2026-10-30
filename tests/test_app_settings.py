import json
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch

from core import Store, ChatService


class AppSettingsTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
    def tearDown(self):
        self.tmp.cleanup()
    def prefs(self):
        from app_settings import AppSettings
        return AppSettings(self.root)
    def test_defaults_and_legacy_keys_roundtrip(self):
        path=self.root/'data/preferences.json';path.parent.mkdir();path.write_text(json.dumps({'theme':'dark','font':18,'custom':'原文'}),encoding='utf-8')
        prefs=self.prefs();value=prefs.read()
        self.assertEqual(value['language'],'zh-CN');self.assertEqual(value['custom'],'原文')
        self.assertTrue(value['pluginsEnabled'])
        prefs.update({'language':'en','showContextUsage':True})
        self.assertEqual(prefs.read()['theme'],'dark');self.assertEqual(prefs.read()['custom'],'原文')
    def test_strict_validation_and_atomic_failure(self):
        prefs=self.prefs();prefs.update({'language':'en'})
        for body in ({'language':'fr'},{'font':True},{'archiveDays':14},{'pluginsEnabled':'false'},{'terminalShell':'bash'},{'agentEnvironment':'wsl'},{'popoutHotkey':'Alt+F4'},{'chatFolder':'../escape'},{'chatFolder':'https://example.com'},{'confirmClose':'maybe'}):
            with self.subTest(body=body):
                with self.assertRaises(ValueError):prefs.update(body)
                self.assertEqual(prefs.read()['language'],'en')
    def test_launch_at_login_is_only_written_on_explicit_change(self):
        prefs=self.prefs()
        with patch('app_settings.set_launch_at_login') as toggle:
            prefs.read();prefs.update({'theme':'dark'});toggle.assert_not_called()
            prefs.update({'launchAtLogin':True});toggle.assert_called_once_with(True,self.root)
            prefs.update({'launchAtLogin':True});self.assertEqual(toggle.call_count,1)
    def test_new_room_defaults_do_not_mutate_existing_permission_or_workdir(self):
        prefs=self.prefs();store=Store(self.root/'data/history.db');old=store.create_room('原有会话',['codex'],{'permission':'read-only'})
        folder=self.root/'中文 工作';prefs.update({'defaultPermission':'danger-full-access','chatFolder':str(folder)})
        new=store.create_room('新会话',['codex'],preferences=prefs.read())
        self.assertEqual(new['settings']['permission'],'danger-full-access');self.assertEqual(new['settings']['computer'],'off')
        self.assertEqual(Path(new['work_folder']),folder/new['id'])
        self.assertEqual(store.room(old['id'])['settings']['permission'],'read-only');self.assertEqual(store.room(old['id'])['work_folder'],'')
    def test_autoarchive_protects_active_hidden_deleted_and_recent_rooms(self):
        store=Store(self.root/'data/history.db');rooms=[store.create_room(str(i),['codex']) for i in range(6)]
        with store.connect() as db:db.execute('UPDATE rooms SET created=?',(time.time()-40*86400,))
        store.set_visibility(rooms[2]['id'],'hidden');store.set_visibility(rooms[3]['id'],'deleted');store.message(rooms[4]['id'],'user','最近消息')
        archived=store.autoarchive(30,protected=[rooms[0]['id'],rooms[1]['id']])
        self.assertEqual(archived,[rooms[5]['id']]);self.assertEqual(store.room(rooms[0]['id'])['visibility'],'visible')
    def test_source_safe_export_import_preserves_content_without_authority(self):
        store=Store(self.root/'data/history.db');room=store.create_room('中文私聊',['codex'],{'permission':'danger-full-access','computer':'critical'})
        store.message(room['id'],'user','原文 $skill #会话，不翻译')
        exported=store.export_chat(room['id']);exported['room']['settings']={'permission':'danger-full-access','computer':'critical'}
        imported=store.import_chat(exported,preferences=self.prefs().read())
        self.assertEqual(imported['messages'][0]['text'],'原文 $skill #会话，不翻译')
        self.assertEqual(imported['settings']['permission'],'workspace-write');self.assertEqual(imported['settings']['computer'],'off')
        self.assertNotEqual(imported['id'],room['id'])
        exported['messages'][0]['author']='attacker'
        count=len(store.list_rooms())
        with self.assertRaises(ValueError):store.import_chat(exported)
        self.assertEqual(len(store.list_rooms()),count)
    def test_plugins_off_prevents_skill_resolution_and_speed_reaches_prompt(self):
        prefs=self.prefs();prefs.update({'pluginsEnabled':False,'speed':'thorough'})
        store=Store(self.root/'data/history.db');room=store.create_room('测试',['codex']);store.message(room['id'],'user','$test 请完成任务')
        service=ChatService(store,None,self.root)
        prompt=service._prompt(store.room(room['id']),'codex')
        self.assertIn('thorough',prompt);self.assertIn('禁用',prompt)


import io
import threading
import urllib.request
import urllib.error
import server
from adapters import AgentRunner


class SettingsHttpTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
        with patch.object(server,'ROOT',self.root):self.httpd,self.token,self.service=server.make_server(discover_models=False)
        self.thread=threading.Thread(target=self.httpd.serve_forever,daemon=True);self.thread.start()
        self.base='http://127.0.0.1:'+str(self.httpd.server_port)
    def tearDown(self):
        self.httpd.shutdown();self.httpd.server_close();self.thread.join();self.tmp.cleanup()
    def request(self,path,data=None):
        req=urllib.request.Request(self.base+path,headers={'X-App-Token':self.token,'Content-Type':'application/json'},data=None if data is None else json.dumps(data).encode('utf-8'))
        with urllib.request.urlopen(req) as response:return json.load(response)
    def test_terminal_workspace_is_created_without_opening_an_application(self):
        room=self.request('/api/rooms',{'name':'空聊天','members':['codex']})
        self.assertFalse(Path(room['work_folder']).exists())
        with patch('native_services.subprocess.Popen') as launch:
            data=self.request('/api/workspace-path',{'room':room['id']})
            self.assertTrue(Path(data['path']).is_dir());launch.assert_not_called()
    def test_settings_static_assets_are_served_with_correct_types(self):
        folder=self.root/'ui';folder.mkdir()
        for name,mime in [('settings-page.js','text/javascript'),('settings-page.css','text/css'),('i18n.js','text/javascript'),('workspace-layout.js','text/javascript'),('workspace-layout.css','text/css'),('file-library.js','text/javascript'),('file-library.css','text/css')]:
            (folder/name).write_text('/* test */',encoding='utf-8')
            with urllib.request.urlopen(self.base+'/'+name) as response:
                self.assertEqual(response.read(),b'/* test */');self.assertTrue(response.headers['Content-Type'].startswith(mime))
    def test_partial_preferences_info_and_new_room(self):
        value=self.request('/api/preferences',{'language':'en','defaultPermission':'read-only','chatFolder':str(self.root/'new chats')})
        self.assertEqual(value['theme'],'light')
        room=self.request('/api/rooms',{'name':'中文名','members':['codex']})
        self.assertEqual(room['settings']['permission'],'read-only')
        self.assertEqual(Path(room['work_folder']).parent,self.root/'new chats')
        info=self.request('/api/settings-info');self.assertFalse(info['capabilities']['agentEnvironment']['wsl'])
        with self.assertRaises(urllib.error.HTTPError) as error:self.request('/api/preferences',{'pluginsEnabled':'no'})
        self.assertEqual(error.exception.code,400)
    def test_json_roundtrip_and_archive_respects_open_room(self):
        room=self.request('/api/rooms',{'name':'我的原文','members':['codex']});self.service.store.message(room['id'],'user','中文消息 $不变')
        exported=self.request('/api/export-json?id='+room['id'])
        imported=self.request('/api/import-chat',{'data':exported['text']})
        self.assertEqual(imported['messages'][0]['text'],'中文消息 $不变')
        self.request('/api/preferences',{'archiveDays':7})
        with self.service.store.connect() as db:
            db.execute('UPDATE rooms SET created=?',(time.time()-40*86400,));db.execute('UPDATE messages SET created=?',(time.time()-40*86400,))
        state=self.request('/api/state?activeRoom='+room['id'])
        self.assertEqual(next(r for r in state['rooms'] if r['id']==room['id'])['visibility'],'visible')
        self.assertEqual(next(r for r in state['rooms'] if r['id']==imported['id'])['visibility'],'hidden')


class RunnerSettingsTests(unittest.TestCase):
    def test_codex_receives_effort_override(self):
        class Process:
            def __init__(self,*args,**kwargs):
                self.stdin=io.BytesIO();self.stdout=io.BytesIO(b'{"type":"item.completed","item":{"type":"agent_message","text":"ok"}}\n')
            def wait(self,timeout=None):return 0
            def poll(self):return 0
        with tempfile.TemporaryDirectory() as root:
            with patch('adapters.find_codex',return_value='codex.exe'),patch('adapters.subprocess.Popen',side_effect=Process) as run:
                answer=AgentRunner(root).run('codex','hello',None,root,threading.Event(),lambda *a:None,control={'speed':'thorough'})
                self.assertEqual(answer['text'],'ok');self.assertIn('model_reasoning_effort="high"',run.call_args.args[0])

class PrivateChatRuntimeTests(unittest.TestCase):
    def test_private_chat_has_one_reply_and_no_group_system_instructions(self):
        class Runner:
            def __init__(self):self.prompts=[]
            def run(self,provider,prompt,*args,**kwargs):self.prompts.append(prompt);return {'text':'答复','session_id':'private-session'}
        with tempfile.TemporaryDirectory() as root:
            store=Store(Path(root)/'data/history.db');room=store.create_room('中文私聊',['codex'],{'cycles':3});runner=Runner();service=ChatService(store,runner,root)
            job=service.submit(room['id'],'请深入分析这个研究任务');self.assertTrue(service.wait(job['id'],5));job=service.job(job['id'])
            self.assertEqual(job['status'],'completed');self.assertFalse(job['expert']);self.assertEqual(len(job['steps']),1)
            self.assertEqual(job['strategy'],'private');self.assertIn('私聊',job['reason'])
            for phrase in ('双方职责','房间协作规则','同组成员','发言顺序','独立回答','协作聊天室成员','本轮已有回答','本轮采用擅长者','当前第 1 /','协作交接'):
                self.assertNotIn(phrase,runner.prompts[0])
    def test_disabled_superteam_skills_are_not_resolved_in_real_dispatch(self):
        class Runner:
            def run(self,*args,**kwargs):return {'text':'done','session_id':None}
        with tempfile.TemporaryDirectory() as root:
            from app_settings import AppSettings
            AppSettings(root).update({'pluginsEnabled':False})
            store=Store(Path(root)/'data/history.db');room=store.create_room('test',['codex']);service=ChatService(store,Runner(),root)
            with patch('core.SkillLibrary.resolve',side_effect=AssertionError('must not resolve')) as resolve:
                job=service.submit(room['id'],'$test 请完成任务');self.assertTrue(service.wait(job['id'],5));resolve.assert_not_called()
                self.assertEqual(service.job(job['id'])['status'],'completed')

class SettingsBoundaryTests(unittest.TestCase):
    def test_import_limits_reject_bad_timestamps_without_creating_room(self):
        with tempfile.TemporaryDirectory() as root:
            store=Store(Path(root)/'data/history.db')
            base={'format':'superteam-chat','version':1,'room':{'name':'原文','members':['codex']},'messages':[{'author':'user','text':'保留','created':float('nan')}]}
            with self.assertRaises(ValueError):store.import_chat(base)
            self.assertEqual(len(store.list_rooms()),0)
            base['messages']=[{'author':'user','text':'保留'}]*10001
            with self.assertRaises(ValueError):store.import_chat(base)
            self.assertEqual(len(store.list_rooms()),0)
    def test_export_limit_prevents_unbounded_transfer(self):
        with tempfile.TemporaryDirectory() as root:
            store=Store(Path(root)/'data/history.db');room=store.create_room('test',['codex'])
            with store.connect() as db:db.executemany('INSERT INTO messages(room,author,text,created) VALUES(?,?,?,?)',[(room['id'],'user','x',time.time())]*10001)
            with self.assertRaises(ValueError):store.export_chat(room['id'])
    def test_persistence_failure_does_not_overwrite_preferences(self):
        from app_settings import AppSettings
        with tempfile.TemporaryDirectory() as root:
            prefs=AppSettings(root);prefs.update({'language':'en'})
            with patch('app_settings.set_launch_at_login',side_effect=OSError('registry denied')):
                with self.assertRaises(ValueError):prefs.update({'launchAtLogin':True,'language':'zh-CN'})
            self.assertEqual(prefs.read()['language'],'en');self.assertFalse(prefs.read()['launchAtLogin'])


class FollowupSteeringTests(unittest.TestCase):
    def test_neutral_defaults_apply_without_changing_existing_customization(self):
        from app_settings import AppSettings
        with tempfile.TemporaryDirectory() as root:
            prefs=AppSettings(root);value=prefs.read()
            self.assertEqual((value['theme'],value['accent'],value['sidebar']),('light','#000000',288))
            prefs.update({'theme':'dark','accent':'#123456','sidebar':320})
            self.assertEqual((prefs.read()['theme'],prefs.read()['accent'],prefs.read()['sidebar']),('dark','#123456',320))
    def test_steer_cancels_old_work_and_queue_but_retains_original_goal(self):
        self.check_policy('steer',preserve=True)
    def test_explicit_replace_starts_new_context(self):
        self.check_policy('replace',preserve=False)
    def check_policy(self,policy,preserve):
        from adapters import AgentError
        class Runner:
            def __init__(self):self.entered=threading.Event();self.prompts=[]
            def run(self,provider,prompt,session_id,cwd,cancel,on_event,**options):
                self.prompts.append(prompt)
                if len(self.prompts)==1:
                    self.entered.set();cancel.wait(5);raise AgentError('cancelled')
                return {'text':'已调整','session_id':'continued'}
        with tempfile.TemporaryDirectory() as root:
            store=Store(Path(root)/'data/history.db');room=store.create_room('私聊',['codex']);runner=Runner();service=ChatService(store,runner,root)
            original=service.submit(room['id'],'ORIGINAL_GOAL_591 完成这个研究任务')
            try:
                self.assertTrue(runner.entered.wait(2))
                obsolete=service.dispatch(room['id'],'OLD_QUEUED_592 已作废方向',policy='queue')
                followup=service.dispatch(room['id'],'FOLLOWUP_593 使用公开数据继续原目标',policy=policy)
                self.assertTrue(service.wait(followup['id'],5));self.assertTrue(service.wait(obsolete['id'],2))
                self.assertEqual(service.job(original['id'])['status'],'cancelled');self.assertEqual(service.job(obsolete['id'])['status'],'cancelled')
                self.assertEqual(service.job(followup['id'])['status'],'completed');self.assertEqual(len(runner.prompts),2)
                current=store.room(room['id'])
                self.assertEqual(current['context_start']==0,preserve)
                self.assertEqual('ORIGINAL_GOAL_591' in runner.prompts[-1],preserve)
                self.assertNotIn('OLD_QUEUED_592',runner.prompts[-1])
                self.assertIn('FOLLOWUP_593',runner.prompts[-1])
                self.assertTrue(any(m['text'].startswith('ORIGINAL_GOAL_591') for m in current['messages']))
            finally:
                pending=[j['id'] for j in service.active()]
                for jid in pending:service.cancel(jid)
                for jid in pending:service.wait(jid,3)


if __name__=='__main__':unittest.main()

class OpenRoomLeaseTests(unittest.TestCase):
    def test_concurrent_panes_protect_each_other_until_lease_expires(self):
        from app_settings import OpenRoomLeases
        clock=[0];leases=OpenRoomLeases(clock=lambda:clock[0]);a='a'*32;b='b'*32
        self.assertEqual(leases.touch([a]),[a]);clock[0]=2
        self.assertEqual(set(leases.touch([b])),{a,b});clock[0]=31
        self.assertEqual(leases.touch([]),[b]);clock[0]=33;self.assertEqual(leases.touch([]),[])
