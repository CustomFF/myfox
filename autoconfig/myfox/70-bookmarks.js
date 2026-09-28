// Bookmarks-toolbar entries: "Advanced settings" (about:config) and "Add
// bookmarklets" (the ddblm gallery). Runs AFTER "places-browser-init-complete":
// by then the bookmarks DB is up and the async import of the default
// bookmarks is done (on a first start it would wipe (replace:true) whatever we
// inserted earlier). Idempotent — an existing bookmark is never duplicated;
// the guard pref is set only once both are in place.
(function (MyFox) {
  const { Cc, Ci, prefs, t, whenPlacesReady } = MyFox;

  // The titles are in the browser's language. The entries are recognized by
  // their bookmark GUID, kept in the prefs below (see 72-bookmark-roles.js),
  // so neither the title nor a later change of the gallery's address matters.
  // The bookmarklet gallery (ddblm) picks its language from ?lang=.
  const GALLERY_URL = "https://daydve.github.io/ddblm/";
  // Addresses the gallery had before GALLERY_URL: a bookmark still pointing at
  // one of them is ours and is moved to the current address. Add the old
  // address here whenever GALLERY_URL changes.
  const GALLERY_LEGACY_URLS = [];
  const ROLE_PREFS = {
    advanced: "myfox.bookmark.advanced",
    gallery: "myfox.bookmark.gallery",
  };

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
    // Remembers which bookmark plays `role`, for the styling.
    const remember = (role, bookmark) => {
      try { if (bookmark) prefs.setStringPref(ROLE_PREFS[role], bookmark.guid); } catch(e) {}
      return null;
    };
    let addIfMissing = (title, url, index, role) => {
      return pu.bookmarks.fetch({ url }).then(found => {
        if (!found) {
          return pu.bookmarks.insert({ parentGuid: toolbarGuid, title, url, index })
            .then(added => remember(role, added));
        }
        return remember(role, found);
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
            return pu.bookmarks.update({ guid: existing.guid, url: galleryUrl })
              .then(() => remember("gallery", existing));
          }
          return addIfMissing(t("bookmarks.gallery"), galleryUrl, 1, "gallery");
        }).catch(() => null);
      }
      return addIfMissing(t("bookmarks.gallery"), galleryUrl, 1, "gallery");
    };

    if (!bookmarksDone && !MyFox.bookmarksRunning) {
      MyFox.bookmarksRunning = true;
      let ensureAll = () => addIfMissing(t("bookmarks.advanced"), "about:config", 0, "advanced")
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

  // Profiles set up before the GUIDs were recorded already have the bookmarks:
  // find them once by URL and remember them. Runs on every start but only
  // acts while a GUID is missing.
  function recordExistingBookmarks() {
    let win = Cc["@mozilla.org/appshell/window-mediator;1"].getService(Ci.nsIWindowMediator)
      .getMostRecentWindow("navigator:browser");
    let pu = win && win.PlacesUtils;
    if (!pu) return;
    const find = async (role, urls) => {
      if (prefs.getStringPref(ROLE_PREFS[role], "")) return;
      for (let url of urls) {
        let found = await pu.bookmarks.fetch({ url });
        if (found && found.parentGuid === "toolbar_____") {
          prefs.setStringPref(ROLE_PREFS[role], found.guid);
          // A gallery bookmark left at a previous address follows the move.
          if (role === "gallery" && GALLERY_LEGACY_URLS.includes(url)) {
            await pu.bookmarks.update({ guid: found.guid, url: galleryUrlFor() });
          }
          return;
        }
      }
    };
    find("advanced", ["about:config"]).catch(() => {});
    find("gallery", [galleryUrlFor(), GALLERY_URL, ...GALLERY_LEGACY_URLS]).catch(() => {});
  }
  function galleryUrlFor() {
    return MyFox.lang === "ru" ? GALLERY_URL + "?lang=ru" : GALLERY_URL;
  }

  MyFox.windowInits.push(() => whenPlacesReady(addGalleryBookmarks));
  MyFox.windowInits.push(() => whenPlacesReady(recordExistingBookmarks));
})(globalThis.MyFox);
