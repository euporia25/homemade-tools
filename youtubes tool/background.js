const DEBUGGER_VERSION = '1.3';
const attachedTabs = new Set();

function getDebuggerTarget(tabId) {
return { tabId };
}

async function attachDebugger(tabId) {
if (attachedTabs.has(tabId)) return;

await chrome.debugger.attach(getDebuggerTarget(tabId), DEBUGGER_VERSION);
attachedTabs.add(tabId);
}

async function detachDebugger(tabId) {
if (!attachedTabs.has(tabId)) return;

try {
await chrome.debugger.detach(getDebuggerTarget(tabId));
} catch (error) {
console.warn('[YouTube Auto Skip] debugger detach failed', error);
} finally {
attachedTabs.delete(tabId);
}
}

async function dispatchMouseClick(tabId, x, y) {
await attachDebugger(tabId);

const target = getDebuggerTarget(tabId);
const baseParams = {
x,
y,
button: 'left',
buttons: 1,
clickCount: 1,
pointerType: 'mouse'
};

await chrome.debugger.sendCommand(target, 'Input.dispatchMouseEvent', {
...baseParams,
type: 'mouseMoved'
});
await chrome.debugger.sendCommand(target, 'Input.dispatchMouseEvent', {
...baseParams,
type: 'mousePressed'
});
await chrome.debugger.sendCommand(target, 'Input.dispatchMouseEvent', {
...baseParams,
type: 'mouseReleased',
buttons: 0
});
}

chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
if (message?.type !== 'AUTO_SKIP_REAL_CLICK') {
return false;
}

const tabId = sender.tab?.id;
if (typeof tabId !== 'number') {
sendResponse({ ok: false, error: 'missing-tab-id' });
return false;
}

(async () => {
try {
await dispatchMouseClick(tabId, message.x, message.y);
sendResponse({ ok: true });
} catch (error) {
console.warn('[YouTube Auto Skip] debugger click failed', error);
sendResponse({ ok: false, error: String(error) });
}
})();

return true;
});

chrome.tabs.onRemoved.addListener((tabId) => {
detachDebugger(tabId);
});

chrome.debugger.onDetach.addListener((source) => {
if (typeof source.tabId === 'number') {
attachedTabs.delete(source.tabId);
}
});