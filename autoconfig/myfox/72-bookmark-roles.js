// Marks the toolbar buttons of myfox's own bookmarks (see 70-bookmarks.js) with
// a `myfox-role` attribute, so the icon-only styling in
// chrome/user/10-menus-bookmarks.css doesn't depend on the bookmark's title,
// its language, or its URL.
(function (MyFox) {
  const { prefs } = MyFox;

  const ROLE_PREFS = {
    advanced: "myfox.bookmark.advanced",
    gallery: "myfox.bookmark.gallery",
  };

  function initWindow(win) {
    const doc = win.document;

    function markAll() {
      try {
        let roles = {};
        for (let [role, pref] of Object.entries(ROLE_PREFS)) {
          let guid = prefs.getStringPref(pref, "");
          if (guid) roles[guid] = role;
        }
        for (let item of doc.querySelectorAll("#PersonalToolbar .bookmark-item")) {
          let guid = item._placesNode && item._placesNode.bookmarkGuid;
          if (roles[guid]) {
            if (item.getAttribute("myfox-role") !== roles[guid]) {
              item.setAttribute("myfox-role", roles[guid]);
            }
          } else if (item.hasAttribute("myfox-role")) {
            item.removeAttribute("myfox-role");
          }
        }
      } catch(e) {}
    }

    // The toolbar's buttons are rebuilt whenever the bookmarks change.
    const attach = () => {
      let toolbar = doc.getElementById("PersonalToolbar");
      if (!toolbar) return;
      new win.MutationObserver(markAll).observe(toolbar, { childList: true, subtree: true });
      markAll();
    };
    MyFox.whenDelayedStartupDone(win, attach);

    // ...and the GUIDs are recorded only once the bookmarks exist.
    let prefObserver = { observe() { markAll(); } };
    prefs.addObserver("myfox.bookmark.", prefObserver);
    win.addEventListener("unload", () => {
      try { prefs.removeObserver("myfox.bookmark.", prefObserver); } catch(e) {}
    }, { once: true });
  }
  MyFox.windowInits.push(initWindow);
})(globalThis.MyFox);
