(() => {
'use strict';

const SCRIPT_VERSION = '1.1.0';
const CLICK_COOLDOWN_MS = 1200;
const POLL_INTERVAL_MS = 1000;
const POST_CLICK_CHECK_DELAY_MS = 350;
const MAX_RETRY_ATTEMPTS = 3;
const LABEL_KEYWORDS = [
'skip',
'skip ad',
'skip ads',
'\u5e83\u544a\u3092\u30b9\u30ad\u30c3\u30d7',
'\u30b9\u30ad\u30c3\u30d7'
];
const EXCLUDED_LABEL_KEYWORDS = [
'navigation',
'\u30ca\u30d3\u30b2\u30fc\u30b7\u30e7\u30f3'
];
const BUTTON_SELECTORS = [
'.ytp-ad-skip-button',
'.ytp-ad-skip-button-modern',
'button.ytp-skip-ad-button',
'button[class*="skip"]',
'button[aria-label]'
];

let lastClickAt = 0;
let retryCount = 0;
const clickedButtons = new WeakSet();

function normalizeText(value) {
return (value || '').trim().toLowerCase();
}

function isVisible(element) {
if (!element || !element.isConnected) return false;

const style = window.getComputedStyle(element);
if (
style.display === 'none' ||
style.visibility === 'hidden' ||
style.pointerEvents === 'none' ||
style.opacity === '0'
) {
return false;
}

const rect = element.getBoundingClientRect();
return rect.width > 0 && rect.height > 0;
}

function isTopMostAtCenter(element) {
if (!element) return false;

const rect = element.getBoundingClientRect();
if (rect.width <= 0 || rect.height <= 0) return false;

const clientX = Math.min(
Math.max(rect.left + rect.width / 2, 0),
window.innerWidth - 1
);
const clientY = Math.min(
Math.max(rect.top + rect.height / 2, 0),
window.innerHeight - 1
);
const topElement = document.elementFromPoint(clientX, clientY);

return Boolean(
topElement &&
(topElement === element ||
element.contains(topElement) ||
topElement.contains(element))
);
}

function isEnabled(button) {
if (!button) return false;

return (
button.disabled !== true &&
button.getAttribute('disabled') === null &&
button.getAttribute('aria-disabled') !== 'true'
);
}

function matchesSkipButton(button) {
if (!button || button.tagName !== 'BUTTON') return false;

const label = normalizeText(
button.getAttribute('aria-label') ||
button.getAttribute('title') ||
button.textContent
);

if (EXCLUDED_LABEL_KEYWORDS.some((keyword) => label.includes(keyword))) {
return false;
}

if (
button.classList.contains('ytp-skip-ad-button') ||
button.classList.contains('ytp-ad-skip-button') ||
button.classList.contains('ytp-ad-skip-button-modern')
) {
return true;
}

return LABEL_KEYWORDS.some((keyword) => label.includes(keyword));
}

function getCandidateButtons() {
const buttons = new Set();

for (const selector of BUTTON_SELECTORS) {
for (const element of document.querySelectorAll(selector)) {
if (element instanceof HTMLButtonElement) {
buttons.add(element);
}
}
}

return [...buttons];
}

function findSkipButton() {
for (const button of getCandidateButtons()) {
if (!matchesSkipButton(button)) continue;
if (!isVisible(button) || !isEnabled(button) || !isTopMostAtCenter(button)) continue;
return button;
}

return null;
}

function getMoviePlayer() {
const player = document.getElementById('movie_player');
return player instanceof HTMLElement ? player : null;
}

function isAdShowing() {
const player = getMoviePlayer();
if (player?.classList.contains('ad-showing')) {
return true;
}

return Boolean(
document.querySelector('.video-ads.ytp-ad-module') ||
document.querySelector('.ytp-ad-player-overlay') ||
document.querySelector('.ytp-ad-skip-button') ||
document.querySelector('.ytp-ad-skip-button-modern') ||
document.querySelector('.ytp-skip-ad-button')
);
}

function dispatchMouseSequence(button) {
const rect = button.getBoundingClientRect();
const clientX = rect.left + rect.width / 2;
const clientY = rect.top + rect.height / 2;
const eventInit = {
bubbles: true,
cancelable: true,
composed: true,
view: window,
clientX,
clientY,
button: 0
};

button.dispatchEvent(new PointerEvent('pointerdown', eventInit));
button.dispatchEvent(new MouseEvent('mousedown', eventInit));
button.dispatchEvent(new PointerEvent('pointerup', eventInit));
button.dispatchEvent(new MouseEvent('mouseup', eventInit));
button.dispatchEvent(new MouseEvent('click', eventInit));
}

function getButtonCenter(button) {
const rect = button.getBoundingClientRect();
return {
x: Math.round(rect.left + rect.width / 2),
y: Math.round(rect.top + rect.height / 2)
};
}

async function requestRealClick(button) {
const center = getButtonCenter(button);

return chrome.runtime.sendMessage({
type: 'AUTO_SKIP_REAL_CLICK',
...center
});
}

async function tryActivate(button) {
if (!button) return false;

try {
const response = await requestRealClick(button);
if (response?.ok) {
return true;
}

dispatchMouseSequence(button);
if (document.activeElement !== button) {
button.focus({ preventScroll: true });
}
button.click();
clickedButtons.add(button);
return true;
} catch (error) {
console.warn('[YouTube Auto Skip] click failed', error);
return false;
}
}

function verifySkipSuccess(reason) {
window.setTimeout(() => {
if (!isAdShowing()) {
retryCount = 0;
console.log('[YouTube Auto Skip] ad cleared after', reason);
return;
}

if (retryCount >= MAX_RETRY_ATTEMPTS) {
console.log('[YouTube Auto Skip] ad still showing after retries');
retryCount = 0;
return;
}

retryCount += 1;
const retryButton = findSkipButton();

if (!retryButton) {
console.log('[YouTube Auto Skip] ad still showing but no skip button found');
return;
}

clickedButtons.delete(retryButton);
lastClickAt = 0;
clickSkipButton(`retry-${retryCount}`);
}, POST_CLICK_CHECK_DELAY_MS);
}

async function clickSkipButton(reason) {
const now = Date.now();
if (now - lastClickAt < CLICK_COOLDOWN_MS) return;

const button = findSkipButton();
if (!button) return;

if (await tryActivate(button)) {
lastClickAt = now;
console.log(`[YouTube Auto Skip ${SCRIPT_VERSION}] clicked skip button via`, reason, button);
verifySkipSuccess(reason);
}
}

function scheduleCheck(reason) {
window.requestAnimationFrame(() => clickSkipButton(reason));
}

const observer = new MutationObserver((mutations) => {
for (const mutation of mutations) {
if (mutation.type === 'childList' && mutation.addedNodes.length > 0) {
scheduleCheck('mutation');
return;
}

if (
mutation.type === 'attributes' &&
mutation.target instanceof HTMLButtonElement
) {
scheduleCheck('attribute');
return;
}
}
});

observer.observe(document.documentElement, {
childList: true,
subtree: true,
attributes: true,
attributeFilter: ['aria-label', 'aria-disabled', 'class', 'style']
});

window.addEventListener('yt-navigate-finish', () => scheduleCheck('yt-navigation'));
window.addEventListener('popstate', () => scheduleCheck('popstate'));
document.addEventListener(
'visibilitychange',
() => {
if (document.visibilityState === 'visible') {
scheduleCheck('visibilitychange');
}
},
{ passive: true }
);

window.setInterval(() => clickSkipButton('interval'), POLL_INTERVAL_MS);
scheduleCheck('startup');

console.log(`[YouTube Auto Skip ${SCRIPT_VERSION}] ready`);
})();