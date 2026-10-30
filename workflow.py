"""Transparent, editable task preferences, not claimed model benchmarks."""
import re,json

def visible_answer(text):
    """Keep machine-only routing out of final messages and streaming previews."""
    return re.split(r'<superteam-route(?:>|$)',str(text),maxsplit=1)[0].rstrip()

def selected_peers(text,members,leader):
    match=re.search(r'<superteam-route>\s*(\{[\s\S]*?\})\s*</superteam-route>\s*$',str(text))
    if not match:return []
    try:data=json.loads(match.group(1))
    except ValueError:return []
    selected=[];seen={leader}
    for item in data.get('next',[]) if isinstance(data,dict) and isinstance(data.get('next'),list) else []:
        if not isinstance(item,dict):continue
        member=item.get('member');task=item.get('task')
        if member in members and member not in seen and isinstance(task,str) and task.strip():
            selected.append((member,task.strip()[:600]));seen.add(member)
    return selected

def classify_message(text,attachments=None):
    clean=re.sub(r'@(?:Codex|DeepSeek|WorkBuddy|全体成员)\s*','',text,flags=re.I).strip(' ，。！!？?~～')
    if not attachments and re.fullmatch(r'(?:你们|大家|你)?(?:好|好啊|好呀|好哦)|早上好|晚上好|早|嗨|哈喽|hello|hi|谢谢|感谢|再见',clean,re.I):return 'greeting'
    if re.search(r'各自|各提|分别.*(?:建议|意见|观点)|每人|独立.*(?:回答|建议)',clean):return 'opinion'
    if re.search(r'实现|编程|脚本|修复|调试|写入|生成|制作|汇总|接力|分工|交接|修改|处理文件|执行|完成任务',clean,re.I):return 'task'
    return 'chat'

def explicit_assignments(text,members):
    matches=list(re.finditer(r'\b(Codex|DeepSeek|WorkBuddy)\b\s*(?:负责|先)?',text,re.I))
    if len({m.group(1).lower() for m in matches})<2:return {},[]
    assignments={}
    order=[]
    for i,m in enumerate(matches):
        p=m.group(1).lower()
        if p not in members:continue
        content=text[m.end():matches[i+1].start() if i+1<len(matches) else len(text)].strip(' 、，,；;。')
        if content and p not in assignments:assignments[p]=content[:300];order.append(p)
    return assignments,order

PROFILES={'api':{'name':'自定义 API','focus':'使用用户配置的 API 分析材料并回答问题','keywords':[]},
 'doubao':{'name':'豆包','focus':'已加入联系人，站内自动回复尚未接通','keywords':[]},
 'qwen':{'name':'千问','focus':'原软件聊天已验证，站内自动回复尚未接通','keywords':[]},
 'workbuddy':{'name':'WorkBuddy','focus':'文本分析、方案整理与写作；当前连接不执行工具','keywords':['写作','整理','润色','总结','文案']},
 'codex':{'name':'Codex','focus':'代码实现、调试、工程执行与文件处理','keywords':['代码','脚本','python','bug','调试','实现','编程','测试','搭建','报错','工程','运行','重构','工具']},
 'deepseek':{'name':'DeepSeek','focus':'概念解释、问题拆解、资料分析与方案推演','keywords':['解释','原理','分析','论文','文献','思路','研究','实验','综述','概念','比较','设计','论证']}
}

def resolve_target(text,target='auto'):
    if re.search(r'@(?:全体成员|所有人|全体|everyone|all)(?:\s|$|[，,:：。])',text,re.I):return 'all'
    match=re.search(r'@(codex|deepseek|workbuddy)(?:\b|[，,:：。])',text,re.I)
    return match.group(1).lower() if match else target

def choose_order(text,members,profiles=None,leader='auto',roles=None,feedback_scores=None):
    if leader in members:return [leader]+[m for m in members if m!=leader],f'由你指定 {PROFILES[leader]["name"]} 先处理'
    profiles=profiles or PROFILES
    if roles:
        vocabulary={k for p in PROFILES.values() for k in p['keywords']}
        profiles={m:{**profiles.get(m,{}),'keywords':(profiles.get(m,PROFILES[m])['keywords'] if roles.get(m)==PROFILES[m]['focus'] else
                  [k for k in vocabulary if k in roles.get(m,'')]+[k.strip() for k in re.split('[、，,；; /]',roles.get(m,'')) if len(k.strip())>1])} for m in members}
    scores={m:sum(3 if k in ['代码','脚本','python','调试','编程','解释','原理','论文','文献'] else 1 for k in profiles.get(m,{}).get('keywords',PROFILES[m]['keywords']) if k.lower() in text.lower()) for m in members}
    for member,value in (feedback_scores or {}).items():
        if member in scores:scores[member]+=max(-2,min(2,value))
    order=sorted(members,key=lambda m:-scores[m])
    lead=order[0]
    return order,f'{PROFILES[lead]["name"]} 先处理，依据当前任务与职责偏好匹配；后手阅读结果后接力'
