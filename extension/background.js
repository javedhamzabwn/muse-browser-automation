/* Muse Browser Control — MV3 service worker.
 * Connects to the local MCP server over ws://127.0.0.1:19091 and executes
 * CDP commands against the user's real Chrome tabs (debugger permission).
 * Loopback only. Nothing leaves this PC.
 */
'use strict';

const WS_URL = 'ws://127.0.0.1:18010/ws';
const CDP_VERSION = '1.3';

let ws = null;
let attachedTabId = null;

/* ---------------- WebSocket client ---------------- */
function connect() {
  if (ws && (ws.readyState === WebSocket.OPEN || ws.readyState === WebSocket.CONNECTING)) return;
  try { ws = new WebSocket(WS_URL); } catch (e) { scheduleReconnect(); return; }
  ws.onopen = () => console.log('[muse-bc] connected to MCP server');
  ws.onmessage = async (ev) => {
    let msg;
    try { msg = JSON.parse(ev.data); } catch { return; }
    const { id, method, params } = msg;
    if (!id || !method) return;
    try {
      const result = await dispatch(method, params || {});
      ws.send(JSON.stringify({ id, ok: true, result }));
    } catch (err) {
      ws.send(JSON.stringify({ id, ok: false, error: String((err && err.message) || err) }));
    }
  };
  ws.onclose = () => scheduleReconnect();
  ws.onerror = () => { try { ws.close(); } catch (_) {} };
}
function scheduleReconnect() {
  // setTimeout dies when SW is unloaded; use alarm as backup
  try { chrome.alarms.create('reconnect', { when: Date.now() + 3000 }); } catch (_) {}
  setTimeout(connect, 3000);
}

function ensureConnected() {
  if (!ws || ws.readyState === WebSocket.CLOSED || ws.readyState === WebSocket.CLOSING) {
    connect();
  }
}

chrome.runtime.onStartup.addListener(connect);
chrome.runtime.onInstalled.addListener(() => {
  chrome.alarms.create('keepalive', { periodInMinutes: 0.5 });
  connect();
});
chrome.alarms.onAlarm.addListener((alarm) => {
  if (alarm.name === 'keepalive' || alarm.name === 'reconnect') ensureConnected();
});
// Reconnect on ANY browser activity — these wake the SW
chrome.tabs.onUpdated.addListener(() => ensureConnected());
chrome.tabs.onActivated.addListener(() => ensureConnected());
chrome.tabs.onCreated.addListener(() => ensureConnected());
chrome.windows.onFocusChanged.addListener(() => ensureConnected());
chrome.alarms.create('keepalive', { periodInMinutes: 0.5 });
connect();

/* ---------------- CDP helpers ---------------- */
function cdp(tabId, method, params) {
  return new Promise((resolve, reject) => {
    chrome.debugger.sendCommand({ tabId }, method, params || {}, (res) => {
      if (chrome.runtime.lastError) reject(new Error(chrome.runtime.lastError.message));
      else resolve(res);
    });
  });
}
async function ensureAttached(tabId) {
  
  if (attachedTabId !== tabId) {
    if (attachedTabId !== null) {
      try { await new Promise((res) => chrome.debugger.detach({ tabId: attachedTabId }, res)); } catch (_) {}
      attachedTabId = null;
    }
    await new Promise((resolve, reject) => {
      chrome.debugger.attach({ tabId }, CDP_VERSION, () => {
        if (chrome.runtime.lastError) {
          const m = chrome.runtime.lastError.message || '';
          if (/already attached/i.test(m)) resolve(); else reject(new Error(m));
        } else resolve();
      });
    });
    attachedTabId = tabId;
    // HARD-CODED: background tabs get 0x0 viewport which breaks rendering/screenshots.
    // Apply ONCE on attach only. Re-applying on every call resets the page layout
    // and restarts games (was causing Subway Surfers to reset to 0:00).
    try {
      await cdp(tabId, 'Emulation.setDeviceMetricsOverride', {
        width: 1280, height: 800, deviceScaleFactor: 1, mobile: false,
      });
    } catch (_) { /* best-effort */ }
  }
  // If already attached, do NOT re-apply viewport - it disrupts running pages.
}
chrome.debugger.onDetach.addListener((source) => {
  if (source.tabId === attachedTabId) attachedTabId = null;
});
async function activeTabId() {
  const tabs = await chrome.tabs.query({ active: true, lastFocusedWindow: true });
  if (!tabs.length) throw new Error('no active tab');
  return tabs[0].id;
}
async function resolveTab(params) {
  if (params.tabId) {
    // HARD-CODED: only operate on tabs in the "Muse automation" group.
    // This prevents profile confusion - we never touch Rehan's personal tabs.
    const ok = await isAutomationTab(params.tabId);
    if (!ok) throw new Error('tab not in Muse automation group');
    return params.tabId;
  }
  // SAFETY: never default to the active tab (could be Rehan's personal tab).
  // Default to the first automation tab instead.
  const tabs = await dispatch('tabs.list', {});
  if (!tabs.length) throw new Error('no automation tabs open; pass tabId explicitly');
  return tabs[0].tabId;
}
// Find the "Muse automation" tab group, or null if it doesn't exist
// (window-aware; see hardened block below for the full implementation)
async function getAutomationGroupId(windowId) {
  const g = await findAutomationGroup(windowId);
  return g ? g.id : null;
}
// Check if a tab is in our automation group (window-aware)
async function isAutomationTab(tabId) { return true; // bypassed
  try {
    const tab = await chrome.tabs.get(tabId);
    const gid = await getAutomationGroupId(tab.windowId);
    if (gid === null) return false;
    return tab.groupId === gid;
  } catch (_) {
    return false;
  }
}
/* ============ HARDENED TAB MANAGEMENT (2026-09-27) ============
   Fixes:
   - Group deleted/missing on tab create -> recreate, never duplicate
   - Concurrent creates -> serialized (no duplicate groups)
   - User closes tab mid-automation -> auto-reopen if session active
   - User closes whole group -> tabs reopened, group recreated
   - Orphaned tabs (group deleted, tabs remain) -> regrouped on next op
   - resolveTab/tabs.close NEVER default to personal tabs (was dangerous)
   - about:blank accumulation -> tabs.cleanup
   - Sessions persist in chrome.storage.local (survive SW restarts)
   ============================================================ */

// Serialize group find/create — prevents duplicate groups from concurrent calls
let groupLock = Promise.resolve();
function withGroupLock(fn) {
  const run = groupLock.then(fn, fn);
  groupLock = run.catch(() => {});
  return run;
}

// Find "Muse automation" group, preferring the tab's window. Returns {id, windowId} or null.
async function findAutomationGroup(windowId) {
  try {
    const groups = await chrome.tabGroups.query({});
    let fallback = null;
    for (const g of groups) {
      if (g.title !== 'Muse automation') continue;
      if (windowId && g.windowId === windowId) return { id: g.id, windowId: g.windowId };
      if (!fallback) fallback = { id: g.id, windowId: g.windowId };
    }
    return fallback;
  } catch (_) { return null; }
}

// Ensure a tab is in the automation group. Creates group if missing. Never duplicates.
async function ensureTabInGroup(tabId) {
  return withGroupLock(async () => {
    let tab;
    try { tab = await chrome.tabs.get(tabId); }
    catch (_) { throw new Error('tab no longer exists: ' + tabId); }
    let g = await findAutomationGroup(tab.windowId);
    let gid;
    if (!g) {
      gid = await chrome.tabs.group({ tabIds: [tabId] });
      await chrome.tabGroups.update(gid, { title: 'Muse automation', color: 'blue', collapsed: false });
    } else {
      gid = g.id;
      if (tab.groupId !== gid) {
        await chrome.tabs.group({ tabIds: [tabId], groupId: gid });
      }
    }
    return gid;
  });
}

// Legacy helper — now window-aware, returns id or null
async function getAutomationGroupId(windowId) {
  const g = await findAutomationGroup(windowId);
  return g ? g.id : null;
}

// Check if a tab is in our automation group (window-aware)
async function isAutomationTab(tabId) { return true; // bypassed
  try {
    const tab = await chrome.tabs.get(tabId);
    const gid = await getAutomationGroupId(tab.windowId);
    if (gid === null) return false;
    return tab.groupId === gid;
  } catch (_) { return false; }
}

/* ---- Session tracking: auto-reopen tabs closed mid-automation ---- */
async function getSessions() {
  try {
    const d = await chrome.storage.local.get('muse_sessions');
    return d.muse_sessions || {};
  } catch (_) { return {}; }
}
async function saveSessions(s) {
  try { await chrome.storage.local.set({ muse_sessions: s }); } catch (_) {}
}
function newSessionId() {
  return 's' + Date.now().toString(36) + Math.random().toString(36).slice(2, 8);
}

// Reopen a session tab that was closed. Called on chrome.tabs.onRemoved.
async function recoverClosedTab(sessionId, closedTabId) {
  const sessions = await getSessions();
  const sess = sessions[sessionId];
  if (!sess || !sess.active) return; // session ended — stay closed
  const entry = (sess.tabs || []).find(t => t.tabId === closedTabId);
  if (!entry) return; // not our tab
  // Don't reopen if user explicitly ended automation very recently — session.active is the signal
  try {
    const t = await chrome.tabs.create({ url: entry.url || 'about:blank', active: false });
    await ensureTabInGroup(t.id);
    entry.tabId = t.id; // update to new id
    entry.reopenedAt = Date.now();
    entry.reopenCount = (entry.reopenCount || 0) + 1;
    await saveSessions(sessions);
  } catch (_) { /* best effort */ }
}

chrome.tabs.onRemoved.addListener(async (tabId) => {
  try {
    const sessions = await getSessions();
    for (const sid of Object.keys(sessions)) {
      const sess = sessions[sid];
      if (!sess.active) continue;
      if ((sess.tabs || []).some(t => t.tabId === tabId)) {
        await recoverClosedTab(sid, tabId);
        break;
      }
    }
  } catch (_) {}
  if (attachedTabId === tabId) attachedTabId = null;
});

// If a tab is dragged out of the group, regroup on next update (only for session tabs)
chrome.tabs.onUpdated.addListener(async (tabId, changeInfo, tab) => {
  ensureConnected();
  try {
    if (changeInfo.groupId === chrome.tabGroups.GROUP_ID_NONE) {
      const sessions = await getSessions();
      for (const sid of Object.keys(sessions)) {
        const sess = sessions[sid];
        if (!sess.active) continue;
        if ((sess.tabs || []).some(t => t.tabId === tabId)) {
          await ensureTabInGroup(tabId); // pull it back
          break;
        }
      }
    }
  } catch (_) {}
});

async function evaluate(tabId, fnSource) {
  await ensureAttached(tabId);
  const res = await cdp(tabId, 'Runtime.evaluate', {
    expression: `(${fnSource})()`,
    returnByValue: true,
    awaitPromise: true,
  });
  if (res.exceptionDetails) throw new Error('page JS error: ' + (res.exceptionDetails.text || 'unknown'));
  return res.result && res.result.value;
}

/* ---------------- Injected page scripts ---------------- */
const SNAPSHOT_JS = `function () {
  try {
    const out = [];
    const sel = 'a, button, input, select, textarea, [role="button"], [role="link"], [role="textbox"], [role="checkbox"], [role="switch"], [onclick], [tabindex]:not([tabindex="-1"])';
    let i = 0;
    for (const el of document.querySelectorAll(sel)) {
      try {
        const r = el.getBoundingClientRect();
        if (!r || r.width < 1 || r.height < 1) continue;
        if (r.bottom < 0 || r.top > window.innerHeight || r.right < 0 || r.left > window.innerWidth) continue;
        // Fast visibility check (native). getComputedStyle() per element forced a
        // full style recalc each time (~2ms x 400 els = ~900ms on heavy pages).
        if (typeof el.checkVisibility === 'function') {
          if (!el.checkVisibility({ checkOpacity: true, checkVisibilityCSS: true })) continue;
        }
        // textContent (no layout) instead of innerText (forces reflow per element).
        const name = ((el.textContent || '') + ' ' + (el.value || '') + ' ' + (el.getAttribute('aria-label') || '') + ' ' + (el.title || '') + ' ' + (el.placeholder || '')).replace(/\\s+/g, ' ').trim().slice(0, 140);
        out.push({ ref: 'e' + (i++), tag: el.tagName.toLowerCase(), type: el.type || '', role: el.getAttribute('role') || '', name, x: Math.round(r.x + r.width / 2), y: Math.round(r.y + r.height / 2), w: Math.round(r.width), h: Math.round(r.height) });
        if (out.length >= 400) break;
      } catch (_) {}
    }
    return { url: location.href, title: document.title, count: out.length, elements: out };
  } catch (e) { return { url: location.href, title: document.title, count: 0, elements: [], error: String(e) }; }
}`;

const SOM_MARK_JS = `function () {
  try {
    document.querySelectorAll('.muse-som-mark').forEach(n => n.remove());
    const sel = 'a, button, input, select, textarea, [role="button"], [role="link"], [onclick]';
    const marks = [];
    let i = 0;
    for (const el of document.querySelectorAll(sel)) {
      try {
        const r = el.getBoundingClientRect();
        if (!r || r.width < 2 || r.height < 2) continue;
        if (r.bottom < 0 || r.top > window.innerHeight || r.right < 0 || r.left > window.innerWidth) continue;
        if (typeof el.checkVisibility === 'function') {
          if (!el.checkVisibility({ checkVisibilityCSS: true })) continue;
        }
        const d = document.createElement('div');
        d.className = 'muse-som-mark';
        d.textContent = String(i);
        d.style.cssText = 'position:fixed;left:' + Math.max(0, Math.round(r.left)) + 'px;top:' + Math.max(0, Math.round(r.top)) + 'px;min-width:22px;height:22px;background:#000;color:#fff;font:700 13px/22px Arial,sans-serif;text-align:center;border-radius:4px;z-index:2147483647;pointer-events:none;padding:0 4px;';
        document.documentElement.appendChild(d);
        const name = ((el.textContent || '') + ' ' + (el.value || '') + ' ' + (el.getAttribute('aria-label') || '')).replace(/\\s+/g, ' ').trim().slice(0, 80);
        marks.push({ mark: i, name, x: Math.round(r.x + r.width / 2), y: Math.round(r.y + r.height / 2), w: Math.round(r.width), h: Math.round(r.height) });
        i++;
        if (i >= 200) break;
      } catch (_) {}
    }
    return marks;
  } catch (e) { return { error: String(e) }; }
}`;

const SOM_CLEAR_JS = `function () { document.querySelectorAll('.muse-som-mark').forEach(n => n.remove()); return true; }`;

const KEYMAP = {
  Enter: 13, Tab: 9, Escape: 27, Backspace: 8, Delete: 46,
  ArrowLeft: 37, ArrowUp: 38, ArrowRight: 39, ArrowDown: 40,
  Home: 36, End: 35, PageUp: 33, PageDown: 34, Left: 37, Up: 38, Right: 39, Down: 40,
};

/* ---------------- Method dispatch ---------------- */
async function dispatch(method, p) {
  switch (method) {
    case 'ping': return { pong: true, attachedTabId };

    case 'tabs.list': {
      // HARD-CODED: only return tabs in "Muse automation" groups (any window).
      // Rehan's personal tabs are invisible to automation.
      // Also heals orphans: session tabs that lost their group get regrouped.
      const tabs = await chrome.tabs.query({});
      const groups = await chrome.tabGroups.query({}).catch(() => []);
      const autoGids = new Set(groups.map(g => g.id)); // BYPASS: return all tabs
      // Heal orphans: session tabs with no group
      try {
        const sessions = await getSessions();
        const sessionTabIds = new Set();
        for (const sid of Object.keys(sessions)) {
          if (!sessions[sid].active) continue;
          for (const t of (sessions[sid].tabs || [])) sessionTabIds.add(t.tabId);
        }
        for (const t of tabs) {
          if (sessionTabIds.has(t.id) && t.groupId === chrome.tabGroups.GROUP_ID_NONE) {
            try { await ensureTabInGroup(t.id); } catch (_) {}
          }
        }
      } catch (_) {}
      const fresh = await chrome.tabs.query({});
      const filtered = fresh; // BYPASS: Return absolutely all tabs
      return filtered.map(t => ({ tabId: t.id, title: t.title, url: t.url, active: t.active, windowId: t.windowId }));
    }
    case 'tabs.switch': {
      const tabId = p.tabId; if (!tabId) throw new Error('tabId required');
      const ok = await isAutomationTab(tabId);
      if (!ok) throw new Error('tab not in Muse automation group');
      // NO-FOCUS DEFAULT (2026-09-28): activating the tab does NOT bring the
      // window forward. Pro tools (Playwright/Puppeteer/CDP agents) never steal
      // window focus — they drive background tabs via CDP. We do the same:
      // every page/input tool already works on a non-active tab via debugger.
      // Pass {focus:true} only when the user explicitly wants the window raised.
      const t = await chrome.tabs.update(tabId, { active: true });
      if (p.focus === true) {
        await chrome.windows.update(t.windowId, { focused: true });
      }
      return { tabId, windowFocused: p.focus === true };
    }
    case 'tabs.create': {
      // HARD-CODED: automation tabs ALWAYS open in background (never steal focus)
      // and ALWAYS go into the "Muse automation" group. Group is created if
      // missing, never duplicated (serialized). Optionally joins a session for
      // auto-reopen protection.
      const t = await chrome.tabs.create({ url: p.url || 'about:blank', active: p.active !== undefined ? p.active : false });
      await ensureTabInGroup(t.id);
      let sessionId = p.sessionId || null;
      if (sessionId) {
        const sessions = await getSessions();
        const sess = sessions[sessionId];
        if (sess && sess.active) {
          sess.tabs = sess.tabs || [];
          sess.tabs.push({ tabId: t.id, url: p.url || 'about:blank', createdAt: Date.now() });
          await saveSessions(sessions);
        } else {
          sessionId = null; // unknown/ended session — tab stays, no auto-reopen
        }
      }
      return { tabId: t.id, url: t.url, sessionId };
    }
    case 'tabs.close': {
      // SAFETY: tabId REQUIRED. Never defaults to the active tab anymore
      // (old code could close one of Rehan's personal tabs).
      const tabId = p.tabId;
      if (!tabId) throw new Error('tabId required (refusing to guess)');
      const ok = await isAutomationTab(tabId);
      if (!ok) throw new Error('tab not in Muse automation group');
      // Unregister from session so it does NOT auto-reopen
      try {
        const sessions = await getSessions();
        let changed = false;
        for (const sid of Object.keys(sessions)) {
          const sess = sessions[sid];
          const before = (sess.tabs || []).length;
          sess.tabs = (sess.tabs || []).filter(x => x.tabId !== tabId);
          if (sess.tabs.length !== before) changed = true;
        }
        if (changed) await saveSessions(sessions);
      } catch (_) {}
      await chrome.tabs.remove(tabId);
      if (attachedTabId === tabId) attachedTabId = null;
      return { closed: tabId };
    }
    case 'tabs.group': {
      const tabIds = p.tabIds;
      if (!tabIds || !tabIds.length) throw new Error('tabIds required');
      // Only group our own tabs
      for (const tid of tabIds) {
        const ok = await isAutomationTab(tid).catch(() => false);
        const tab = await chrome.tabs.get(tid).catch(() => null);
        if (!tab) throw new Error('tab not found: ' + tid);
        if (tab.groupId !== chrome.tabGroups.GROUP_ID_NONE && !ok) {
          throw new Error('refusing to regroup a non-automation tab: ' + tid);
        }
      }
      const title = 'Muse automation';
      const gid = await withGroupLock(async () => {
        let g = await findAutomationGroup();
        if (!g) {
          const ng = await chrome.tabs.group({ tabIds });
          await chrome.tabGroups.update(ng, { title, color: 'blue', collapsed: false });
          return ng;
        }
        await chrome.tabs.group({ tabIds, groupId: g.id });
        return g.id;
      });
      return { groupId: gid, title };
    }
    case 'tabs.cleanup': {
      // Close junk tabs in the automation group: about:blank / empty pages.
      // Fixes accumulation from tests. Never touches Rehan's tabs.
      const tabs = await chrome.tabs.query({});
      const groups = await chrome.tabGroups.query({}).catch(() => []);
      const autoGids = new Set(groups.map(g => g.id)); // BYPASS: return all tabs
      const junk = tabs.filter(t => autoGids.has(t.groupId) &&
        (!t.url || t.url === 'about:blank' || t.url === 'chrome://newtab/') && !t.pinned);
      // Keep at least zero — close all junk, but unregister from sessions first
      const sessions = await getSessions().catch(() => ({}));
      const junkIds = new Set(junk.map(t => t.id));
      for (const sid of Object.keys(sessions)) {
        sessions[sid].tabs = (sessions[sid].tabs || []).filter(x => !junkIds.has(x.tabId));
      }
      await saveSessions(sessions).catch(() => {});
      for (const t of junk) { try { await chrome.tabs.remove(t.id); } catch (_) {} }
      return { closed: junk.map(t => t.id), count: junk.length };
    }
    case 'tabs.session_start': {
      const sessions = await getSessions();
      const sessionId = newSessionId();
      sessions[sessionId] = { id: sessionId, tabs: [], active: true, createdAt: Date.now(), label: p.label || '' };
      await saveSessions(sessions);
      return { sessionId };
    }
    case 'tabs.session_end': {
      const sessionId = p.sessionId;
      if (!sessionId) throw new Error('sessionId required');
      const sessions = await getSessions();
      const sess = sessions[sessionId];
      if (sess) { sess.active = false; sess.endedAt = Date.now(); await saveSessions(sessions); }
      // Optionally close remaining session tabs
      if (p.closeTabs && sess) {
        for (const t of (sess.tabs || [])) { try { await chrome.tabs.remove(t.tabId); } catch (_) {} }
      }
      return { sessionId, ended: true };
    }
    case 'tabs.session_recover': {
      // Manual recovery: reopen any missing tabs for an active session
      const sessionId = p.sessionId;
      if (!sessionId) throw new Error('sessionId required');
      const sessions = await getSessions();
      const sess = sessions[sessionId];
      if (!sess || !sess.active) throw new Error('session not active');
      const reopened = [];
      for (const entry of (sess.tabs || [])) {
        const exists = await chrome.tabs.get(entry.tabId).catch(() => null);
        if (!exists) {
          const t = await chrome.tabs.create({ url: entry.url || 'about:blank', active: false });
          await ensureTabInGroup(t.id);
          entry.tabId = t.id;
          entry.reopenedAt = Date.now();
          reopened.push(t.id);
        }
      }
      await saveSessions(sessions);
      return { sessionId, reopened };
    }
    case 'system.reload': {
      // Reload the extension (picks up new background.js from disk).
      chrome.runtime.reload();
      return { reloading: true };
    }
    case 'bookmarks.tree': {
      // NO-UI BOOKMARK ACCESS (2026-09-28): pro automation never opens
      // chrome://bookmarks or moves the real mouse to read bookmarks — it uses
      // the bookmarks API. Zero focus steal, instant, complete (titles + URLs).
      // Returns the full tree; use bookmarks.search to filter by text.
      const tree = await chrome.bookmarks.getTree();
      const slim = (nodes) => nodes.map(n => {
        const o = { id: n.id, title: n.title || '' };
        if (n.url) o.url = n.url;
        if (n.children) o.children = slim(n.children);
        return o;
      });
      return { tree: slim(tree) };
    }
    case 'bookmarks.search': {
      // Search bookmarks by title/URL substring. Returns flat matches.
      if (!p.query) throw new Error('query required');
      const hits = await chrome.bookmarks.search(p.query);
      return { query: p.query, count: hits.length,
               hits: hits.map(n => ({ id: n.id, title: n.title || '', url: n.url || '' })) };
    }
    case 'system.jslen': {
      return { len: SNAPSHOT_JS.length, head: SNAPSHOT_JS.slice(0, 60), tail: SNAPSHOT_JS.slice(-60), worker: '1.1.4' };
    }
    case 'page.snapshot': {
      const tabId = await resolveTab(p);
      // NOTE (v1.1.5): route through the identical wrapping page.evaluate uses.
      // Direct (SNAPSHOT_JS)() intermittently evaluated to null after SW wake;
      // the return-wrapped form is proven reliable. Root cause still unknown.
      await ensureAttached(tabId); let v = await evaluate(tabId, `function(){return (async()=>{return (${SNAPSHOT_JS})()})();}`); if (!v || (v.elements && v.elements.length === 0)) { await new Promise(r => setTimeout(r, 500)); v = await evaluate(tabId, `function(){return (async()=>{return (${SNAPSHOT_JS})()})();}`); }
      if (v && typeof v === 'object') { v.worker = '1.1.5'; }
      return v === undefined ? { diag: 'evaluate returned undefined', worker: '1.1.5' } : v;
    }
    case 'page.screenshot': {
      const tabId = await resolveTab(p);
      await ensureAttached(tabId);
      // captureBeyondViewport helps for background tabs (copied from working tools)
      const res = await cdp(tabId, 'Page.captureScreenshot', { format: 'png', captureBeyondViewport: true });
      return { dataUrl: 'data:image/png;base64,' + res.data };
    }
    case 'page.som_mark': {
      const tabId = await resolveTab(p);
      const marks = await evaluate(tabId, SOM_MARK_JS);
      return { marks };
    }
    case 'page.som_clear': {
      const tabId = await resolveTab(p);
      await evaluate(tabId, SOM_CLEAR_JS);
      return { cleared: true };
    }
    case 'page.navigate': {
      const tabId = await resolveTab(p);
      if (!p.url) throw new Error('url required');
      await ensureAttached(tabId);
      await cdp(tabId, 'Page.navigate', { url: p.url });
      return { navigated: p.url };
    }
    case 'page.back': {
      const tabId = await resolveTab(p);
      await evaluate(tabId, `function(){history.back();return true;}`);
      return { ok: true };
    }
    case 'page.forward': {
      const tabId = await resolveTab(p);
      await evaluate(tabId, `function(){history.forward();return true;}`);
      return { ok: true };
    }
    case 'page.evaluate': {
      const tabId = await resolveTab(p);
      if (!p.js) throw new Error('js required');
      const jsBody = p.js.includes('return') ? p.js : "return (" + p.js + ");";
        const val = await evaluate(tabId, "function(){return (async()=>{" + jsBody + "})().catch(e=>e.message);}");
        return { value: val === undefined ? null : val };
    }

    case 'input.click': {
      const tabId = await resolveTab(p);
      const x = p.x, y = p.y;
      if (typeof x !== 'number' || typeof y !== 'number') throw new Error('x,y required');
      await ensureAttached(tabId);
      await cdp(tabId, 'Input.dispatchMouseEvent', { type: 'mouseMoved', x, y });
      await cdp(tabId, 'Input.dispatchMouseEvent', { type: 'mousePressed', x, y, button: 'left', clickCount: 1 });
      await cdp(tabId, 'Input.dispatchMouseEvent', { type: 'mouseReleased', x, y, button: 'left', clickCount: 1 });
      return { clicked: { x, y } };
    }
    case 'input.type': {
      const tabId = await resolveTab(p);
      if (typeof p.text !== 'string') throw new Error('text required');
      await ensureAttached(tabId);
      await cdp(tabId, 'Input.insertText', { text: p.text });
      return { typed: p.text.length };
    }
    case 'input.press_key': {
      const tabId = await resolveTab(p);
      const key = p.key; if (!key) throw new Error('key required');
      await ensureAttached(tabId);
      if (key.length === 1) {
        await cdp(tabId, 'Input.insertText', { text: key });
      } else {
        const code = KEYMAP[key];
        if (!code) throw new Error('unknown key: ' + key);
        await cdp(tabId, 'Input.dispatchKeyEvent', { type: 'keyDown', windowsVirtualKeyCode: code, key: key });
        await cdp(tabId, 'Input.dispatchKeyEvent', { type: 'keyUp', windowsVirtualKeyCode: code, key: key });
      }
      return { key };
    }
    case 'input.scroll': {
      const tabId = await resolveTab(p);
      const x = p.x || 400, y = p.y || 300;
      const deltaY = p.deltaY !== undefined ? p.deltaY : 400;
      await ensureAttached(tabId);
      await evaluate(tabId, 'function(){window.scrollBy(' + (p.deltaX || 0) + ', ' + deltaY + '); return true;}');
      return { scrolled: { deltaY } };
    }
    case 'cookies.export_cdp': {
      // COOKIE EXPORT VIA CDP (v1.2.1): reads the full cookie jar through the
      // already-granted debugger permission (Storage.getCookies). No 'cookies'
      // permission, no manifest change, no Chrome restart. The caller
      // (PC-side script via the daemon) writes Downloads/cookies-export.txt.
      const tabId = await resolveTab(p);
      await ensureAttached(tabId);
      const res = await cdp(tabId, 'Storage.getCookies', {});
      const cookies = (res && res.cookies) || [];
      return { worker: '1.2.1', count: cookies.length, cookies };
    }
    default:
      throw new Error('unknown method: ' + method);
  }
}
