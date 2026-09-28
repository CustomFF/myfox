// Theme: enables the theme add-on the installer picked, once per profile.
(function (MyFox) {
  const { prefs, wm, whenPlacesReady } = MyFox;

  // Theme add-on IDs (AMO google-chrome-dark / google-chrome-light); the
  // installer puts both .xpi files into <profile>/extensions/.
  const THEME_IDS = {
    dark: "{9631ec37-35f2-4719-815e-2f84ff28b901}",
    light: "{1fd1213e-dcb2-48d9-806f-c0a8a7d0a8e7}",
  };

  function applyTheme() {
    let win = wm.getMostRecentWindow("navigator:browser");
    if (!win) { return; }

    // Both theme add-ons are installed into the profile regardless of
    // choice (<profile>/extensions/*.xpi — instant switching later);
    // myfox.theme (from user.js, see apply_theme_pref) picks which one
    // gets enabled here. Firefox stores a sideloaded theme in
    // extensions.json with userDisabled=true until addon.enable() is
    // called explicitly — so we enable AND activate. Only ONCE
    // (myfox.themeApplied) and only if the user hasn't since picked a
    // different theme themselves: theme choice is a setting, never
    // overwritten on later startups.
    let themeId = THEME_IDS[prefs.getCharPref("myfox.theme", "dark")] || THEME_IDS.dark;
    try {
      let am = win.AddonManager;
      if (am && !prefs.getBoolPref("myfox.themeApplied", false)) {
        am.getAddonByID(themeId).then(async (addon) => {
          if (addon && addon.type === "theme") {
            let current = prefs.getStringPref("extensions.activeThemeID", "default-theme@mozilla.org");
            if (current === "default-theme@mozilla.org" || current === themeId) {
              try {
                if (addon.userDisabled) { await addon.enable(); }
              } catch(e) {}
              prefs.setStringPref("extensions.activeThemeID", themeId);
              try { prefs.clearUserPref("extensions.lastSelectedThemeID"); } catch(e) {}
            }
            prefs.setBoolPref("myfox.themeApplied", true);
          }
        }).catch(() => {});
      }
    } catch(e) {}
  }

  MyFox.windowInits.push(() => whenPlacesReady(applyTheme));
})(globalThis.MyFox);
