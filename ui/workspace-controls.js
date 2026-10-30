'use strict';

// Each split is a separate application document: messages, attachments, in-flight
// sends and drafts stay with that document's own room state.
(() => {
  const isPane = new URLSearchParams(location.search).get('pane') === '1';
  const text = (zh, en) => typeof uiText === 'function' ? uiText(zh, en) : preferences.language === 'en' ? en : zh;
  const settings = category => {
    if (typeof openAppSettings === 'function') openAppSettings(category);
    else openAppearance();
  };
  const notify = (zh, en) => showError(text(zh, en));
  const onError = error => showError(error?.message || String(error));
  const button = (label, cls = '') => {
    const node = el('button', cls, label);
    node.type = 'button';
    return node;
  };
  const originalRenderRooms = renderRooms;
  const originalSwitchView = switchView;

  window.addEventListener('message',event=>{if(!isPane&&event.origin===location.origin&&event.data?.type==='superteam:open-settings')settings(event.data.category||'general');});
  if (isPane) {
    document.documentElement.classList.add('chat-pane-document');
    const report = () => window.parent.postMessage({type: 'superteam:split-status', room: current}, location.origin);
    renderRooms = function (...args) { const result = originalRenderRooms.apply(this, args); report(); return result; };
    window.addEventListener('message', async event => {
      if (event.source !== window.parent || event.origin !== location.origin) return;
      if (event.data?.type === 'superteam:split-room' && state.rooms.some(r => r.id === event.data.room && (!r.visibility || r.visibility === 'visible'))) {
        try { await selectRoom(event.data.room); report(); } catch (error) { onError(error); }
      }
      if (event.data?.type === 'superteam:split-room-settings') $('roomSettings').click();
    });
    window.addEventListener('storage', event => {
      if (event.key !== 'superteam-appearance' || !event.newValue) return;
      try {
        preferences = {...preferences, ...JSON.parse(event.newValue)};
        applyAppearance();
        document.dispatchEvent(new CustomEvent('superteam:language'));
      } catch { /* Ignore incomplete storage writes. */ }
    });
    report();
    return;
  }

  const controls = $('desktopControls');
  document.documentElement.classList.add('has-app-menu');
  controls.hidden = false;
  controls.classList.add('top-window-controls');
  controls.classList.remove('pywebview-drag-region');
  controls.querySelector('.window-drag-space')?.classList.add('pywebview-drag-region');
  document.body.prepend(controls);
  const menuBar = el('nav', 'app-menu-bar');
  menuBar.id = 'appMenuBar';
  menuBar.setAttribute('aria-label', text('应用菜单', 'Application menu'));
  menuBar.setAttribute('role', 'menubar');
  controls.prepend(menuBar);

  let editContext = null;
  let lastEditingTarget = null;
  let openMenu = null;
  let splitRoom = null;
  let splitPane = null;
  let splitFrame = null;
  let splitSelect = null;
  let splitter = null;
  let splitOptionsKey = '';
  let splitWanted = false;
  let lastFrameRoom = null;
  const main = document.querySelector('main');

  function focusContext() {
    let doc = document;
    let target = doc.activeElement;
    if (menuBar.contains(target)) target = lastEditingTarget;
    if (target?.tagName === 'IFRAME') {
      try { doc = target.contentDocument; target = doc.activeElement; } catch { return null; }
    }
    if (!target) return null;
    const isInput = ['TEXTAREA', 'INPUT'].includes(target.tagName) && typeof target.selectionStart === 'number';
    const editable = (isInput || target.isContentEditable) && !target.disabled && !target.readOnly;
    const selection = doc.getSelection();
    return {
      doc, target, isInput, editable,
      start: isInput ? target.selectionStart : null,
      end: isInput ? target.selectionEnd : null,
      range: !isInput && selection?.rangeCount ? selection.getRangeAt(0).cloneRange() : null,
      selected: isInput ? target.value.slice(target.selectionStart, target.selectionEnd) : selection?.toString() || ''
    };
  }

  document.addEventListener('focusin', event => {
    if (!menuBar.contains(event.target)) lastEditingTarget = event.target;
  });

  function restoreEditFocus(ctx) {
    if (!ctx?.target?.isConnected) return false;
    ctx.target.focus({preventScroll: true});
    if (ctx.isInput) ctx.target.setSelectionRange(ctx.start, ctx.end);
    else if (ctx.range) { const selection = ctx.doc.getSelection(); selection.removeAllRanges(); selection.addRange(ctx.range); }
    return true;
  }

  async function edit(command) {
    const ctx = editContext;
    if (!ctx || !restoreEditFocus(ctx)) return;
    if (['undo', 'redo'].includes(command)) {
      if (ctx.editable && !ctx.doc.execCommand(command)) notify('当前输入框没有可执行的' + (command === 'undo' ? '撤销' : '重做') + '操作。', 'No ' + command + ' operation is available in the focused input.');
      return;
    }
    if (command === 'copy' || command === 'cut') {
      if (!ctx.selected || (command === 'cut' && !ctx.editable)) return;
      // Native editing keeps the browser's undo history whenever supported.
      if (ctx.doc.execCommand(command)) return;
      try {
        await navigator.clipboard.writeText(ctx.selected);
        if (command === 'cut') replaceSelection(ctx, '');
      } catch { notify('剪贴板暂不可用，请在输入框中使用 Ctrl+C / Ctrl+X。', 'Clipboard access is unavailable. Use Ctrl+C / Ctrl+X in the input.'); }
      return;
    }
    if (command === 'paste' && ctx.editable) {
      try {
        const value = await navigator.clipboard.readText();
        restoreEditFocus(ctx);
        if (!ctx.doc.execCommand('insertText', false, value)) replaceSelection(ctx, value);
      } catch { notify('剪贴板读取未获浏览器允许，请在输入框中按 Ctrl+V。', 'The browser could not read the clipboard. Press Ctrl+V in the input.'); }
    }
  }

  function replaceSelection(ctx, value) {
    if (ctx.isInput) {
      const max = ctx.target.maxLength;
      if (max > 0) value = value.slice(0, Math.max(0, max - ctx.target.value.length + ctx.end - ctx.start));
      ctx.target.setRangeText(value, ctx.start, ctx.end, 'end');
    } else if (ctx.range) {
      ctx.range.deleteContents();
      const node = ctx.doc.createTextNode(value);
      ctx.range.insertNode(node);
      ctx.range.setStartAfter(node);
      ctx.range.collapse(true);
      const selection = ctx.doc.getSelection();
      selection.removeAllRanges(); selection.addRange(ctx.range);
    }
    const EventType = ctx.doc.defaultView?.Event || Event;
    ctx.target.dispatchEvent(new EventType('input', {bubbles: true}));
  }

  function closeMenus(restore = false) {
    const previous = openMenu;
    for (const item of menuBar.children) {
      item.querySelector('.app-menu-popup').hidden = true;
      item.querySelector('.app-menu-trigger').setAttribute('aria-expanded', 'false');
    }
    openMenu = null;
    if (restore) previous?.querySelector('.app-menu-trigger').focus();
  }

  async function setPreference(key, value) {
    try {
      if (typeof saveAppPreference === 'function') await saveAppPreference(key, value);
      else { preferences[key] = value; applyAppearance(true); }
      if (key === 'font' && typeof autoGrow === 'function') autoGrow();
    } catch (error) { onError(error); }
  }

  function toggleSidebar() {
    document.body.classList.toggle('sidebar-collapsed');
    document.body.classList.remove('sidebar-open');
  }

  async function exportJSON() {
    if (!current) return notify('请先选择一个聊天。', 'Select a chat first.');
    try {
      const result = await api('export-json?id=' + encodeURIComponent(current));
      const url = URL.createObjectURL(new Blob([result.text], {type: 'application/json;charset=utf-8'}));
      const link = el('a'); link.href = url; link.download = result.name; link.click();
      setTimeout(() => URL.revokeObjectURL(url), 2000);
    } catch (error) { onError(error); }
  }

  const importInput = el('input');
  importInput.id = 'menuImportFile'; importInput.type = 'file'; importInput.accept = '.json,application/json'; importInput.hidden = true;
  document.body.append(importInput);
  importInput.onchange = async () => {
    const file = importInput.files?.[0];
    importInput.value = '';
    if (!file) return;
    if (file.size > 20 * 1024 * 1024) return notify('导入文件不能超过 20 MB。', 'Import files must be under 20 MB.');
    try {
      const data = JSON.parse((await file.text()).replace(/^\uFEFF/, ''));
      const result = await api('import-chat', {data});
      await refresh();
      await selectRoom(result.id || result.room?.id || result.room);
      notify('聊天已导入；附件文件需从原工作区另行复制。', 'Chat imported. Attachment files must be copied separately from the original workspace.');
    } catch (error) { onError(error); }
  };

  function helpDialog(kind) {
    let dialog = $('workspaceHelpDialog');
    if (!dialog) { dialog = el('dialog', 'workspace-help-dialog'); dialog.id = 'workspaceHelpDialog'; document.body.append(dialog); }
    dialog.replaceChildren();
    const heading = el('div', 'dialog-title');
    const close = button('', 'icon-button'); close.append(icon('close')); close.setAttribute('aria-label', text('关闭', 'Close')); close.onclick = () => dialog.close();
    heading.append(el('h2', '', text(kind === 'guide' ? '使用指南' : '键盘快捷键', kind === 'guide' ? 'Getting started' : 'Keyboard shortcuts')), close);
    dialog.append(heading);
    if (kind === 'guide') {
      for (const pair of [
        ['新建聊天后选择成员，在输入框中发送任务；默认只让一位擅长者处理，必要时再邀请补充。', 'Create a chat, choose members, and send a task. One suitable member handles the request by default, inviting help only when needed.'],
        ['输入 @ 选择回复成员，输入 # 选择技能，输入 $ 引用其他聊天档案。附件可通过回形针按钮或拖入输入框添加。', 'Use @ for members, # for skills, and $ for chat archives. Attach files using the paperclip or by dragging them into the composer.'],
        ['右上角的分栏按钮可同时打开另一个聊天。两边分别保留消息、草稿和任务状态，拖动中间分隔线调整宽度。', 'The split button opens another chat beside this one. Each pane keeps its own messages, drafts, and task state. Drag the divider to resize.'],
        ['应用偏好在左下角设置中调整；当前聊天的成员、规则和权限在右上角聊天设置中调整。', 'Use the settings button at the lower left for application preferences, and chat settings at the upper right for members, rules, and permissions.']
      ]) dialog.append(el('p', '', text(...pair)));
    } else {
      const keys = preferences.shortcuts || {};
      for (const [zh, en, key] of [['发送消息', 'Send message', keys.send || 'Enter'], ['换行', 'New line', 'Shift+Enter'], ['新建聊天', 'New chat', keys.newChat || 'Ctrl+N'], ['搜索聊天', 'Search chats', keys.search || 'Ctrl+F'], ['打开设置', 'Open settings', keys.settings || 'Ctrl+,'], ['关闭菜单', 'Close menu', 'Esc']]) {
        const row = el('div', 'workspace-shortcut-row'); row.append(el('span', '', text(zh, en)), el('kbd', '', key)); dialog.append(row);
      }
      const configure = button(text('自定义快捷键', 'Customize shortcuts'), 'button secondary');
      configure.onclick = () => { dialog.close(); settings('shortcuts'); }; dialog.append(configure);
    }
    if (!dialog.open) dialog.showModal();
  }

  function menus() {
    closeMenus(); menuBar.replaceChildren();
    menuBar.setAttribute('aria-label', text('应用菜单', 'Application menu'));
    const definitions = [
      ['文件', 'File', [
        ['新建聊天', 'New chat', () => $('newRoom').click(), preferences.shortcuts?.newChat || 'Ctrl+N'],
        ['导入聊天…', 'Import chat…', () => importInput.click()],
        ['导出聊天…', 'Export chat…', exportJSON, '', () => !current],
        null,
        ['打开聊天工作区', 'Open chat workspace', () => $('openWorkspace').click(), '', () => !loaded()],
        ['设置…', 'Settings…', () => settings('general'), preferences.shortcuts?.settings || 'Ctrl+,']
      ]],
      ['编辑', 'Edit', [
        ['撤销', 'Undo', () => edit('undo'), 'Ctrl+Z', () => !editContext?.editable],
        ['重做', 'Redo', () => edit('redo'), 'Ctrl+Y', () => !editContext?.editable],
        null,
        ['剪切', 'Cut', () => edit('cut'), 'Ctrl+X', () => !editContext?.editable || !editContext?.selected],
        ['复制', 'Copy', () => edit('copy'), 'Ctrl+C', () => !editContext?.selected],
        ['粘贴', 'Paste', () => edit('paste'), 'Ctrl+V', () => !editContext?.editable]
      ]],
      ['视图', 'View', [
        ['显示 / 收起聊天列表', 'Toggle chat list', toggleSidebar],
        ['聊天分栏', 'Split chat', toggleSplit, '', () => !current],
        ['终端', 'Terminal', () => typeof toggleTerminalPanel === 'function' ? toggleTerminalPanel() : notify('终端需要桌面应用连接本机服务。', 'The terminal requires the desktop application.')],
        null,
        ['浅色主题', 'Light theme', () => setPreference('theme', 'light')],
        ['深色主题', 'Dark theme', () => setPreference('theme', 'dark')],
        ['跟随系统主题', 'System theme', () => setPreference('theme', 'system')],
        null,
        ['放大文字', 'Larger text', () => setPreference('font', Math.min(24, Number(preferences.font || 16) + 1))],
        ['缩小文字', 'Smaller text', () => setPreference('font', Math.max(14, Number(preferences.font || 16) - 1))],
        ['重置文字大小', 'Reset text size', () => setPreference('font', 16)]
      ]],
      ['帮助', 'Help', [
        ['使用指南', 'Getting started', () => helpDialog('guide')],
        ['键盘快捷键', 'Keyboard shortcuts', () => helpDialog('shortcuts')],
        ['关于 SuperTeam', 'About SuperTeam', () => settings('about')],
        ['开源许可', 'Open-source licenses', () => settings('about')]
      ]]
    ];
    definitions.forEach(([zh, en, entries], index) => {
      const host = el('div', 'app-menu');
      const trigger = button(text(zh, en), 'app-menu-trigger');
      trigger.setAttribute('role', 'menuitem'); trigger.setAttribute('aria-haspopup', 'menu'); trigger.setAttribute('aria-expanded', 'false');
      trigger.id = 'appMenuTrigger' + index;
      const popup = el('div', 'app-menu-popup'); popup.hidden = true; popup.setAttribute('role', 'menu'); popup.setAttribute('aria-labelledby', trigger.id);
      const open = (keyboard = false) => {
        const same = openMenu === host;
        editContext = focusContext() || editContext;
        closeMenus();
        if (same && !keyboard) return;
        for (const item of popup.querySelectorAll('button')) item.disabled = item.unavailable?.() || false;
        popup.hidden = false; trigger.setAttribute('aria-expanded', 'true'); openMenu = host;
        if (keyboard) popup.querySelector('button:not(:disabled)')?.focus();
      };
      trigger.onpointerdown = event => { editContext = focusContext() || editContext; event.preventDefault(); };
      trigger.onclick = () => open();
      trigger.onpointerenter = () => { if (openMenu && openMenu !== host) open(); };
      trigger.onkeydown = event => {
        if (['ArrowDown', 'Enter', ' '].includes(event.key)) { event.preventDefault(); open(true); }
        if (['ArrowLeft', 'ArrowRight'].includes(event.key)) { event.preventDefault(); closeMenus(); menuBar.children[(index + (event.key === 'ArrowRight' ? 1 : 3)) % 4].querySelector('button').focus(); }
      };
      for (const entry of entries) {
        if (!entry) { const separator = el('div', 'app-menu-separator'); separator.setAttribute('role', 'separator'); popup.append(separator); continue; }
        const [label, english, action, shortcut, unavailable] = entry;
        const item = button('', 'app-menu-item'); item.setAttribute('role', 'menuitem');
        item.append(el('span', '', text(label, english)));
        if (shortcut) item.append(el('kbd', '', shortcut));
        item.unavailable = unavailable;
        item.onpointerdown = event => event.preventDefault();
        item.onclick = async () => { closeMenus(); try { await action(); } catch (error) { onError(error); } };
        popup.append(item);
      }
      popup.onkeydown = event => {
        const items = [...popup.querySelectorAll('button')].filter(item => !item.disabled);
        const selected = items.indexOf(document.activeElement);
        if (['ArrowDown', 'ArrowUp', 'Home', 'End'].includes(event.key)) {
          event.preventDefault();
          const at = event.key === 'Home' ? 0 : event.key === 'End' ? items.length - 1 : (selected + (event.key === 'ArrowDown' ? 1 : items.length - 1)) % items.length;
          items[at]?.focus();
        }
        if (['ArrowLeft', 'ArrowRight'].includes(event.key)) { event.preventDefault(); closeMenus(); menuBar.children[(index + (event.key === 'ArrowRight' ? 1 : 3)) % 4].querySelector('button').click(); openMenu?.querySelector('.app-menu-popup button:not(:disabled)')?.focus(); }
        if (event.key === 'Tab') closeMenus();
      };
      host.append(trigger, popup); menuBar.append(host);
    });
  }

  document.addEventListener('pointerdown', event => { if (!menuBar.contains(event.target)) closeMenus(); });
  document.addEventListener('keydown', event => { if (event.key === 'Escape' && openMenu) { event.preventDefault(); event.stopPropagation(); closeMenus(true); } });
  window.addEventListener('blur', () => closeMenus());

  const splitButton = button('', 'icon-button workspace-split-button'); splitButton.id = 'splitChatButton';
  const splitIcon = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
  splitIcon.setAttribute('viewBox', '0 0 24 24'); splitIcon.setAttribute('fill', 'none'); splitIcon.setAttribute('stroke', 'currentColor'); splitIcon.setAttribute('stroke-width', '1.65');
  const splitPath = document.createElementNS(splitIcon.namespaceURI, 'path'); splitPath.setAttribute('d', 'M3 4h18v16H3zM12 4v16'); splitIcon.append(splitPath); splitButton.append(splitIcon);
  document.querySelector('.header-actions').prepend(splitButton);
  splitButton.onclick = toggleSplit;

  function candidates() { return state.rooms.filter(r => r.id !== current && (!r.visibility || r.visibility === 'visible')); }

  function ensureSplit() {
    if (splitPane) return;
    splitPane = el('aside', 'chat-split-pane'); splitPane.id = 'chatSplitPane';
    const toolbar = el('div', 'chat-split-toolbar');
    splitSelect = el('select', 'chat-split-room'); splitSelect.id = 'chatSplitRoom';
    splitSelect.onchange = () => { splitRoom = splitSelect.value; sendSplitRoom(); };
    const roomSettings = button('', 'icon-button'); roomSettings.id = 'splitRoomSettings'; roomSettings.append(icon('sliders')); roomSettings.onclick = () => splitFrame.contentWindow?.postMessage({type: 'superteam:split-room-settings'}, location.origin);
    const close = button('', 'icon-button'); close.id = 'closeChatSplit'; close.append(icon('close')); close.onclick = closeSplit;
    toolbar.append(splitSelect, roomSettings, close);
    splitFrame = el('iframe', 'chat-split-frame'); splitFrame.id = 'chatSplitFrame';
    splitFrame.onload = () => {
      lastFrameRoom = new URL(splitFrame.src, location.origin).searchParams.get('room');
      sendSplitRoom();
    };
    splitPane.append(toolbar, splitFrame);
    splitter = el('div', 'chat-split-divider'); splitter.id = 'chatSplitDivider'; splitter.tabIndex = 0;
    splitter.setAttribute('role', 'separator'); splitter.setAttribute('aria-orientation', 'vertical'); splitter.setAttribute('aria-valuemin', '25'); splitter.setAttribute('aria-valuemax', '75');
    main.append(splitter, splitPane);
    let pointer = null;
    const setWidth = percentage => {
      const width=main.getBoundingClientRect().width-6;
      const minimum=Math.min(220,Math.max(100,width/2-10));
      const low=minimum/Math.max(1,width)*100,high=100-low;
      const value = Math.max(low, Math.min(high, percentage));
      splitter.setAttribute('aria-valuemin',String(Math.round(low)));splitter.setAttribute('aria-valuemax',String(Math.round(high)));
      main.style.setProperty('--chat-primary-width', value + '%'); splitter.setAttribute('aria-valuenow', String(Math.round(value)));
    };
    setWidth(50);
    splitter.onpointerdown = event => { if (event.button !== 0) return; pointer = event.pointerId; splitter.setPointerCapture(event.pointerId); document.body.classList.add('split-resizing'); event.preventDefault(); };
    splitter.onpointermove = event => { if (pointer !== event.pointerId) return; const rect = main.getBoundingClientRect(); setWidth((event.clientX - rect.left) / rect.width * 100); };
    splitter.onpointerup = splitter.onpointercancel = splitter.onlostpointercapture = () => { pointer = null; document.body.classList.remove('split-resizing'); };
    splitter.onkeydown = event => { if (['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(event.key)) { event.preventDefault(); const currentWidth = Number(splitter.getAttribute('aria-valuenow')) || 50; setWidth(event.key === 'Home' ? 25 : event.key === 'End' ? 75 : currentWidth + (event.key === 'ArrowRight' ? 5 : -5)); } };
  }

  function sendSplitRoom() {
    if (!splitFrame || !splitRoom || lastFrameRoom === splitRoom) return;
    splitFrame.contentWindow?.postMessage({type: 'superteam:split-room', room: splitRoom}, location.origin);
    lastFrameRoom = splitRoom;
  }

  function closeSplit() {
    splitWanted = false;
    document.body.classList.remove('chat-split-open', 'split-resizing');
    if (splitPane) splitPane.hidden = true;
    if (splitter) splitter.hidden = true;
    splitButton.setAttribute('aria-pressed', 'false');
    // Keep the hidden document alive, including unsent attachments and drafts.
  }

  function toggleSplit() {
    if (splitWanted) { closeSplit(); return; }
    const rooms = candidates();
    if (!rooms.length) { notify('需要另一个聊天才能分栏，请先新建聊天。', 'Create another chat before opening a split pane.'); return; }
    ensureSplit();
    splitWanted = true;
    if (!rooms.some(r => r.id === splitRoom)) splitRoom = rooms[0].id;
    if (!splitFrame.src) {
      const url = new URL('/', location.origin); url.searchParams.set('pane', '1'); url.searchParams.set('room', splitRoom); url.hash = token;
      lastFrameRoom = splitRoom; splitFrame.src = url.href;
    }
    updateControls();
  }

  function updateControls() {
    splitButton.title = text('聊天分栏', 'Split chat'); splitButton.setAttribute('aria-label', splitButton.title);
    splitButton.setAttribute('aria-pressed', String(splitWanted));
    if (!splitWanted) return;
    const rooms = candidates();
    if (!rooms.length) { closeSplit(); return; }
    if (!rooms.some(r => r.id === splitRoom)) splitRoom = rooms[0].id;
    const key = JSON.stringify(rooms.map(r => [r.id, r.name]));
    if (key !== splitOptionsKey) {
      splitOptionsKey = key;
      splitSelect.replaceChildren();
      for (const roomOption of rooms) { const option = el('option', '', roomOption.name); option.value = roomOption.id; splitSelect.append(option); }
    }
    splitSelect.value = splitRoom;
    splitSelect.setAttribute('aria-label', text('右侧聊天', 'Right chat'));
    splitFrame.title = text('独立聊天分栏', 'Independent chat pane');
    splitter.setAttribute('aria-label', text('调整聊天分栏宽度', 'Resize chat panes'));
    $('closeChatSplit').title = text('关闭分栏', 'Close split'); $('closeChatSplit').setAttribute('aria-label', $('closeChatSplit').title);
    $('splitRoomSettings').title = text('右侧聊天设置', 'Right chat settings'); $('splitRoomSettings').setAttribute('aria-label', $('splitRoomSettings').title);
    const visible = view === 'chat' && !document.body.classList.contains('settings-open');
    splitPane.hidden = !visible; splitter.hidden = !visible;
    if(document.body.classList.contains('chat-split-open')!==visible)document.body.classList.toggle('chat-split-open', visible);
    sendSplitRoom();
  }

  renderRooms = function (...args) { const result = originalRenderRooms.apply(this, args); updateControls(); return result; };
  switchView = function (...args) { const result = originalSwitchView.apply(this, args); updateControls(); return result; };
  new MutationObserver(updateControls).observe(document.body, {attributes: true, attributeFilter: ['class']});
  window.addEventListener('message', event => {
    if (event.origin !== location.origin || event.source !== splitFrame?.contentWindow || event.data?.type !== 'superteam:split-status') return;
    // A delayed report from the previous room must not overwrite a more recent
    // selector change. The parent is the authority for the pane's destination.
    if (event.data.room !== splitRoom) { lastFrameRoom = null; updateControls(); }
    else lastFrameRoom = splitRoom;
  });
  document.addEventListener('superteam:language', () => { menus(); updateControls(); });
  window.toggleChatSplit = toggleSplit;
  window.closeChatSplit = closeSplit;
  window.updateWorkspaceControls = updateControls;
  menus(); updateControls();
})();
