// Shared helpers and the registries the other modules plug into. Loaded
// first (modules load in file-name order).
(function (MyFox) {
  const { prefs, os, wm } = MyFox;

  // Registries filled by the modules and run by 90-windows.js:
  //   windowInits    fn(win) — once per browser window, after DOMContentLoaded
  //   sidebarHooks   fn(ctx) — whenever a sidebar panel document loads
  //   documentHooks  fn(win) — every new chrome document global
  MyFox.windowInits = [];
  MyFox.sidebarHooks = [];
  MyFox.documentHooks = [];

  function hasRussianLocale(doc) {
    return !!(doc.documentElement.lang && doc.documentElement.lang.startsWith("ru"));
  }

  // Picks the Russian or English string by the document's language.
  function tr(doc, ru, en) {
    return hasRussianLocale(doc) ? ru : en;
  }

  // Runs fn once per profile: the guard pref is set before fn runs, so a
  // failure halfway never retries on the next startup. Anything the user can
  // change in Firefox's own settings belongs behind one of these — it must
  // never be re-applied over their choice.
  function oncePerProfile(guardPref, fn) {
    try {
      if (prefs.getBoolPref(guardPref, false)) return;
      prefs.setBoolPref(guardPref, true);
      fn();
    } catch(e) {}
  }

  // Calls callback once the browser window has finished delayed startup.
  function whenDelayedStartupDone(win, callback) {
    if (win.gBrowserInit && win.gBrowserInit.delayedStartupFinished) {
      callback();
      return;
    }
    let listener = {
      observe(subject, topic) {
        if (topic === "browser-delayed-startup-finished" && subject === win) {
          try { os.removeObserver(listener, topic); } catch(e) {}
          callback();
        }
      }
    };
    try {
      os.addObserver(listener, "browser-delayed-startup-finished", false);
    } catch(e) {
      win.addEventListener("load", function onLoad() {
        win.removeEventListener("load", onLoad);
        callback();
      });
    }
  }

  function runOnDOMContentLoaded(win, callback) {
    if (win.document && win.document.readyState !== "loading") {
      try { callback(); } catch(e) {}
    } else {
      win.addEventListener("DOMContentLoaded", function onDom() {
        try {
          win.removeEventListener("DOMContentLoaded", onDom);
          callback();
        } catch(e) {}
      });
    }
  }

  function notifyLayoutChange() {
    let wins = wm.getEnumerator("navigator:browser");
    while (wins.hasMoreElements()) {
      try {
        let w = wins.getNext();
        w.dispatchEvent(new w.CustomEvent("sidebar-layout-change"));
      } catch(e) {}
    }
  }

  // Calls fn when Places has finished initializing: on the init-complete
  // notification or, if that already fired before we subscribed, on delayed
  // startup. fn must be idempotent — it can run twice.
  function whenPlacesReady(fn) {
    try {
      let placesObserver = {
        observe(subject, topic, data) {
          if (topic != "places-browser-init-complete") { return; }
          try { os.removeObserver(placesObserver, topic); } catch(e) {}
          fn();
        }
      };
      os.addObserver(placesObserver, "places-browser-init-complete", false);
      let startupObserver = {
        observe(subject, topic, data) {
          if (topic != "browser-delayed-startup-finished") { return; }
          try { os.removeObserver(startupObserver, topic); } catch(e) {}
          fn();
        }
      };
      os.addObserver(startupObserver, "browser-delayed-startup-finished", false);
    } catch(e) {}
  }

  // Puts a clear (x) button over the right edge of a moz-input-search. Returns
  // the wrapper element, which the caller inserts instead of the search box.
  function wrapSearchWithClear(sidebarDoc, search, title) {
    const HTML = "http://www.w3.org/1999/xhtml";
    let wrap = sidebarDoc.createElementNS(HTML, "div");
    wrap.className = "myfox-search-wrap";
    wrap.appendChild(search);
    let btn = sidebarDoc.createElementNS(HTML, "button");
    btn.className = "myfox-search-clear";
    btn.title = title;
    btn.hidden = true;
    let img = sidebarDoc.createElementNS(HTML, "img");
    img.src = "chrome://global/skin/icons/close.svg";
    btn.appendChild(img);
    btn.addEventListener("click", () => {
      search.value = "";
      search.dispatchEvent(new sidebarDoc.defaultView.Event("input", { bubbles: true }));
      search.focus();
    });
    search.addEventListener("input", () => { btn.hidden = !search.value; });
    wrap.appendChild(btn);
    // The box has its own native clear button in some documents; keep ours
    // only (hidden by a rule in chrome/agent/10-sidebar-panels.css).
    const markInput = () => {
      let inner = search.shadowRoot && search.shadowRoot.querySelector("input");
      if (inner) inner.setAttribute("data-myfox-no-clear", "");
    };
    Promise.resolve(search.updateComplete).then(markInput).catch(() => {});
    return wrap;
  }

  Object.assign(MyFox, {
    wrapSearchWithClear,
    hasRussianLocale, tr, oncePerProfile, whenDelayedStartupDone,
    runOnDOMContentLoaded, notifyLayoutChange, whenPlacesReady,
  });
})(globalThis.MyFox);
