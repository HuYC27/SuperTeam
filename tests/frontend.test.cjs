const {test}=require('node:test');
const assert=require('node:assert/strict');
const vm=require('node:vm');
const fs=require('node:fs');
const path=require('node:path');

async function harness(enhancements=false){
 const nodes=new Map(),storage=new Map();
 function node(){return {value:'',hidden:false,disabled:false,dataset:{},classList:{toggle(){},add(){},remove(){}},append(){},replaceChildren(){},setAttribute(){},addEventListener(){},focus(){},options:[],scrollHeight:0,scrollTop:0,clientHeight:0};}
 const document={querySelector(){return node();},addEventListener(){},getElementById(id){if(!nodes.has(id))nodes.set(id,node());return nodes.get(id);},querySelectorAll(){return [];},createElement:node,createElementNS:node,createTextNode:text=>text,body:node()};
 const sessionStorage={getItem:k=>storage.get(k)||null,setItem:(k,v)=>storage.set(k,String(v)),removeItem:k=>storage.delete(k)};
 let resolve;const sendGate={promise:new Promise(r=>resolve=r),resolve:v=>resolve(v)};
 const context=vm.createContext({document,sessionStorage,localStorage:sessionStorage,location:{hash:'#test',pathname:'/'},history:{replaceState(){}},fetch:async()=>({ok:true,json:async()=>({rooms:[],jobs:[],profiles:{},models:{}})}),setInterval:()=>0,clearInterval(){},setTimeout,matchMedia:()=>({matches:false}),URL,URLSearchParams,Blob,console,sendGate});
 vm.runInContext(fs.readFileSync(path.join(__dirname,'../ui/app.js'),'utf8'),context);
 if(enhancements)vm.runInContext(fs.readFileSync(path.join(__dirname,'../ui/superteam.js'),'utf8'),context);
 await new Promise(setImmediate);
 vm.runInContext(`
 current='A';room={id:'A',members:['codex'],settings:{mode:'chat'}};
 state={rooms:[],jobs:[],profiles:{},models:{}};
 renderActivity=()=>{};renderRooms=()=>{};
 refreshRoom=async()=>{room={id:current,members:['codex'],settings:{mode:'chat'}};};
 let calls=0;api=async(path)=>{if(path==='send'){calls++;return await sendGate.promise;}return {};};
 pending.set('A',[{id:'a'}]);pending.set('B',[{id:'b'}]);
 $('messageInput').value='A original';localStorage.setItem('draft:A','A original');localStorage.setItem('draft:B','B original');
 `,context);
 return {context,document,sendGate,get:code=>JSON.parse(vm.runInContext('JSON.stringify('+code+')',context))};
}

test('sending then changing room preserves the destination draft and attachments',async()=>{
 const h=await harness();const send=h.document.getElementById('composer').onsubmit({preventDefault(){}});
 await vm.runInContext("selectRoom('B')",h.context);
 h.sendGate.resolve({id:'jobA',room:'A',status:'running'});await send;
 assert.equal(h.document.getElementById('messageInput').value,'B original');
 assert.deepEqual(h.get("pending.get('B')"),[{id:'b'}]);
 assert.deepEqual(h.get("pending.get('A')"),[]);
 assert.equal(h.get("localStorage.getItem('draft:B')"),'B original');
});

test('double submit starts only one request before the first receipt',async()=>{
 const h=await harness();const first=h.document.getElementById('composer').onsubmit({preventDefault(){}});
 await h.document.getElementById('composer').onsubmit({preventDefault(){}});
 assert.equal(h.get('calls'),1);
 h.sendGate.resolve({id:'jobA',room:'A',status:'running'});await first;
});

test('new edits and queued attachments are retained while sending the previous draft',async()=>{
 const h=await harness();const send=h.document.getElementById('composer').onsubmit({preventDefault(){}});
 vm.runInContext("$('messageInput').value='A newer';localStorage.setItem('draft:A','A newer');pending.get('A').push({id:'new'});",h.context);
 h.sendGate.resolve({id:'jobA',room:'A',status:'running'});await send;
 assert.equal(h.document.getElementById('messageInput').value,'A newer');
 assert.equal(h.get("localStorage.getItem('draft:A')"),'A newer');
 assert.deepEqual(h.get("pending.get('A')"),[{id:'new'}]);
});

test('stale room data cannot open settings or submit for a newly selected room',async()=>{
 const h=await harness();vm.runInContext("current='B';room={id:'A'};",h.context);
 assert.doesNotThrow(()=>vm.runInContext('openSettings()',h.context));
 await h.document.getElementById('composer').onsubmit({preventDefault(){}});
 assert.equal(h.get('calls'),0);
});

test('mention keyboard selects a filtered member without submitting the form',async()=>{
 const h=await harness(true);
 vm.runInContext(`room={id:'A',members:['codex','deepseek'],settings:{roles:{}}};$('messageInput').value='请 @Deep';$('messageInput').selectionStart=7;$('messageInput').setSelectionRange=()=>{};suggestMentions();`,h.context);
 assert.deepEqual(h.get('mentionChoices'),['deepseek']);
 assert.equal(vm.runInContext(`mentionKey({key:'Enter',preventDefault(){}})`,h.context),true);
 assert.equal(h.document.getElementById('messageInput').value,'请 @DeepSeek ');
 assert.equal(h.get('calls'),0);
});
test('private mention picker excludes all and other members',async()=>{
 const h=await harness(true);
 vm.runInContext(`$('messageInput').value='@';$('messageInput').selectionStart=1;suggestMentions();`,h.context);
 assert.deepEqual(h.get('mentionChoices'),['codex']);
});


test('concurrent preview loads share one blob and release it on room change',async()=>{
 const h=await harness();
 vm.runInContext(`let previewFetches=0,revoked=[];URL={createObjectURL:()=> 'blob:synthetic',revokeObjectURL:u=>revoked.push(u)};fetch=async()=>{previewFetches++;return {ok:true,blob:async()=>new Blob(['synthetic'])};};`,h.context);
 await vm.runInContext(`Promise.all([cachedPreview('image','/file'),cachedPreview('image','/file')])`,h.context);
 assert.equal(h.get('previewFetches'),1);
 assert.equal(h.get('fileUrls.size'),1);
 await vm.runInContext(`selectRoom('B')`,h.context);
 assert.equal(h.get('fileUrls.size'),0);
 assert.deepEqual(h.get('revoked'),['blob:synthetic']);
});
