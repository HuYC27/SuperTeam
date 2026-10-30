'use strict';
(() => {
 const pane=new URLSearchParams(location.search).get('pane')==='1';
 iconPaths.activity='M21 12a9 9 0 1 1-18 0 9 9 0 0 1 18 0ZM12 7v5l3 2';
 $('showActivity').replaceChildren(icon('activity'));
 // This command is distinct from maximizing and occupies its own changing icon.
 const full=$('windowFullscreen'),max=$('windowMaximize');
 if(full&&max)max.before(full);
 iconPaths.fullscreenExit='M3 8h5V3m13 5h-5V3M3 16h5v5m13-5h-5v5';
 let windowState={fullscreen:false,maximized:false};
 function windowButtons(data){windowState={...windowState,...data};full.replaceChildren(icon(windowState.fullscreen?'fullscreenExit':'fullscreen'));full.title=uiText(windowState.fullscreen?'退出全屏（F11）':'全屏（F11）',windowState.fullscreen?'Exit fullscreen (F11)':'Fullscreen (F11)');full.setAttribute('aria-label',full.title);full.setAttribute('aria-pressed',String(windowState.fullscreen));max.replaceChildren(icon(windowState.maximized?'restore':'maximize'));max.title=uiText(windowState.maximized?'还原':'最大化',windowState.maximized?'Restore':'Maximize');max.setAttribute('aria-label',max.title);}
 function wireWindowButtons(){if(!full||!max)return;full.onclick=async()=>{try{windowButtons(await nativeAction('toggle_fullscreen'));}catch(e){showError(e.message);}};max.onclick=async()=>{try{windowButtons(await nativeAction('toggle_maximize'));}catch(e){showError(e.message);}};windowButtons({});}
 window.addEventListener('pywebviewready',wireWindowButtons);wireWindowButtons();
 if(pane)return;
 const history=$('activityPanel'),terminal=document.querySelector('.terminal-panel');
 if(terminal)terminal.id='terminalPanel';
 function separator(cls,label,orientation){const node=el('div',cls);node.tabIndex=0;node.setAttribute('role','separator');node.setAttribute('aria-label',label);node.setAttribute('aria-orientation',orientation);return node;}
 const historyHandle=separator('activity-resize','调整协作记录宽度','vertical');historyHandle.id='activityResize';history.prepend(historyHandle);
 const terminalHandle=separator('terminal-resize','调整终端高度','horizontal');terminalHandle.id='terminalResize';terminal.prepend(terminalHandle);
 function railWidth(){return parseFloat(getComputedStyle(document.documentElement).getPropertyValue('--workspace-rail'))||68;}
 function historyWidth(width){const sidebar=document.querySelector('.sidebar'),sidebarWidth=sidebar.getBoundingClientRect().width&&getComputedStyle(sidebar).display!=='none'?sidebar.getBoundingClientRect().width:0;const minChat=document.body.classList.contains('chat-split-open')?400:260;const available=innerWidth-railWidth()-sidebarWidth-minChat;const maxWidth=Math.max(170,Math.min(640,available));const value=Math.max(Math.min(240,maxWidth),Math.min(maxWidth,width));document.body.style.setProperty('--activity-width',value+'px');historyHandle.setAttribute('aria-valuemin',String(Math.min(240,maxWidth)));historyHandle.setAttribute('aria-valuemax',String(maxWidth));historyHandle.setAttribute('aria-valuenow',String(Math.round(value)));}
 function terminalHeight(height){const maxHeight=Math.max(130,Math.min(600,innerHeight-34-220));const value=Math.max(130,Math.min(maxHeight,height));document.body.style.setProperty('--terminal-height',value+'px');terminalHandle.setAttribute('aria-valuemin','130');terminalHandle.setAttribute('aria-valuemax',String(maxHeight));terminalHandle.setAttribute('aria-valuenow',String(Math.round(value)));}
 function drag(handle,onMove,cursor){let active=null;handle.onpointerdown=e=>{if(e.button!==0)return;active=e.pointerId;handle.setPointerCapture(active);document.body.classList.add('workspace-resizing');document.body.style.cursor=cursor;e.preventDefault();};handle.onpointermove=e=>{if(e.pointerId===active)onMove(e);};handle.onpointerup=handle.onpointercancel=handle.onlostpointercapture=()=>{active=null;document.body.classList.remove('workspace-resizing');document.body.style.cursor='';};}
 drag(historyHandle,e=>historyWidth(innerWidth-e.clientX),'col-resize');drag(terminalHandle,e=>terminalHeight(innerHeight-e.clientY),'row-resize');
 historyHandle.onkeydown=e=>{if(!['ArrowLeft','ArrowRight','Home','End'].includes(e.key))return;e.preventDefault();historyWidth(e.key==='Home'?240:e.key==='End'?640:Number(historyHandle.getAttribute('aria-valuenow'))+(e.key==='ArrowLeft'?24:-24));};
 terminalHandle.onkeydown=e=>{if(!['ArrowUp','ArrowDown','Home','End'].includes(e.key))return;e.preventDefault();terminalHeight(e.key==='Home'?130:e.key==='End'?600:Number(terminalHandle.getAttribute('aria-valuenow'))+(e.key==='ArrowUp'?24:-24));};
 function alignMenus(){const title=$('sidebarTitle'),bar=$('appMenuBar'),trigger=bar?.querySelector('.app-menu-trigger');if(!trigger)return;const sidebar=document.querySelector('.sidebar');const x=getComputedStyle(sidebar).display!=='none'?title.getBoundingClientRect().left:railWidth()+16;bar.style.setProperty('--app-menu-inset',Math.max(0,x-parseFloat(getComputedStyle(trigger).paddingLeft))+'px');}
 let dockState='';
 function layout(){const next=[terminal.hidden,history.hidden,document.body.classList.contains('chat-split-open'),document.body.classList.contains('sidebar-collapsed')].join(':');if(next!==dockState){dockState=next;document.body.classList.toggle('terminal-open',!terminal.hidden);historyWidth(Number(historyHandle.getAttribute('aria-valuenow'))||320);terminalHeight(Number(terminalHandle.getAttribute('aria-valuenow'))||280);}alignMenus();}
 new MutationObserver(layout).observe(terminal,{attributes:true,attributeFilter:['hidden']});new MutationObserver(layout).observe(history,{attributes:true,attributeFilter:['hidden']});new MutationObserver(layout).observe(document.body,{attributes:true,attributeFilter:['class']});new ResizeObserver(alignMenus).observe(document.querySelector('.sidebar'));
 window.addEventListener('resize',()=>{dockState='';layout();});document.addEventListener('superteam:language',()=>{historyHandle.setAttribute('aria-label',uiText('调整协作记录宽度','Resize activity panel'));terminalHandle.setAttribute('aria-label',uiText('调整终端高度','Resize terminal'));windowButtons({});});layout();
})();
