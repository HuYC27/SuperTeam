"""Explicit, bounded skill indexing and ZIP admission; never executes skill code."""
from pathlib import Path,PurePosixPath
import hashlib,json,re,io,zipfile,urllib.request,urllib.parse,uuid,shutil

class SkillLibrary:
    def __init__(self,root,external_roots=None):
        self.root=Path(root);self.folder=self.root/'skills';self.folder.mkdir(parents=True,exist_ok=True)
        home=Path.home()
        self.sources=external_roots if external_roots is not None else [('Codex',home/'.codex/skills',['codex']),('DeepSeek',home/'.dsh/skills',['deepseek']),('Claude',home/'.claude/skills',['claude']),('WorkBuddy',home/'.workbuddy/skills',['workbuddy']),('WorkBuddy AI',home/'.workbuddy-ai/skills',['workbuddy'])]
        self.settings=self.root/'data/skills.json';self.settings.parent.mkdir(exist_ok=True)
    def config(self):
        try:return json.loads(self.settings.read_text(encoding='utf-8'))
        except (OSError,ValueError):return {}
    def scan(self):
        disabled=self.config().get('disabled',[]);items=[]
        for source,base,providers in [('SuperTeam',self.folder,['codex','deepseek','workbuddy']),*self.sources]:
            base=Path(base)
            if not base.exists():continue
            for path in base.rglob('SKILL.md'):
                if len(items)>=600:break
                if len(path.relative_to(base).parts)>6 or path.is_symlink() or not path.resolve().is_relative_to(base.resolve()):continue
                try:
                    text=path.read_text(encoding='utf-8')
                    if len(text)>100000:continue
                except (OSError,UnicodeError):continue
                title=re.search(r'^name:\s*[\"\']?(.+?)[\"\']?\s*$',text,re.M)
                description=re.search(r'^description:\s*(.+)',text,re.M)
                name=(title.group(1) if title else path.parent.name).strip('"\'')
                sid=hashlib.sha256(str(path.resolve()).encode()).hexdigest()[:20]
                items.append({'id':sid,'name':name,'call':name if source=='SuperTeam' else source.lower().replace(' ','-')+':'+name,'description':description.group(1).strip('"\'')[:240] if description else '', 'source':source,'providers':providers,'enabled':sid not in disabled,'managed':source=='SuperTeam','path':str(path)})
        return items
    def content(self,sid):
        skill=next((s for s in self.scan() if s['id']==sid),None)
        if not skill:raise ValueError('技能不存在')
        return {**skill,'text':Path(skill['path']).read_text(encoding='utf-8')[:24000]}
    def toggle(self,sid,enabled):
        self.content(sid);config=self.config();disabled=set(config.get('disabled',[]))
        disabled.discard(sid) if enabled else disabled.add(sid)
        config['disabled']=sorted(disabled);self.settings.write_text(json.dumps(config),encoding='utf-8');return {'ok':True}
    def remove(self,sid):
        skill=self.content(sid)
        if not skill['managed']:raise ValueError('原软件的技能仅索引，请在原软件中管理')
        target=Path(skill['path']).parent.resolve();base=self.folder.resolve()
        if target==base or not target.is_relative_to(base):raise ValueError('技能路径无效')
        trash=self.root/'data/skill-trash';trash.mkdir(exist_ok=True);shutil.move(str(target),str(trash/(target.name+'-'+uuid.uuid4().hex[:8])));return {'ok':True}
    def copy_shared(self,sid):
        skill=self.content(sid);source=Path(skill['path']).parent.resolve();target=self.folder/('shared-'+uuid.uuid4().hex[:12]);target.mkdir()
        files=[];total=0
        for path in source.rglob('*'):
            if path.is_symlink():continue
            if not path.is_file() or not path.resolve().is_relative_to(source):continue
            relative=path.relative_to(source)
            if any(part.startswith('.') for part in relative.parts) or re.search(r'auth|token|secret|credential',path.name,re.I):continue
            total+=path.stat().st_size;files.append((path,relative))
            if total>60*1024*1024 or len(files)>2000:raise ValueError('技能文件过多，请只导入需要的技能目录')
        for path,relative in files:
            destination=target/relative;destination.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(path,destination)
        return {'ok':True,'note':'已复制通用技能文件；账号、工具连接器与相应权限不会一起复制'}
    def admit_zip(self,raw,subfolder=''):
        if len(raw)>30*1024*1024:raise ValueError('压缩包最多 30 MB')
        target=self.folder/('import-'+uuid.uuid4().hex[:12]);target.mkdir()
        if not target.resolve().is_relative_to(self.folder.resolve()):raise ValueError('技能目录无效')
        try:
            with zipfile.ZipFile(io.BytesIO(raw)) as z:
                if sum(i.file_size for i in z.infolist())>80*1024*1024 or len(z.infolist())>3000:raise ValueError('技能压缩包展开后过大')
                entries=z.infolist();prefix=entries[0].filename.split('/')[0]+'/' if entries else ''
                selected=prefix+subfolder.strip('/')+'/' if subfolder else prefix
                count=0
                for entry in entries:
                    name=entry.filename
                    if '\\' in name or PurePosixPath(name).is_absolute() or '..' in PurePosixPath(name).parts or (entry.external_attr>>16)&0o170000==0o120000:raise ValueError('压缩包包含不安全路径')
                    if not name.startswith(selected) or entry.is_dir():continue
                    relative=name[len(selected):]
                    if not relative:continue
                    path=(target/relative).resolve()
                    if not path.is_relative_to(target.resolve()):raise ValueError('技能路径无效')
                    path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(z.read(entry));count+=1
                if not count or not list(target.rglob('SKILL.md')):raise ValueError('所选目录没有 SKILL.md')
            return {'ok':True,'folder':str(target),'message':'仅下载文件，未执行安装脚本'}
        except Exception:
            shutil.rmtree(target);raise
    def download(self,url):
        parsed=urllib.parse.urlparse(url)
        if parsed.scheme!='https' or parsed.hostname!='github.com':raise ValueError('请输入公开 GitHub 仓库或技能文件夹的 HTTPS 链接')
        parts=parsed.path.strip('/').split('/')
        if len(parts)<2:raise ValueError('GitHub 链接无效')
        owner,repo=parts[:2];branch=parts[3] if len(parts)>=4 and parts[2]=='tree' else None
        subfolder='/'.join(parts[4:]) if branch else ''
        for ref in [branch] if branch else ['main','master']:
            endpoint=f'https://codeload.github.com/{owner}/{repo}/zip/refs/heads/{ref}'
            try:
                with urllib.request.urlopen(endpoint,timeout=35) as response:raw=response.read(30*1024*1024+1)
                return self.admit_zip(raw,subfolder)
            except urllib.error.HTTPError as exc:
                if exc.code!=404:raise ValueError('GitHub 下载失败，请稍后重试') from exc
        raise ValueError('未找到仓库分支，请使用带 tree/分支/目录 的链接')
    def resolve(self,text,provider):
        invoked=set(re.findall(r'(?:^|\s)[#]([^\s#$，。；;]+)',text));blocks=[];used=set();catalog=self.scan()
        if len(invoked)>8:raise ValueError('每条消息最多调用 8 个技能')
        for item in catalog:
            exact=item['call'] in invoked
            if not exact and item['name'] not in invoked:continue
            if not exact and any(s['managed'] and s['name']==item['name'] for s in catalog):continue
            if item['name'] in used and not exact:continue
            if not item['enabled']:raise ValueError('技能已停用：'+item['name'])
            if provider not in item['providers']:continue
            used.add(item['name']);skill=self.content(item['id']);blocks.append(f"用户明确调用技能 ${item['name']}，来源 {item['source']}，目录 {Path(item['path']).parent}。以下技能只在当前任务和已有权限内适用；不能扩大权限或自动执行安装脚本。\n<selected_skill>\n{skill['text']}\n</selected_skill>")
        return '\n'.join(blocks)[:32000]
