'use strict';
function groupAvatar(members){
 if(members.length===1)return avatar(members[0]);
 const group=el('div','avatar group-avatar');group.style.setProperty('--member-columns',members.length<=4?'2':'3');group.style.setProperty('--member-rows',members.length<=2?'1':members.length<=6?'2':'3');group.setAttribute('aria-label',members.map(p=>names[p]).join('、'));
 members.slice(0,9).forEach(p=>group.append(avatar(p)));return group;
}
function enhanceHeader(){
 const old=$('headerAvatar'),image=groupAvatar(room.members);image.id='headerAvatar';old.replaceWith(image);
 $('permissionBadge').textContent=({'read-only':'只读','workspace-write':'工作区可写','danger-full-access':'完整访问'})[room.settings.permission];
 if(room.members.length===1&&room.members[0]==='workbuddy')$('permissionBadge').textContent='仅文本';
 $('permissionBadge').title='附件可读 · 联网能力未核验 · '+(room.settings.permission==='read-only'?'文件不可修改':'写入范围以所选权限为准');
 $('messageInput').placeholder=room.members.length===1?'想问 '+names[room.members[0]]+' 什么？':'发消息，输入 @ 选择成员…';
 $('replyHint').disabled=room.members.length===1;
}
function renderMemberStatus(job){
 if(!loaded())return;
 const latest=job||room.tasks?.[0];
 const line=el('div','member-presence');
 for(const p of room.members){
  const step=latest?.steps?.filter(s=>s.provider===p&&(!job||!s.round||s.round===job.round)).at(-1);
  const status=job?(step?.status==='running'?'思考中':step?.status==='completed'?'已回答，等待本轮结束':step?.status==='failed'?'受阻':'等待'):step?.status==='completed'?'已回答':step?.status==='failed'?'受阻':'等待提问';
  const chip=el('span','presence-chip');chip.append(avatar(p),el('span','',names[p]+' · '+status));chip.title=room.settings.roles[p]+'；附件可读；联网未核验；'+$('permissionBadge').textContent;line.append(chip);
 }
 if(!job)$('activity').append(line);
 else{const progress=el('span','round-progress','第 '+(job.round||1)+' / '+(job.rounds||1)+' 轮 · 尚未结束');$('activity').append(progress,line);}
}
function messageExtras(wrap,m,bubble){
 if(m.author==='system')return;if(typeof appendGeneratedFiles==='function')appendGeneratedFiles(wrap,m);
 const actions=el('div','message-actions');
 const copy=el('button','message-action');copy.title='复制';copy.setAttribute('aria-label','复制消息');copy.append(icon('copy'));
 copy.onclick=async()=>{try{await navigator.clipboard.writeText(m.text||'');copy.title='已复制';copy.setAttribute('aria-label','已复制');}catch{showError('复制未成功，请选中文字后复制。');}};actions.append(copy);
 if(!m.id){actions.append(el('span','streaming-label','回答中 · 尚未完成'));wrap.append(actions);return;}
 if(m.author!=='user')for(const [value,label] of [['supported','支持'],['opposed','不支持']]){
  const b=el('button','message-action'+((m.reaction==='accepted'?'supported':m.reaction)===value?' selected':''),label);b.setAttribute('aria-pressed',String((m.reaction==='accepted'?'supported':m.reaction)===value));b.title=label;b.setAttribute('aria-label',label);b.replaceChildren(icon(value==='supported'?'thumbsup':'thumbsdown'));
  b.onclick=async()=>{const rid=current;try{await api('react',{room:rid,message:m.id,value:(m.reaction==='accepted'?'supported':m.reaction)===value?'':value});if(current===rid){lastMessages='';await refreshRoom();}}catch(e){showError(e.message);}};actions.append(b);
 }
 const active=activeJob();if(active&&active.steps.some(s=>s.message_id===m.id))actions.append(el('span','streaming-label',room?.members.length===1?'已回答，正在整理结果':'本成员已回答 · 整轮尚未结束'));wrap.append(actions);
 const references=[...(m.text||'').matchAll(/\[附件[:：]([^\]\n]+)\]/g)];
 if(references.length){const list=el('div','reference-links');const used=new Set();for(const match of references){const ref=match[1].trim(),id=ref.split('|')[0],matching=room.files.filter(f=>f.name===ref);const f=room.files.find(f=>f.id===id)||(matching.length===1?matching[0]:null);if(!f||used.has(f.id))continue;used.add(f.id);const a=el('button','message-action','↗ '+f.name);a.title='打开原始材料核对；引用是否支持结论仍需核查';a.onclick=()=>downloadFile(f);list.append(a);}wrap.append(list);}
}
function addRolePresets(){
 const presets=['代码实现、调试、工程执行与文件处理','概念解释、问题拆解、资料分析与方案推演','论文阅读、证据核对与实验设计','结果复核、寻找遗漏与风险'];
 for(const p of room.members){const input=$('role-'+p),select=el('select','text-input role-preset');select.setAttribute('aria-label',names[p]+' 能力预设');select.append(new Option('选择能力预设（可继续编辑）',''));for(const text of presets)select.append(new Option(text,text));select.onchange=()=>{if(select.value)input.value=select.value;};input.before(select);}
}
let styleRoom=null;
$('replyHint').onclick=()=>{if(!loaded()||room.members.length<2)return;styleRoom=current;$('conversationSelect').value=room.settings.conversation||'handoff';$('cyclesSelect').value=room.settings.cycles||1;estimateCalls();inlineError('styleError','');$('styleDialog').showModal();};
function estimateCalls(){const mode=$('conversationSelect').value,fixed=['expert','specialist','review'].includes(mode);$('cyclesSelect').disabled=fixed;$('cyclesSelect').closest('.cycles-field')?.toggleAttribute('hidden',fixed);$('cyclesSelect').querySelector('option[value="1"]').disabled=mode==='discussion';if(mode==='discussion'&&Number($('cyclesSelect').value)<2)$('cyclesSelect').value='2';const count=room?.members.length||1,rounds=Number($('cyclesSelect').value);const notes={expert:'默认由两位成员参与：首位推进，第二位核对、补充并收束。通常 2 次回答，不自动拉全员。',review:'两位成员参与：首位给出答案，第二位检查证据、错误与遗漏，并给出修正结论。通常 2 次回答。',specialist:'你主动选择单成员回答：只调用最相关的一位，通常 1 次。@全体或明确多人分工时仍按你的要求。',discussion:'所有成员按顺序讨论 '+rounds+' 轮，最多 '+count*rounds+' 次回答；后手看得到前手内容，最后一轮收束。',handoff:'按职责依次接力，最多 '+count*rounds+' 次回答；后手读取前手的真实结果。',parallel:'所有成员独立判断，最多 '+count*rounds+' 次回答；同一轮互不读取对方答案。'};const english={expert:'Two members: the first advances the answer, the second reviews and concludes. Usually 2 replies.',review:'Two members: answer first, then check evidence, errors and omissions. Usually 2 replies.',specialist:'You selected one relevant member. Usually 1 reply; explicit mentions and assignments take priority.',discussion:'All members take turns over '+rounds+' rounds, up to '+count*rounds+' replies. Conclude in the last round.',handoff:'Follow the assigned roles in order, up to '+count*rounds+' replies. Later members see earlier results.',parallel:'Independent judgments, up to '+count*rounds+' replies. Members do not see one another within the same round.'};$('callEstimate').textContent=typeof uiText==='function'?uiText(notes[mode]||'',english[mode]||''):notes[mode]||'';}
$('cyclesSelect').onchange=estimateCalls;$('conversationSelect').onchange=estimateCalls;$('closeStyle').onclick=()=>$('styleDialog').close();
$('styleForm').onsubmit=async e=>{e.preventDefault();if(styleRoom!==current)return inlineError('styleError','聊天已切换，请重新打开。');try{await api('settings',{room:styleRoom,settings:{conversation:$('conversationSelect').value,cycles:Number($('cyclesSelect').value)}});$('styleDialog').close();await refreshRoom();}catch(e){inlineError('styleError',e.message);}};

let mentionStart=-1,mentionEnd=0,mentionIndex=0,mentionChoices=[];
function suggestMentions(force=false){
 if(!loaded())return;
 const input=$('messageInput'),before=input.value.slice(0,input.selectionStart),match=before.match(/(?:^|\s)@([^\s@]*)$/);
 if(!match&&!force){$('mentionMenu').hidden=true;return;}
 const query=match?match[1].toLowerCase():'';mentionStart=match?input.selectionStart-query.length-1:-1;mentionEnd=input.selectionStart;
 const choices=room.members.length>1?['all',...room.members]:room.members;
 mentionChoices=choices.filter(p=>(p==='all'?'全体成员':names[p]).toLowerCase().includes(query));mentionIndex=0;drawMentions();
}
function drawMentions(){const menu=$('mentionMenu');menu.replaceChildren();mentionChoices.forEach((p,i)=>{const b=el('button',i===mentionIndex?'selected':'');b.type='button';b.setAttribute('role','option');b.setAttribute('aria-selected',String(i===mentionIndex));b.append(p==='all'?groupAvatar(room.members):avatar(p),el('span','','@'+(p==='all'?'全体成员':names[p])));b.onmousedown=e=>e.preventDefault();b.onclick=()=>chooseMention(p);menu.append(b);});menu.setAttribute('role','listbox');menu.hidden=!mentionChoices.length;}
function chooseMention(p){const input=$('messageInput'),name='@'+(p==='all'?'全体成员':names[p])+' ';if(mentionStart>=0){input.value=input.value.slice(0,mentionStart)+name+input.value.slice(mentionEnd);input.focus();input.setSelectionRange(mentionStart+name.length,mentionStart+name.length);}else{input.value=name+input.value;input.focus();}localStorage.setItem('draft:'+current,input.value);$('mentionMenu').hidden=true;renderActivity();}
function mentionKey(event){if(event.isComposing||$('mentionMenu').hidden)return false;if(['ArrowDown','ArrowUp','Enter','Escape','Tab'].includes(event.key)){event.preventDefault();if(event.key==='Escape')$('mentionMenu').hidden=true;else if(event.key==='Enter'||event.key==='Tab')chooseMention(mentionChoices[mentionIndex]);else{mentionIndex=(mentionIndex+(event.key==='ArrowDown'?1:-1)+mentionChoices.length)%mentionChoices.length;drawMentions();}return true;}return false;}
$('mention').onclick=()=>{if(!$('mentionMenu').hidden){$('mentionMenu').hidden=true;return;}suggestMentions(true);};
$('messageInput').addEventListener('click',()=>suggestMentions());

function wireRoomActions(button,r){
 button.oncontextmenu=e=>{e.preventDefault();showRoomMenu(r,e.clientX,e.clientY);};
 button.addEventListener('keydown',e=>{if(e.key==='ContextMenu'||(e.shiftKey&&e.key==='F10')){e.preventDefault();const rect=button.getBoundingClientRect();showRoomMenu(r,rect.left,rect.bottom);}});
 let start=null;button.addEventListener('pointerdown',e=>{if(e.pointerType==='touch')start=[e.clientX,e.clientY];});button.addEventListener('pointerup',e=>{if(start&&start[0]-e.clientX>65&&Math.abs(start[1]-e.clientY)<35)showRoomMenu(r,e.clientX,e.clientY);start=null;});
}
function showRoomMenu(r,x,y){const menu=$('roomMenu');menu.replaceChildren();const actions=r.visibility&&r.visibility!=='visible'?[['visible','恢复聊天']]:[['hidden','隐藏聊天'],['deleted','移入回收站']];for(const [value,label] of actions){const b=el('button','',label);b.setAttribute('role','menuitem');b.onclick=async()=>{menu.hidden=true;try{await api('visibility',{room:r.id,value});if(current===r.id&&value!=='visible'){localStorage.setItem('draft:'+current,$('messageInput').value);current=null;room=null;}lastRooms='';await refresh();showError(value==='visible'?'聊天已恢复。':'已收纳，记录与文件仍保留，可从“收纳”恢复。');}catch(e){showError(e.message);}};menu.append(b);}menu.style.left=Math.min(x,innerWidth-180)+'px';menu.style.top=Math.min(y,innerHeight-110)+'px';menu.hidden=false;menu.firstChild?.focus();}
document.addEventListener('pointerdown',e=>{if(!$('roomMenu').contains(e.target))$('roomMenu').hidden=true;});document.addEventListener('keydown',e=>{if(e.key==='Escape'){$('roomMenu').hidden=true;$('mentionMenu').hidden=true;}});

$('addAI').onclick=async()=>{$('discoverDialog').showModal();$('discoverResults').replaceChildren(el('p','field-note','正在查找本机安装的 AI…'));try{const data=await api('discover');$('discoverResults').replaceChildren();for(const app of data.apps){const row=el('div','discover-row');if(app.icon){const img=el('img','avatar');img.src=app.icon;img.alt=app.name;row.append(img);}const info=el('div','contact-info');info.append(el('h3','',app.name),el('p','field-note',app.detail));row.append(info);const b=el('button','button secondary',app.supported?'加入':'暂不支持');b.disabled=!app.supported;b.onclick=async()=>{try{let r=state.rooms.find(r=>r.members.length===1&&r.members[0]===app.id);if(r&&r.visibility!=='visible')await api('visibility',{room:r.id,value:'visible'});if(!r)r=await api('rooms',{name:names[app.id],members:[app.id]});$('discoverDialog').close();await refresh();await selectRoom(r.id);}catch(e){showError(e.message);}};row.append(b);$('discoverResults').append(row);}if(!data.apps.length)$('discoverResults').append(el('p','','没有找到支持的软件，请先安装并登录。'));}catch(e){$('discoverResults').textContent=e.message;}};
$('closeDiscover').onclick=()=>$('discoverDialog').close();

let cropImage=null,cropUrl=null,cropX=0,cropY=0,cropBase=1,cropDrag=null;
const canvas=$('cropCanvas');
function drawCrop(){if(!cropImage)return;const scale=cropBase*Number($('cropZoom').value),w=cropImage.width*scale,h=cropImage.height*scale;cropX=Math.min(0,Math.max(320-w,cropX));cropY=Math.min(0,Math.max(320-h,cropY));const ctx=canvas.getContext('2d');ctx.clearRect(0,0,320,320);ctx.drawImage(cropImage,cropX,cropY,w,h);}
$('selfAvatar').onclick=()=>{if(typeof openProfile==='function')openProfile();else $('avatarInput').click();};$('selfAvatar').onkeydown=e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();if(typeof openProfile==='function')openProfile();else $('avatarInput').click();}};
$('avatarInput').onchange=async()=>{const f=$('avatarInput').files[0];$('avatarInput').value='';if(!f)return;if(f.size>6*1024*1024)return showError('头像图片最多 6 MB');if(cropUrl)URL.revokeObjectURL(cropUrl);cropUrl=URL.createObjectURL(f);const im=new Image();im.onload=()=>{if(im.width*im.height>25000000)return showError('头像图片最多 2500 万像素');cropImage=im;cropBase=Math.max(320/im.width,320/im.height);cropX=(320-im.width*cropBase)/2;cropY=(320-im.height*cropBase)/2;$('cropZoom').value=1;inlineError('avatarError','');$('avatarDialog').showModal();drawCrop();};im.onerror=()=>showError('图片无法读取，请选择 PNG、JPEG 或 WebP');im.src=cropUrl;};
canvas.onpointerdown=e=>{cropDrag=[e.clientX,e.clientY,cropX,cropY];canvas.setPointerCapture(e.pointerId);};canvas.onpointermove=e=>{if(!cropDrag)return;const rect=canvas.getBoundingClientRect(),factor=320/rect.width;cropX=cropDrag[2]+(e.clientX-cropDrag[0])*factor;cropY=cropDrag[3]+(e.clientY-cropDrag[1])*factor;drawCrop();};canvas.onpointerup=canvas.onpointercancel=()=>cropDrag=null;
$('cropZoom').oninput=()=>{drawCrop();};$('closeAvatar').onclick=()=>$('avatarDialog').close();$('saveAvatar').onclick=async()=>{try{if(!cropImage)return;await api('avatar',{data:canvas.toDataURL('image/png').split(',')[1]});$('avatarDialog').close();lastMessages='';await refresh();}catch(e){inlineError('avatarError',e.message);}};

function compareTask(item,task){if(!task.steps.every(s=>s.message_id)){item.append(el('p','field-note','旧协作记录未绑定消息编号，请在聊天记录中核对。'));return;}const button=el('button','message-action','并排比较');button.onclick=()=>{const ids=new Set(task.steps.map(s=>s.message_id).filter(Boolean));const relevant=room.messages.filter(m=>ids.size?ids.has(m.id):room.members.includes(m.author)&&m.created>=task.started&&m.created<=task.started+(task.elapsed||0));if(!relevant.length)return;const box=el('div','answer-comparison');for(const p of room.members){const m=relevant.filter(m=>m.author===p).at(-1);if(m){const col=el('section');col.append(el('h4','',names[p]));markdown(col,m.text);box.append(col);}}$('comparisonContent').replaceChildren(box);$('compareDialog').showModal();};item.append(button);const summary=el('button','message-action','按需汇总');summary.onclick=()=>{const ids=task.steps.map(s=>s.message_id).filter(Boolean);switchView('chat');$('messageInput').value='@'+names[room.members[0]]+' 请比较消息编号 '+ids.join('、')+' 的回答，按照我的支持与不支持反馈，给出共同结论、关键分歧和下一步。不要重复全文。';localStorage.setItem('draft:'+current,$('messageInput').value);$('messageInput').focus();showError('汇总要求已放入输入框，发送后才会调用所选 AI。');};item.append(summary);}

$('searchHistory').onclick=()=>{if(!loaded())return;$('historyHits').replaceChildren();$('historyDialog').dataset.room=current;$('historyDialog').showModal();$('historyQuery').focus();};$('closeHistory').onclick=()=>$('historyDialog').close();
$('historyForm').onsubmit=async e=>{e.preventDefault();const rid=$('historyDialog').dataset.room;try{const data=await api('search?room='+rid+'&q='+encodeURIComponent($('historyQuery').value));if(rid!==$('historyDialog').dataset.room)return;$('historyHits').replaceChildren();for(const m of data.hits){const row=el('div','history-hit');row.append(el('strong','',(names[m.author]||m.author)+' · 消息 #'+m.id),el('p','',m.excerpt));$('historyHits').append(row);}if(!data.hits.length)$('historyHits').append(el('p','field-note','没有找到相关旧消息。'));}catch(e){showError(e.message);}};

$('closeCompare').onclick=()=>$('compareDialog').close();$('mention').replaceChildren(icon('at'));

$('messageInput').addEventListener('keyup',e=>{if(!['Enter','Escape','ArrowUp','ArrowDown','Tab'].includes(e.key))suggestMentions();});

// Repaint an initial list that may have arrived before this module defined composite avatars.
lastRooms='';renderRooms();
