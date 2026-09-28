// Runs the modules' window hooks on every browser window, present and future.
// Loaded last.
(function (MyFox) {
  const { os, wm, runOnDOMContentLoaded } = MyFox;

  function initWindow(win) {
    try {
      if (win.location.href !== "chrome://browser/content/browser.xhtml") return;
      if (win.myLayoutObserverInitialized) return;
      win.myLayoutObserverInitialized = true;
      for (let init of MyFox.windowInits) {
        try { init(win); } catch(e) {}
      }
    } catch(e) {}
  }

  // Hook windows that are already open
  let wins = wm.getEnumerator("navigator:browser");
  while (wins.hasMoreElements()) {
    let w = wins.getNext();
    try {
      runOnDOMContentLoaded(w, () => initWindow(w));
    } catch(e) {}
  }

  // Hook future windows and other chrome documents
  MyFox.windowObserver = {
    observe(subject, topic, data) {
      try {
        if (topic !== "chrome-document-global-created") return;
        let win = subject;
        if (win.location.href === "chrome://browser/content/browser.xhtml") {
          runOnDOMContentLoaded(win, () => initWindow(win));
        }
        for (let hook of MyFox.documentHooks) {
          try { hook(win); } catch(e) {}
        }
      } catch(e) {}
    }
  };
  os.addObserver(MyFox.windowObserver, "chrome-document-global-created", false);
})(globalThis.MyFox);
