"""Local lexical retrieval, with provenance; never calls it a verified summary."""
import re

def retrieve(messages,query,limit=6):
    selection=re.search(r'消息编号\s*([0-9、，,\s]+)',query)
    selected=set(int(x) for x in re.findall(r'\d+',selection.group(1))) if selection else set()
    tokens=set(re.findall(r'[a-zA-Z0-9_]{2,}|[\u4e00-\u9fff]{2,}',query.lower()))
    for token in list(tokens):
        if re.search(r'[\u4e00-\u9fff]',token):tokens.update(token[i:i+2] for i in range(len(token)-1))
    ranked=[]
    for m in messages:
        if m['author']=='system':continue
        text=m['text'].lower();score=sum(min(text.count(t),3) for t in tokens)
        if m['id'] in selected:score+=100
        if score and m.get('reaction'):score+=8
        if score:
            at=min((text.find(t) for t in tokens if t in text),default=0)
            ranked.append((score,m['id'],{**m,'excerpt':m['text'][max(0,at-160):max(0,at-160)+1600]}))
    return [r[2] for r in sorted(ranked,key=lambda r:(r[0],r[1]),reverse=True)[:limit]]
