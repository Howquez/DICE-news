console.log("news feed ready!");

// Tracking and navigation for the news page.
//
// Every interaction is recorded as an event and streamed to the server via oTree's liveSend (see
// live_method in __init__.py). Unsent events are kept in sessionStorage until the server acknowledges
// them, so a reload or a lost connection does not lose data. The server drops duplicates by uid.
//
// Event kinds: page_load, device, dwell (teaser seconds in viewport), open / close (article reading time,
// idle-adjusted reading time, and scroll depth), ad_click, nav (browser back / forward).

(function () {
    'use strict';

    const DWELL_THRESHOLD = (js_vars.dwell_threshold || 50) / 100;
    const IDLE_MS = (js_vars.idle_seconds || 30) * 1000;
    const FLUSH_INTERVAL_MS = 3000;
    const SUBMIT_WAIT_MS = 1500;

    const pageStart = performance.now();
    const pageLoad = Date.now().toString(36) + Math.random().toString(36).slice(2, 8);
    let eventCounter = 0;


    // -- Event queue ---------------------------------------------------------------------------------------------
    const storageKey = 'dice-news-unsent:' + location.pathname;
    let queue = [];
    try {
        queue = JSON.parse(sessionStorage.getItem(storageKey) || '[]');
    } catch (e) {
        queue = [];
    }
    let ackListeners = [];

    function persist() {
        try {
            sessionStorage.setItem(storageKey, JSON.stringify(queue));
        } catch (e) { /* storage unavailable: events are still sent */ }
    }

    function record(kind, fields) {
        queue.push(Object.assign({
            uid: pageLoad + '-' + (eventCounter++),
            kind: kind,
            page_load: pageLoad,
            client_ms: Math.round(performance.now() - pageStart),
        }, fields || {}));
        persist();
    }

    function flush() {
        if (!queue.length || typeof liveSend !== 'function') return;
        try {
            liveSend({ events: queue.slice(0, 200) });
        } catch (e) {
            console.warn('Could not send events yet', e);
        }
    }

    window.liveRecv = function (data) {
        if (!data || !Array.isArray(data.ack)) return;
        const acked = new Set(data.ack);
        queue = queue.filter(event => !acked.has(event.uid));
        persist();
        ackListeners.forEach(listener => listener());
        if (queue.length) flush();
    };

    setInterval(flush, FLUSH_INTERVAL_MS);


    // -- Page load and device ------------------------------------------------------------------------------------
    const navigation = (performance.getEntriesByType && performance.getEntriesByType('navigation')[0]) || {};
    record('page_load', { info: navigation.type || '' });

    function deviceType() {
        if (window.matchMedia('(max-width: 767px)').matches) return 'Mobile';
        if (window.matchMedia('(max-width: 1024px)').matches) return 'Tablet';
        return 'Desktop';
    }

    record('device', {
        info: JSON.stringify({
            touch: ('ontouchstart' in window) || navigator.maxTouchPoints > 0,
            device_type: deviceType(),
            screen_resolution: window.screen.width + 'x' + window.screen.height,
            viewport: window.innerWidth + 'x' + window.innerHeight,
        }),
    });


    // -- Teaser dwell time ---------------------------------------------------------------------------------------
    // A teaser counts as viewed while at least DWELL_THRESHOLD of it is visible, the tab is visible,
    // and no article covers the front page.
    const inView = new Set();        // doc_ids currently intersecting
    const viewStart = {};            // doc_id -> start time of the current (counted) view
    let feedPaused = false;

    function feedActive() {
        return !feedPaused && !document.hidden;
    }

    function startDwell(docId) {
        if (feedActive() && viewStart[docId] === undefined) viewStart[docId] = Date.now();
    }

    function stopDwell(docId) {
        if (viewStart[docId] === undefined) return;
        const seconds = (Date.now() - viewStart[docId]) / 1000;
        delete viewStart[docId];
        if (seconds >= 0.05) record('dwell', { doc_id: docId, value: Number(seconds.toFixed(3)) });
    }

    function pauseFeed() {
        Object.keys(viewStart).forEach(docId => stopDwell(Number(docId)));
    }

    function resumeFeed() {
        inView.forEach(docId => startDwell(docId));
    }

    function observeTeasers() {
        const observer = new IntersectionObserver(entries => {
            entries.forEach(entry => {
                const docId = parseInt(entry.target.id, 10);
                if (isNaN(docId)) return;
                if (entry.isIntersecting) {
                    inView.add(docId);
                    startDwell(docId);
                } else {
                    inView.delete(docId);
                    stopDwell(docId);
                }
            });
        }, { threshold: DWELL_THRESHOLD });
        document.querySelectorAll('article.news-teaser[id]').forEach(teaser => observer.observe(teaser));
    }


    // -- Article reading time ------------------------------------------------------------------------------------
    // raw time: article open and tab visible; active time: additionally at most IDLE_MS since the last
    // scroll, mouse, key, or touch activity; scroll depth: deepest point of the article that was on screen.
    let reading = null;              // { docId, panel, scroller, rawMs, activeMs, lastTick, lastActivity, maxScroll }
    let readingTimer = null;

    function tick() {
        if (!reading) return;
        const now = Date.now();
        const previous = reading.lastTick;
        reading.lastTick = now;
        if (document.hidden) return;
        reading.rawMs += now - previous;
        // only the part of the interval that lies within IDLE_MS of the last activity counts as active
        const activeUntil = reading.lastActivity + IDLE_MS;
        reading.activeMs += Math.max(0, Math.min(now, activeUntil) - previous);
    }

    function updateScrollDepth() {
        if (!reading) return;
        const s = reading.scroller;
        const pct = s.scrollHeight > 0 ? Math.min(100, (s.scrollTop + s.clientHeight) / s.scrollHeight * 100) : 100;
        reading.maxScroll = Math.max(reading.maxScroll, pct);
    }

    function markActivity() {
        if (!reading) return;
        tick();
        reading.lastActivity = Date.now();
    }

    ['mousemove', 'mousedown', 'keydown', 'touchstart', 'touchmove', 'wheel'].forEach(type => {
        document.addEventListener(type, markActivity, { passive: true });
    });

    function openArticle(docId) {
        const panel = document.getElementById('article_' + docId);
        if (!panel || reading) return false;

        pauseFeed();
        feedPaused = true;

        const scroller = panel.querySelector('.news-article-scroll');
        scroller.scrollTop = 0;
        panel.classList.add('is-open');
        panel.setAttribute('aria-hidden', 'false');
        document.body.classList.add('news-article-open');
        panel.focus({ preventScroll: true });

        const now = Date.now();
        reading = { docId: docId, panel: panel, scroller: scroller, rawMs: 0, activeMs: 0,
                    lastTick: now, lastActivity: now, maxScroll: 0 };
        scroller.addEventListener('scroll', onArticleScroll, { passive: true });
        readingTimer = setInterval(tick, 1000);
        requestAnimationFrame(updateScrollDepth);

        record('open', { doc_id: docId });
        return true;
    }

    function onArticleScroll() {
        markActivity();
        updateScrollDepth();
    }

    function closeArticle() {
        if (!reading) return;
        tick();
        updateScrollDepth();
        clearInterval(readingTimer);
        reading.scroller.removeEventListener('scroll', onArticleScroll);

        record('close', {
            doc_id: reading.docId,
            value: Number((reading.rawMs / 1000).toFixed(3)),
            active_value: Number((reading.activeMs / 1000).toFixed(3)),
            scroll_pct: Number(reading.maxScroll.toFixed(1)),
        });

        const teaser = document.getElementById(String(reading.docId));
        reading.panel.classList.remove('is-open');
        reading.panel.setAttribute('aria-hidden', 'true');
        document.body.classList.remove('news-article-open');
        if (teaser) teaser.focus({ preventScroll: true });
        reading = null;

        feedPaused = false;
        resumeFeed();
        flush();
    }


    // -- Browser history: back / forward between front page and articles -----------------------------------------
    // History entries: [guard] [feed] [article]. Back from an article returns to the feed; back from the feed
    // lands on the guard entry, which shows a notice instead of leaving the oTree page.
    const baseUrl = location.pathname + location.search;
    let noticeTimer = null;

    function showNotice() {
        const notice = document.getElementById('newsNotice');
        if (!notice) return;
        notice.classList.add('is-visible');
        clearTimeout(noticeTimer);
        noticeTimer = setTimeout(() => notice.classList.remove('is-visible'), 4000);
    }

    // Browsers skip history entries that were added without a user gesture, so the guard is set up on the
    // participant's first click, tap, or key press.
    let historyArmed = false;

    function armHistory() {
        if (historyArmed) return;
        historyArmed = true;
        try {
            history.replaceState({ dn: 'guard' }, '', baseUrl);
            history.pushState({ dn: 'feed' }, '', baseUrl);
        } catch (e) {
            console.warn('History API unavailable', e);
        }
    }

    try {
        history.replaceState(null, '', baseUrl);   // drop a stale #article-… after a reload
    } catch (e) { /* ignore */ }
    ['pointerdown', 'keydown', 'touchend'].forEach(type => {
        document.addEventListener(type, armHistory, { capture: true, passive: true });
    });

    function requestOpen(docId) {
        if (reading) return;
        armHistory();
        if (openArticle(docId)) {
            try {
                history.pushState({ dn: 'article', id: docId }, '', baseUrl + '#article-' + docId);
            } catch (e) { /* navigation still works without history */ }
        }
    }

    function requestClose() {
        if (!reading) return;
        if (history.state && history.state.dn === 'article') {
            history.back();          // popstate closes the article
        } else {
            closeArticle();
        }
    }

    window.addEventListener('popstate', event => {
        const state = event.state || {};
        if (state.dn === 'article') {
            // forward (or back from a later article) to an article
            if (reading && reading.docId !== state.id) closeArticle();
            if (!reading) {
                openArticle(state.id);
                record('nav', { info: 'forward', doc_id: state.id });
            }
        } else if (state.dn === 'feed') {
            if (reading) {
                const docId = reading.docId;
                closeArticle();
                record('nav', { info: 'back', doc_id: docId });
            }
        } else if (state.dn === 'guard') {
            if (reading) closeArticle();
            record('nav', { info: 'back_blocked' });
            showNotice();
            try {
                history.pushState({ dn: 'feed' }, '', baseUrl);
            } catch (e) { /* ignore */ }
        }
    });


    // -- Clicks ----------------------------------------------------------------------------------------------------
    document.addEventListener('click', event => {
        if (event.target.closest('.news-close')) {
            event.preventDefault();
            requestClose();
            return;
        }
        const ad = event.target.closest('a.news-ad[data-doc-id]');
        if (ad) {
            record('ad_click', { doc_id: parseInt(ad.dataset.docId, 10) });
            flush();
            return;                  // the link opens in a new tab
        }
        const teaser = event.target.closest('article.news-teaser[data-article]');
        if (teaser) {
            requestOpen(parseInt(teaser.id, 10));
        }
    });

    document.addEventListener('keydown', event => {
        if (event.key === 'Escape' && reading) {
            requestClose();
        } else if (event.key === 'Enter' && !reading && event.target.closest) {
            const teaser = event.target.closest('article.news-teaser[data-article]');
            if (teaser) {
                event.preventDefault();  // don't submit the oTree form
                requestOpen(parseInt(teaser.id, 10));
            }
        }
    });


    // -- Tab visibility and leaving the page -----------------------------------------------------------------------
    document.addEventListener('visibilitychange', () => {
        if (document.hidden) {
            tick();
            pauseFeed();
            flush();
        } else {
            if (reading) {
                reading.lastTick = Date.now();
                reading.lastActivity = Date.now();
            }
            resumeFeed();
        }
    });

    window.addEventListener('pagehide', () => {
        closeArticle();
        pauseFeed();
        flush();
    });


    // -- Continue: send everything before submitting ---------------------------------------------------------------
    let submitting = false;

    document.addEventListener('click', event => {
        const button = event.target.closest('#submitButton');
        if (!button || submitting) return;
        event.preventDefault();
        submitting = true;
        closeArticle();
        pauseFeed();
        feedPaused = true;

        const submit = () => {
            ackListeners = [];
            try { sessionStorage.removeItem(storageKey); } catch (e) { /* ignore */ }
            const form = document.getElementById('form');
            if (form.requestSubmit) form.requestSubmit(button); else form.submit();
        };
        if (!queue.length) return submit();
        const timeout = setTimeout(submit, SUBMIT_WAIT_MS);
        ackListeners.push(() => {
            if (!queue.length) {
                clearTimeout(timeout);
                submit();
            }
        });
        flush();
    }, true);


    // -- Start -----------------------------------------------------------------------------------------------------
    let started = false;

    function start() {
        if (started) return;
        started = true;
        const loadingScreen = document.getElementById('loadingScreen');
        if (loadingScreen) loadingScreen.classList.add('is-done');
        observeTeasers();
        flush();
    }

    if (document.readyState === 'complete') {
        setTimeout(start, 300);
    } else {
        window.addEventListener('load', () => setTimeout(start, 300));
        setTimeout(start, 4000);
    }

})();
