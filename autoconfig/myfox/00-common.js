// Shared helpers and the registries the other modules plug into. Loaded
// first (modules load in file-name order).
(function (MyFox) {
  const { Cc, Ci, prefs, os, wm } = MyFox;

  // Registries filled by the modules and run by 90-windows.js:
  //   windowInits    fn(win) — once per browser window, after DOMContentLoaded
  //   sidebarHooks   fn(ctx) — whenever a sidebar panel document loads
  //   documentHooks  fn(win) — every new chrome document global
  MyFox.windowInits = [];
  MyFox.sidebarHooks = [];
  MyFox.documentHooks = [];

  // ── Strings ────────────────────────────────────────────────────────────
  // Catalogs live in i18n/<language>.js. English is always loaded (the
  // fallback for any missing key); on top of it goes the catalog matching
  // the browser's language, by full tag ("pt-br") and then by language
  // ("pt"), if the file exists. The language is fixed at startup.
  MyFox.messages = {};
  const scriptLoader = Cc["@mozilla.org/moz/jssubscript-loader;1"].getService(Ci.mozIJSSubScriptLoader);
  function loadCatalog(code) {
    let file = MyFox.modDir.clone();
    file.append("i18n");
    file.append(code + ".js");
    if (!file.exists()) return false;
    try {
      scriptLoader.loadSubScript("resource://myfox/i18n/" + code + ".js", globalThis);
      return true;
    } catch(e) {
      return false;
    }
  }
  loadCatalog("en");
  // Catalogs to consult, most specific first ("pt-br", "pt"), English last.
  MyFox.langChain = [];
  {
    let tag = String(Services.locale.appLocaleAsBCP47 || "en").toLowerCase();
    for (let code of [tag, tag.split("-")[0]]) {
      if (code !== "en" && !MyFox.langChain.includes(code) && loadCatalog(code)) {
        MyFox.langChain.push(code);
      }
    }
    MyFox.langChain.push("en");
  }
  // The language in use: "ru", "pt-br", ..., or "en".
  MyFox.lang = MyFox.langChain[0];

  // The string for `key` in the browser's language ({0}, {1}, ... are filled
  // from the extra arguments); English, then the key itself, if it is missing.
  function t(key, ...args) {
    let msg;
    for (let code of MyFox.langChain) {
      msg = (MyFox.messages[code] || {})[key];
      if (msg !== undefined) break;
    }
    if (msg === undefined) msg = key;
    return msg.replace(/\{(\d+)\}/g, (m, i) => (args[i] !== undefined ? args[i] : m));
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

  // "dark" or "light": whichever the browser theme is, judged by the sidebar's
  // text color (light text = dark theme). The computed color-scheme can't be
  // trusted here: it also follows the "website appearance" setting.
  function themeScheme(win, doc) {
    let m = /rgba?\((\d+),\s*(\d+),\s*(\d+)/.exec(win.getComputedStyle(doc.getElementById("sidebar-box")).color);
    if (!m) return "dark";
    let luminance = (0.2126 * m[1] + 0.7152 * m[2] + 0.0722 * m[3]) / 255;
    return luminance > 0.5 ? "dark" : "light";
  }

  // The skeleton of a panel built on a blank page (Extensions, Translations):
  // Firefox's theme stylesheet, the sidebar's colors, and a title row with a
  // close button. Returns the panel element (not attached yet) and a small
  // element factory. Styled by chrome/agent/22-own-panels.css.
  function createOwnPanel(sidebarDoc, win, doc, sbCtrl, id, title) {
    const HTML = "http://www.w3.org/1999/xhtml";
    const mk = (tag, elId, cls) => {
      let e = sidebarDoc.createElementNS(HTML, tag);
      if (elId) e.id = elId;
      if (cls) e.className = cls;
      return e;
    };
    // Theme colors and fonts of the browser's own UI.
    let themeCss = mk("link");
    themeCss.rel = "stylesheet";
    themeCss.href = "chrome://global/skin/global.css";
    sidebarDoc.head.appendChild(themeCss);
    // A blank page doesn't inherit the sidebar's colors; copy them — and copy
    // them again when the theme is switched while the panel is open.
    let root = sidebarDoc.documentElement;
    let themeListeners = [];
    const applyTheme = () => {
      try {
        let boxStyle = win.getComputedStyle(doc.getElementById("sidebar-box"));
        let rootStyle = win.getComputedStyle(doc.documentElement);
        root.style.colorScheme = themeScheme(win, doc);
        root.style.setProperty("--sidebar-text-color", boxStyle.color);
        for (let name of ["--sidebar-background-color", "--link-color"]) {
          let val = rootStyle.getPropertyValue(name).trim();
          if (val) root.style.setProperty(name, val);
        }
        for (let fn of themeListeners) fn();
      } catch(e) {}
    };
    applyTheme();
    let themeTimer = null;
    let themeObserver = new win.MutationObserver(() => {
      if (themeTimer) win.clearTimeout(themeTimer);
      // The theme's colors land on the window over a few mutations.
      themeTimer = win.setTimeout(applyTheme, 150);
    });
    themeObserver.observe(doc.documentElement, {
      attributes: true,
      attributeFilter: ["lwtheme", "lwt-sidebar", "lwt-toolbar", "style"],
    });
    sidebarDoc.defaultView.addEventListener("unload", () => {
      try { themeObserver.disconnect(); } catch(e) {}
    }, { once: true });

    let panel = mk("div", id, "myfox-panel");
    let titleRow = mk("div", null, "myfox-panel-title-row");
    let h4 = mk("h4");
    h4.textContent = title;
    titleRow.appendChild(h4);
    let closeBtn = mk("button", "myfox-panel-close");
    let closeImg = mk("img");
    closeImg.src = "chrome://global/skin/icons/close.svg";
    closeBtn.appendChild(closeImg);
    closeBtn.addEventListener("click", () => {
      try { if (sbCtrl) sbCtrl.hide(); } catch(ex) {}
    });
    titleRow.appendChild(closeBtn);
    panel.appendChild(titleRow);
    return { panel, mk, onThemeChange: fn => themeListeners.push(fn) };
  }

  Object.assign(MyFox, {
    wrapSearchWithClear, createOwnPanel, themeScheme,
    t, oncePerProfile, whenDelayedStartupDone,
    runOnDOMContentLoaded, notifyLayoutChange, whenPlacesReady,
  });
})(globalThis.MyFox);
