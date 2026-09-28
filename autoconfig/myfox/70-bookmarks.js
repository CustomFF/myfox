// Bookmarks-toolbar entries: "Advanced settings" (about:config) and "Add
// bookmarklets" (the ddblm gallery). Runs AFTER "places-browser-init-complete":
// by then the bookmarks DB is up and the async import of the default
// bookmarks is done (on a first start it would wipe (replace:true) whatever we
// inserted earlier). Idempotent — an existing bookmark is never duplicated;
// the guard pref is set only once both are in place.
(function (MyFox) {
  const { Cc, Ci, prefs, whenPlacesReady } = MyFox;

  // Bookmarks-toolbar entries. chrome/user/10-menus-bookmarks.css matches
  // them by these exact Russian titles (icon-only styling).
  const BOOKMARK_ADVANCED_TITLE = "Расширенные настройки";
  const BOOKMARK_GALLERY_TITLE = "Добавить букмарклеты";
  // The bookmarklet gallery (ddblm) picks its language from ?lang=.
  const GALLERY_URL = "https://daydve.github.io/ddblm/";

  function addGalleryBookmarks() {
    let wm = Cc["@mozilla.org/appshell/window-mediator;1"].getService(Ci.nsIWindowMediator);
    let win = wm.getMostRecentWindow("navigator:browser");
    if (!win) { return; }
    let pu = win.PlacesUtils;
    if (!pu) { return; }

    // Added ONCE per profile (the flag is set after a successful add):
    // bookmarks the user deleted must not come back on every start.
    let bookmarksDone = prefs.getBoolPref("myfox.galleryBookmarkAdded", false);

    let toolbarGuid = "toolbar_____";
    let addIfMissing = (title, url, index) => {
      return pu.bookmarks.fetch({ url }).then(found => {
        if (!found) {
          return pu.bookmarks.insert({ parentGuid: toolbarGuid, title, url, index });
        }
        return null;
      }).catch(() => null);
    };

    // The gallery is bilingual (client-side ?lang=ru), so a Russian
    // Firefox gets the localized URL from the start.
    let baseGalleryUrl = GALLERY_URL;
    let galleryUrl = (MyFox.lang === "ru" ? baseGalleryUrl + "?lang=ru" : baseGalleryUrl);

    // A bookmark from before the gallery was bilingual points at the base
    // URL — move it to the localized one instead of adding a duplicate.
    let saveGalleryBookmark = () => {
      if (galleryUrl !== baseGalleryUrl) {
        return pu.bookmarks.fetch({ url: baseGalleryUrl }).then(existing => {
          if (existing && existing.parentGuid === toolbarGuid) {
            return pu.bookmarks.update({ guid: existing.guid, url: galleryUrl }).then(() => null);
          }
          return addIfMissing(BOOKMARK_GALLERY_TITLE, galleryUrl, 1);
        }).catch(() => null);
      }
      return addIfMissing(BOOKMARK_GALLERY_TITLE, galleryUrl, 1);
    };

    if (!bookmarksDone && !MyFox.bookmarksRunning) {
      MyFox.bookmarksRunning = true;
      let ensureAll = () => addIfMissing(BOOKMARK_ADVANCED_TITLE, "about:config", 0)
        .then(saveGalleryBookmark);
      // On a new profile's first start Places may still be processing the
      // default bookmarks and erase what we just added (that's how
      // about:config used to get lost). So: add right away, check again
      // after 20s, and only when BOTH bookmarks are really there set the
      // "done" flag (otherwise the next start retries). A fresh profile
      // first has its bookmarks toolbar wiped, then the defaults imported
      // (source=RESTORE_ON_STARTUP, ~2-5s after start); we re-add right
      // after that import, or about:config would only show up on the
      // second launch.
      let onImport = (events) => {
        for (let ev of events) {
          if (ev.source === pu.bookmarks.SOURCES.RESTORE_ON_STARTUP) {
            try { pu.observers.removeListener(["bookmark-added"], onImport); } catch(e) {}
            win.setTimeout(() => { try { ensureAll(); } catch(e) {} }, 1500);
            break;
          }
        }
      };
      try { pu.observers.addListener(["bookmark-added"], onImport); } catch(e) {}
      ensureAll().then(() => {
        win.setTimeout(() => {
          try { pu.observers.removeListener(["bookmark-added"], onImport); } catch(e) {}
          ensureAll()
            .then(() => Promise.all([
              pu.bookmarks.fetch({ url: "about:config" }),
              pu.bookmarks.fetch({ url: galleryUrl })
            ]))
            .then(([cfg, gal]) => {
              if (cfg && gal) {
                try { prefs.setBoolPref("myfox.galleryBookmarkAdded", true); } catch(e) {}
              }
            })
            .catch(() => {});
        }, 20000);
      }).catch(() => {});
    }
  }

  MyFox.windowInits.push(() => whenPlacesReady(addGalleryBookmarks));
})(globalThis.MyFox);
