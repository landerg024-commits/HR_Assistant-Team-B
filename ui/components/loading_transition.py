"""Browser-only loading feedback for Streamlit UI transitions.

This is deliberately presentation-only. It never reads or stores user inputs,
company data, chat text, or authentication state. The parent-DOM controller is
installed once per browser tab and survives ordinary Streamlit reruns; each
completed page sends an explicit readiness signal.

The very first browser paint is managed by native Streamlit/theme settings:
app Python cannot execute before the browser has loaded Streamlit itself.
"""

from __future__ import annotations

from ui.components.browser_bridge import render_browser_bridge


_LOADING_TRANSITION_SCRIPT = r"""
<script>
(() => {
    const host = window.parent;
    const doc = host.document;
    const key = "__aiHrLoadingTransitionController";
    const version = 238;
    const old = host[key];
    if (old && old.version === version && typeof old.refresh === "function") {
        old.refresh();
        return;
    }
    // Older browser controllers can survive a code upgrade in the same tab.
    // Replace them to activate updated coverage without duplicated listeners.
    old?.dispose?.();

    // Maintain the loading UI outside the Streamlit root: React may replace
    // the root's descendants while rerendering a module.
    const styleId = "ai-hr-loading-transition-style";
    const overlayId = "ai-hr-loading-transition";
    const css = `
        /* Fill ONLY the main page workspace. Never wash out the sidebar or
           fixed portal banner. Position is recomputed from live geometry. */
        #${overlayId} {
            position: fixed; inset: 0 0 0 0;
            display: block; overflow: hidden;
            box-sizing: border-box;
            background: #F7F9FC; color: #10172A;
            z-index: 8850;
            visibility: hidden; opacity: 0; pointer-events: none;
            transition: opacity 130ms ease, visibility 130ms ease;
        }
        #${overlayId}.ai-hr-loading-visible {
            visibility: visible; opacity: 1;
        }
        #${overlayId} .ai-hr-loading-workspace {
            height: 100%; box-sizing: border-box;
            width: 100%; max-width: 1540px;
            padding: clamp(1rem, 2.2vw, 2.25rem);
            margin: 0 auto;
        }
        #${overlayId} .ai-hr-loading-heading {
            display: flex; gap: .75rem; align-items: center;
            font: 600 15px/1.5 sans-serif;
            margin: 0 0 2rem;
            color: #273853;
        }
        #${overlayId} .ai-hr-loading-ring {
            height: 22px; width: 22px; border-radius: 50%;
            border: 3px solid #DBE5F1; border-top-color: #496DB0;
            animation: aiHrLoadSpin .9s linear infinite;
            flex-shrink: 0;
        }
        #${overlayId} .ai-hr-loading-skeleton {
            border-radius: 8px; background: #E8EDF5;
            background-image: linear-gradient(95deg, transparent 20%, #F8FAFD 47%, transparent 75%);
            background-size: 225% 100%;
            animation: aiHrLoadShimmer 1.35s ease-in-out infinite;
        }
        #${overlayId} .ai-hr-loading-title {
            height: 23px; width: min(420px, 70%); margin-bottom: 14px;
        }
        #${overlayId} .ai-hr-loading-description {
            height: 13px; width: min(610px, 90%); margin-bottom: 25px;
        }
        #${overlayId} .ai-hr-loading-metrics {
            display: grid; grid-template-columns: repeat(3,minmax(0,1fr));
            gap: 16px; margin-bottom: 20px;
        }
        #${overlayId} .ai-hr-loading-metric {
            min-height: 96px; border: 1px solid #E5EAF1;
            border-radius: 14px; background: #FFFFFF;
            box-sizing: border-box; padding: 20px;
        }
        #${overlayId} .ai-hr-loading-metric .ai-hr-loading-skeleton:first-child {
            height: 13px; width: 58%; margin-bottom: 14px;
        }
        #${overlayId} .ai-hr-loading-metric .ai-hr-loading-skeleton:last-child {
            height: 21px; width: 38%;
        }
        #${overlayId} .ai-hr-loading-columns {
            display: grid; grid-template-columns: minmax(0, 1.75fr) minmax(0, 1fr);
            gap: 18px;
        }
        #${overlayId} .ai-hr-loading-panel {
            background: #FFFFFF; border: 1px solid #E5EAF1;
            border-radius: 14px; padding: clamp(16px,2vw,24px);
            min-height: 300px; box-sizing: border-box;
        }
        #${overlayId} .ai-hr-loading-panel-title {
            height: 17px; width: 45%; margin-bottom: 24px;
        }
        #${overlayId} .ai-hr-loading-row {
            height: 13px; margin-bottom: 19px;
        }
        #${overlayId} .ai-hr-loading-row:nth-child(2n) { width: 92%; }
        #${overlayId} .ai-hr-loading-row:nth-child(3n) { width: 76%; }
        #${overlayId} .ai-hr-loading-row:nth-child(4n) { width: 84%; }
        #${overlayId} .ai-hr-loading-panel-short {
            min-height: 160px; margin-bottom: 18px;
        }
        #${overlayId} .ai-hr-loading-panel-short .ai-hr-loading-row {
            margin-bottom: 16px;
        }
        /* A second stage is scoped to horizontal-tab CONTENT, not the
           sidebar, sticky banner or the native tab button row. */
        #ai-hr-horizontal-tab-loading {
            position: fixed; display: block;
            box-sizing: border-box; overflow: hidden;
            z-index: 8849; border: 1px solid #E5EAF1;
            border-radius: 12px; background: #F7F9FC;
            color: #273853; visibility: hidden; opacity: 0;
            pointer-events: none;
            transition: opacity 100ms ease, visibility 100ms ease;
        }
        #ai-hr-horizontal-tab-loading.ai-hr-loading-visible {
            visibility: visible; opacity: 1;
        }
        #ai-hr-horizontal-tab-loading .ai-hr-tab-content {
            box-sizing: border-box; width: 100%; padding: 22px;
        }
        #ai-hr-horizontal-tab-loading .ai-hr-loading-ring {
            height: 20px; width: 20px; border-radius: 50%;
            border: 3px solid #DBE5F1; border-top-color: #496DB0;
            animation: aiHrLoadSpin .9s linear infinite;
            flex-shrink: 0;
        }
        #ai-hr-horizontal-tab-loading .ai-hr-tab-heading {
            display: flex; align-items: center; gap: 11px;
            font: 600 14px/1.5 sans-serif; margin-bottom: 20px;
        }
        #ai-hr-horizontal-tab-loading .ai-hr-tab-skeleton {
            border-radius: 7px; height: 14px; margin-bottom: 15px;
            background: #E8EDF5;
            background-image: linear-gradient(95deg, transparent 20%, #F8FAFD 47%, transparent 75%);
            background-size: 225% 100%;
            animation: aiHrLoadShimmer 1.35s ease-in-out infinite;
        }
        #ai-hr-horizontal-tab-loading .ai-hr-tab-skeleton:nth-child(2n) { width: 82%; }
        #ai-hr-horizontal-tab-loading .ai-hr-tab-skeleton:nth-child(3n) { width: 64%; }
        #ai-hr-horizontal-tab-loading .ai-hr-tab-placeholder {
            height: 110px; margin-top: 20px; border-radius: 10px;
            border: 1px solid #E5EAF1; background: #FFFFFF; padding: 18px;
        }
        #ai-hr-horizontal-tab-loading .ai-hr-tab-placeholder .ai-hr-tab-skeleton {
            width: 90%; height: 13px;
        }
        @keyframes aiHrLoadSpin { to { transform: rotate(360deg); } }
        @keyframes aiHrLoadShimmer { to { background-position-x: -225%; } }
        @media (max-width: 940px) {
            #${overlayId} .ai-hr-loading-metrics { gap: 10px; }
            #${overlayId} .ai-hr-loading-columns { grid-template-columns: 1fr; }
            #${overlayId} .ai-hr-loading-panel-short { min-height: 130px; }
        }
        @media (max-width: 520px) {
            #${overlayId} .ai-hr-loading-workspace { padding: 1rem; }
            #${overlayId} .ai-hr-loading-metrics { grid-template-columns: repeat(2,minmax(0,1fr)); }
            #${overlayId} .ai-hr-loading-metric:last-child { display: none; }
        }
        @media (prefers-reduced-motion: reduce) {
            #${overlayId}, #${overlayId} *,
            #ai-hr-horizontal-tab-loading, #ai-hr-horizontal-tab-loading * {
                transition: none !important; animation: none !important;
            }
        }
    `;
    let style = doc.getElementById(styleId);
    if (!style) {
        style = doc.createElement("style");
        style.id = styleId;
        doc.head.appendChild(style);
    }
    style.textContent = css;

    let overlay = doc.getElementById(overlayId);
    if (!overlay) {
        overlay = doc.createElement("div");
        overlay.id = overlayId;
        overlay.setAttribute("role", "status");
        overlay.setAttribute("aria-live", "polite");
        overlay.setAttribute("aria-hidden", "true");
        overlay.innerHTML = `
            <div class="ai-hr-loading-workspace">
                <div class="ai-hr-loading-heading">
                    <span class="ai-hr-loading-ring" aria-hidden="true"></span>
                    <span>Loading workspace…</span>
                </div>
                <div class="ai-hr-loading-skeleton ai-hr-loading-title"></div>
                <div class="ai-hr-loading-skeleton ai-hr-loading-description"></div>
                <div class="ai-hr-loading-metrics" aria-hidden="true">
                    <div class="ai-hr-loading-metric"><div class="ai-hr-loading-skeleton"></div><div class="ai-hr-loading-skeleton"></div></div>
                    <div class="ai-hr-loading-metric"><div class="ai-hr-loading-skeleton"></div><div class="ai-hr-loading-skeleton"></div></div>
                    <div class="ai-hr-loading-metric"><div class="ai-hr-loading-skeleton"></div><div class="ai-hr-loading-skeleton"></div></div>
                </div>
                <div class="ai-hr-loading-columns" aria-hidden="true">
                    <div class="ai-hr-loading-panel">
                        <div class="ai-hr-loading-skeleton ai-hr-loading-panel-title"></div>
                        <div class="ai-hr-loading-skeleton ai-hr-loading-row"></div>
                        <div class="ai-hr-loading-skeleton ai-hr-loading-row"></div>
                        <div class="ai-hr-loading-skeleton ai-hr-loading-row"></div>
                        <div class="ai-hr-loading-skeleton ai-hr-loading-row"></div>
                        <div class="ai-hr-loading-skeleton ai-hr-loading-row"></div>
                    </div>
                    <div>
                        <div class="ai-hr-loading-panel ai-hr-loading-panel-short">
                            <div class="ai-hr-loading-skeleton ai-hr-loading-panel-title"></div>
                            <div class="ai-hr-loading-skeleton ai-hr-loading-row"></div>
                            <div class="ai-hr-loading-skeleton ai-hr-loading-row"></div>
                        </div>
                        <div class="ai-hr-loading-panel ai-hr-loading-panel-short">
                            <div class="ai-hr-loading-skeleton ai-hr-loading-panel-title"></div>
                            <div class="ai-hr-loading-skeleton ai-hr-loading-row"></div>
                            <div class="ai-hr-loading-skeleton ai-hr-loading-row"></div>
                        </div>
                    </div>
                </div>
            </div>`;
        doc.body.appendChild(overlay);
    }

    // Native Streamlit tabs remain visible and interactive.  Only their
    // content panel receives a scoped fallback if a tab switch takes time.
    const tabOverlayId = "ai-hr-horizontal-tab-loading";
    let tabOverlay = doc.getElementById(tabOverlayId);
    if (!tabOverlay) {
        tabOverlay = doc.createElement("div");
        tabOverlay.id = tabOverlayId;
        tabOverlay.setAttribute("role", "status");
        tabOverlay.setAttribute("aria-live", "polite");
        tabOverlay.setAttribute("aria-hidden", "true");
        tabOverlay.innerHTML = `
            <div class="ai-hr-tab-content">
                <div class="ai-hr-tab-heading">
                    <span class="ai-hr-loading-ring" aria-hidden="true"></span>
                    <span>Loading tab…</span>
                </div>
                <div class="ai-hr-tab-skeleton"></div>
                <div class="ai-hr-tab-skeleton"></div>
                <div class="ai-hr-tab-placeholder">
                    <div class="ai-hr-tab-skeleton"></div>
                    <div class="ai-hr-tab-skeleton"></div>
                    <div class="ai-hr-tab-skeleton"></div>
                </div>
            </div>`;
        doc.body.appendChild(tabOverlay);
    }
    let tabRoot = null;
    let tabBar = null;
    let tabButton = null;
    let tabKind = null;
    let tabShowTimer = null;
    let tabReadyTimer = null;
    let tabIdleTimer = null;
    let tabSafetyTimer = null;
    let tabPending = false;
    const clearTabTimers = () => {
        host.clearTimeout(tabShowTimer);
        host.clearTimeout(tabReadyTimer);
        host.clearTimeout(tabIdleTimer);
        host.clearTimeout(tabSafetyTimer);
        tabShowTimer = tabReadyTimer = tabIdleTimer = tabSafetyTimer = null;
    };
    const hideTab = () => {
        clearTabTimers();
        tabPending = false;
        tabRoot = tabBar = tabButton = tabKind = null;
        tabOverlay.classList.remove("ai-hr-loading-visible");
        tabOverlay.setAttribute("aria-hidden", "true");
    };
    const rectIfVisible = (element) => {
        if (!element) return null;
        const rect = element.getBoundingClientRect?.();
        if (!rect || rect.width <= 0 || rect.height <= 0) return null;
        const computed = host.getComputedStyle(element);
        return computed.display !== "none" && computed.visibility !== "hidden"
            ? rect : null;
    };
    const placeTab = () => {
        if (!tabPending) return;
        const bar = rectIfVisible(tabBar);
        if (!bar) return;
        const main = rectIfVisible(doc.querySelector('[data-testid="stMain"]'));
        const side = rectIfVisible(doc.querySelector('[data-testid="stSidebar"]'));
        const left = Math.max(bar.left, main?.left || 0, side?.right || 0);
        const viewportWidth = host.innerWidth || doc.documentElement?.clientWidth || 1280;
        const viewportHeight = host.innerHeight || doc.documentElement?.clientHeight || 800;
        const rootRect = rectIfVisible(tabRoot);
        // Native tab lists can be narrower than their content container.
        // Cover the full tab PANEL width, not just the button labels.
        const contentRight = tabKind === "native"
            ? Math.max(bar.right, rootRect?.right || 0)
            : Math.max(bar.right, main?.right || 0);
        const right = Math.min(viewportWidth - 8, contentRight);
        const top = bar.bottom + 5;
        const available = Math.max(0, viewportHeight - top - 12);
        const rootHeight = rootRect ? rootRect.bottom - top : available;
        const height = Math.min(available, Math.max(220, Math.min(650, rootHeight)));
        if (right <= left || available < 90) return;
        tabOverlay.style.left = `${Math.round(left)}px`;
        tabOverlay.style.top = `${Math.round(top)}px`;
        tabOverlay.style.width = `${Math.round(right - left)}px`;
        tabOverlay.style.height = `${Math.round(height)}px`;
    };
    // No production data, tab labels or question text are saved by the
    // controller. Only native tab/control state is checked in the browser.
    const tabContentReady = () => {
        if (!tabPending || !tabRoot) return false;
        if (tabRoot.isConnected === false) return false;
        if (tabKind === "segmented") {
            const pressed = tabButton?.getAttribute?.("aria-pressed") === "true" ||
                            tabButton?.getAttribute?.("aria-checked") === "true";
            return pressed && mainSnapshot().populated;
        }
        // Do not treat the previously-selected panel as the new tab's
        // completed content while React is still switching selection.
        if (tabButton?.getAttribute?.("aria-selected") !== "true") return false;
        const panels = tabRoot.querySelectorAll?.('[role="tabpanel"], [data-baseweb="tab-panel"]') || [];
        for (const panel of panels) {
            if (!rectIfVisible(panel) || panel.getAttribute?.("aria-hidden") === "true") continue;
            const nodes = panel.querySelectorAll?.(
                'h1, h2, h3, p, button, input, table, [data-testid="stElementContainer"], [data-testid="stDataFrame"]'
            ) || [];
            if (nodes.length) return true;
        }
        return false;
    };
    const showTab = () => {
        if (!tabPending || overlay.classList.contains("ai-hr-loading-visible")) return;
        placeTab();
        tabOverlay.classList.add("ai-hr-loading-visible");
        tabOverlay.setAttribute("aria-hidden", "false");
    };
    const beginTab = (root, bar, button, kind) => {
        if (!root || !bar || !button || button.disabled) return;
        if (kind === "native" && button.getAttribute?.("aria-selected") === "true") return;
        if (kind === "segmented" && (
            button.getAttribute?.("aria-pressed") === "true" ||
            button.getAttribute?.("aria-checked") === "true"
        )) return;
        hideTab();
        tabRoot = root; tabBar = bar; tabButton = button; tabKind = kind;
        tabPending = true;
        // Quiet on instant switches, visible for delayed Streamlit tab reruns.
        tabShowTimer = host.setTimeout(showTab, 125);
        // Client-side tab changes can complete without a Python ready signal.
        // If already populated, release after a brief transition; otherwise
        // wait for content restoration, page-ready, or the safety deadline.
        tabIdleTimer = host.setTimeout(() => {
            if (tabContentReady()) hideTab();
        }, 520);
        tabSafetyTimer = host.setTimeout(hideTab, 10000);
    };
    const evaluateTab = () => {
        if (!tabPending) return;
        if (!tabContentReady()) {
            host.clearTimeout(tabReadyTimer);
            tabReadyTimer = null;
            return;
        }
        if (!tabReadyTimer) {
            tabReadyTimer = host.setTimeout(() => {
                if (tabContentReady()) hideTab();
            }, 105);
        }
    };

    let showTimer = null;
    let readyTimer = null;
    let safetyTimer = null;
    let pending = false;
    let observedBlank = false;
    let pageWasPopulated = false;
    let awaitingGap = false;
    let contentGapTimer = null;
    let contentRestoreTimer = null;
    const clear = () => {
        host.clearTimeout(showTimer);
        host.clearTimeout(readyTimer);
        host.clearTimeout(safetyTimer);
        host.clearTimeout(contentGapTimer);
        host.clearTimeout(contentRestoreTimer);
        showTimer = readyTimer = safetyTimer = null;
        contentGapTimer = contentRestoreTimer = null;
    };
    const hide = () => {
        clear();
        pending = false;
        observedBlank = false;
        awaitingGap = false;
        overlay.classList.remove("ai-hr-loading-visible");
        overlay.setAttribute("aria-hidden", "true");
    };
    const place = () => {
        // The topbar has a higher stacking level (9000); the loading stage
        // starts BELOW its actual rendered edge and to the RIGHT of the
        // visible sidebar. Do not trust stMain.left alone: Streamlit may use
        // a full-viewport stMain while the sidebar floats above it.
        const main = doc.querySelector('[data-testid="stMain"]') ||
                     doc.querySelector('[data-testid="stAppViewContainer"] > .main');
        const sidebar = doc.querySelector('[data-testid="stSidebar"]');
        const topbar = doc.querySelector(
            'div[data-testid="stElementContainer"]:has(.st-key-hr_global_topbar_shell)'
        ) || doc.querySelector('.st-key-hr_global_topbar_shell') ||
             doc.querySelector('.hr-topbar');
        const visibleRect = (element) => {
            if (!element) return null;
            const rect = element.getBoundingClientRect();
            const computed = host.getComputedStyle(element);
            return rect.width > 0 && rect.height > 0 &&
                   computed.display !== 'none' && computed.visibility !== 'hidden'
                ? rect : null;
        };
        const sidebarRect = visibleRect(sidebar);
        const mainRect = visibleRect(main);
        const bannerRect = visibleRect(topbar);
        const left = Math.max(
            sidebarRect ? sidebarRect.right : 0,
            mainRect ? mainRect.left : 0,
            0
        );
        // Login/reset pages have no portal banner and should not have an
        // empty top strip. On a protected page, follow the banner's edge.
        const top = bannerRect ? bannerRect.bottom + 3 : 0;
        overlay.style.left = `${Math.max(0, Math.round(left))}px`;
        overlay.style.top = `${Math.max(0, Math.round(top))}px`;
        overlay.style.right = '0px';
        overlay.style.bottom = '0px';
    };
    const show = () => {
        if (!pending) return;
        place();
        overlay.classList.add("ai-hr-loading-visible");
        overlay.setAttribute("aria-hidden", "false");
        // A lost WebSocket or interrupted rerun must not strand the overlay.
        safetyTimer = host.setTimeout(hide, 10000);
    };
    const begin = (kind = "navigation") => {
        hideTab();
        if (pending) return;
        pending = true;
        host.clearTimeout(showTimer);
        // Explicit page navigation keeps its quiet 220ms delay. Once a
        // genuine cleared workspace is observed, show sooner, since the
        // browser has already removed the previous content.
        showTimer = kind === "content-gap"
            ? host.setTimeout(show, 70)
            : host.setTimeout(show, 220);
    };
    const mainSnapshot = () => {
        const root = doc.getElementById("root");
        const app = root && root.querySelector('[data-testid="stAppViewContainer"]');
        const main = doc.querySelector('[data-testid="stMainBlockContainer"]');
        if (!app || !main) return { app: !!app, populated: false };
        // Ignore the invisible browser bridge, loading stage and topbar. A
        // header alone is not a finished module. This detects a partial
        // Streamlit main-content replacement even when stAppView persists.
        const nodes = main.querySelectorAll('[data-testid="stElementContainer"], [data-testid="stChatMessage"], [data-testid="stDataFrame"]');
        let visible = 0;
        for (const el of nodes) {
            if (el.closest?.('.st-key-hr_global_topbar_shell, .hr-topbar')) continue;
            if (el.querySelector?.('.st-key-hr_global_topbar_shell, .hr-topbar')) continue;
            const rect = el.getBoundingClientRect?.();
            if (!rect || rect.width <= 0 || rect.height <= 0) continue;
            const computed = host.getComputedStyle(el);
            if (computed.display === 'none' || computed.visibility === 'hidden') continue;
            if (++visible >= 2) break;
        }
        return { app: true, populated: visible >= 2 };
    };
    const evaluateWorkspace = () => {
        // A horizontal tab transition owns its own smaller skeleton. Do not
        // supersede it with a whole-workspace overlay just because the
        // active tab panel briefly unmounted.
        if (tabPending) return;
        const state = mainSnapshot();
        if (state.populated) {
            pageWasPopulated = true;
            observedBlank = false;
            host.clearTimeout(contentGapTimer);
            contentGapTimer = null;
            if (awaitingGap) {
                // Some Streamlit fragment updates do not re-render the
                // bottom-of-page ready iframe; still hide after restoration.
                host.clearTimeout(contentRestoreTimer);
                contentRestoreTimer = host.setTimeout(hide, 170);
            }
            return;
        }
        if (!state.app) {
            if (!observedBlank) {
                observedBlank = true;
                awaitingGap = true;
                begin("content-gap");
            }
            return;
        }
        if (!pageWasPopulated || contentGapTimer) return;
        contentGapTimer = host.setTimeout(() => {
            contentGapTimer = null;
            if (!mainSnapshot().populated) {
                awaitingGap = true;
                begin("content-gap");
            }
        }, 45);
    };
    const ready = () => {
        if (tabPending) {
            // Streamlit can emit the page-ready bridge slightly before the
            // selected tab panel has painted. Give it one settled frame.
            host.clearTimeout(tabReadyTimer);
            tabReadyTimer = host.setTimeout(() => host.requestAnimationFrame(() =>
                host.requestAnimationFrame(() => {
                    if (tabContentReady()) hideTab();
                    else {
                        // A deliberately empty tab should not get stuck with
                        // a skeleton just because it has no visible elements.
                        host.clearTimeout(tabIdleTimer);
                        tabIdleTimer = host.setTimeout(hideTab, 300);
                    }
                })), 90);
        }
        // The ready bridge can commit ahead of the final DOM paint. Do not
        // uncover a completely blank workspace just because Python finished.
        host.clearTimeout(readyTimer);
        const done = () => host.requestAnimationFrame(() =>
            host.requestAnimationFrame(() => {
                const state = mainSnapshot();
                if (state.populated || !pageWasPopulated) {
                    pageWasPopulated = pageWasPopulated || state.populated;
                    hide();
                } else {
                    awaitingGap = true;
                }
            }));
        readyTimer = host.setTimeout(done, 90);
    };
    const onClick = (event) => {
        if (event.defaultPrevented) return;
        const raw = event.target;
        const target = raw && raw.nodeType === 1 ? raw : raw?.parentElement;
        if (!target || typeof target.closest !== "function") return;
        // Navigation-only. Form submit and chat send should NOT trigger an
        // opaque full-workspace loader (those controls have local feedback).
        const button = target.closest('[data-testid="stSidebar"] button') ||
            target.closest('[class*="quick_action_button_"] button') ||
            target.closest('[class*="st-key-open_notification_"] button');
        if (button && !button.disabled) {
            begin();
            return;
        }
        // Native (including persistent_tabs) horizontal tab switches are
        // client-side at first, and may or may not also trigger a rerun.
        const nativeTab = target.closest('[data-testid="stTabs"] button[role="tab"]');
        if (nativeTab) {
            const nativeRoot = nativeTab.closest('[data-testid="stTabs"]');
            const nativeBar = nativeRoot?.querySelector?.('[data-baseweb="tab-list"]') ||
                              nativeTab.closest('[role="tablist"]') || nativeRoot;
            beginTab(nativeRoot, nativeBar, nativeTab, "native");
            return;
        }
        // A few project-owned horizontal tab bars are segmented controls;
        // do not intercept unrelated segmented form fields.
        const segment = target.closest(
            '[data-testid="stSegmentedControl"] button, [data-baseweb="button-group"] button'
        );
        const segmentRoot = segment?.closest?.('[class*="_active_tab"]');
        if (segmentRoot) {
            const segmentBar = segment.closest('[data-testid="stSegmentedControl"]') ||
                               segment.closest('[data-baseweb="button-group"]');
            beginTab(segmentRoot, segmentBar, segment, "segmented");
        }
        // Ordinary form submission and chat send are deliberately excluded.
    };
    doc.addEventListener("click", onClick, false);

    // Monitor BOTH full Streamlit mount loss and a temporarily emptied main
    // content block. Previously only stAppView disappearance was detected,
    // missing the more common partial Streamlit rerun and internal navigation.
    let checkQueued = false;
    const onDomChange = () => {
        if (checkQueued) return;
        checkQueued = true;
        host.requestAnimationFrame(() => {
            checkQueued = false;
            if (pending) place();
            if (tabPending) { placeTab(); evaluateTab(); }
            evaluateWorkspace();
        });
    };
    const root = doc.getElementById("root");
    const observer = new MutationObserver(onDomChange);
    if (root) observer.observe(root, {
        childList: true, subtree: true, attributes: true,
        attributeFilter: ['aria-selected', 'aria-pressed', 'aria-checked', 'hidden', 'style'],
    });
    host.addEventListener("resize", place, { passive: true });

    host[key] = {
        version,
        ready,
        refresh: () => { place(); if (tabPending) placeTab(); evaluateWorkspace(); },
        dispose: () => {
            hide(); hideTab(); observer.disconnect();
            doc.removeEventListener("click", onClick, false);
            host.removeEventListener("resize", place);
        },
    };
    place();
    // If this is the first app render and there is no meaningful workspace
    // content yet, show a loader while schema/auth initialization completes.
    // On later reruns the existing controller handles transitions itself.
    const block = doc.querySelector('[data-testid="stMainBlockContainer"]');
    if (!block || !block.querySelector('h1, h2, p, button, table, [data-testid="stDataFrame"]')) {
        begin();
    } else {
        pageWasPopulated = mainSnapshot().populated;
    }
})();
</script>
"""

_READY_SCRIPT = """<script>
(() => {
    window.parent.__aiHrLoadingTransitionController?.ready?.();
})();
</script>"""


def install_loading_transition() -> None:
    """Install the reusable nonblocking browser overlay once per tab."""
    render_browser_bridge(_LOADING_TRANSITION_SCRIPT)


def signal_page_ready() -> None:
    """Signal completion after a login, Admin, or Employee page renders."""
    render_browser_bridge(_READY_SCRIPT)
