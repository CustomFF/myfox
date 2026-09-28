// Preferences: install-level defaults and the one-time profile prefs.
(function (MyFox) {
  const { prefs, oncePerProfile } = MyFox;

  // Sideloaded add-ons (<profile>/extensions/*.xpi) are installed disabled
  // by default (extensions.autoDisableScopes=15) and flagged in about:addons.
  // Allow silent activation (MDN, "Add-ons in the enterprise"): only this
  // profile has our .xpi files, so nothing is enabled anywhere else.
  try {
    defaultPref("extensions.autoDisableScopes", 0);
    defaultPref("extensions.enabledScopes", 15);
    // The profile button (fxa-toolbar-menu-button) is drawn only while the
    // window carries the fxatoolbarmenu attribute (driven by this pref).
    // Hidden by default; a user-pref can bring it back. Removing the widget
    // doesn't help: it returns from the saved placements.
    defaultPref("identity.fxaccounts.toolbar.enabled", false);
  } catch(e) {}

  // Launcher row above the sidebar: on by default, once.
  oncePerProfile("sidebar.launcherAboveSidebar.initialized", () => {
    prefs.setBoolPref("sidebar.launcherAboveSidebar", true);
  });

  // Core prefs, once: userChrome.css support and the sidebar revamp.
  oncePerProfile("myfox.corePreferencesInitialized", () => {
    prefs.setBoolPref("toolkit.legacyUserProfileCustomizations.stylesheets", true);
    prefs.setBoolPref("sidebar.revamp", true);
  });

  // First-run prefs, once per profile (written to the profile's prefs.js, not
  // the install): no about:welcome wizard with "Import from another
  // browser", the website color scheme follows the chosen theme
  // (0 = dark, 1 = light, 2 = system), and so on. A separate guard from the
  // core one, so existing profiles that already have
  // myfox.corePreferencesInitialized still get these.
  oncePerProfile("myfox.firstRunPreferencesInitialized", () => {
    prefs.setBoolPref("browser.aboutwelcome.enabled", false);
    // myfox.theme comes from user.js, pre-seeded by the installer before
    // this profile's first launch (see lib/apply.sh's apply_theme_pref) —
    // absent for profiles that never went through the installer's theme
    // step (browser-only, clean-profile, manually created), where dark
    // stays the default.
    let wantLightTheme = prefs.getCharPref("myfox.theme", "dark") === "light";
    prefs.setIntPref("layout.css.prefers-color-scheme.content-override", wantLightTheme ? 1 : 0);
    // Bookmarks toolbar is always visible (Firefox hides it on regular tabs,
    // showing it only on "newtab"), or a new bookmark/the gallery would seem
    // to vanish as soon as you leave a new tab.
    prefs.setCharPref("browser.toolbars.bookmarks.visibility", "always");

    // One-off starting settings for a fresh profile: AI off, Pocket
    // recommendations/sponsors off, telemetry and marketing banners off,
    // compact UI on. All ordinary user prefs (the same ones Settings and
    // about:config expose) — written once and never overwritten; the user is
    // free to flip any back.
    let freshProfilePrefs = {
      // Compact UI (+ show the density switch in Customize).
      "browser.compactmode.show": true,
      "browser.uidensity": 1,

      // AI — what the "Block AI enhancements" button in "AI controls" does
      // (the global block, each feature, and the prefs underneath).
      "browser.ai.control.default": "blocked",
      "browser.ai.control.sidebarChatbot": "blocked",
      // Translations run locally — keep them (an explicit "enabled": a
      // feature left at "default" would follow the global block).
      "browser.ai.control.translations": "enabled",
      "browser.ai.control.pdfjsAltText": "blocked",
      "browser.ai.control.linkPreviewKeyPoints": "blocked",
      "browser.ai.control.smartTabGroups": "blocked",
      "browser.ai.control.smartWindow": "blocked",
      "browser.ai.control.speechRecognition": "blocked",
      "extensions.ml.enabled": false,
      // browser.ml.enable (the ML engine itself) stays: what we keep on
      // (local translations) uses it; the features are disabled above.
      "browser.ml.chat.enabled": false,
      "browser.ml.chat.menu": false,
      "browser.ml.chat.page": false,
      "browser.ml.chat.shortcuts": false,
      "browser.ml.chat.sidebar": false,
      "browser.ml.linkPreview.enabled": false,
      "browser.tabs.groups.smart.enabled": false,
      "browser.tabs.groups.smart.userEnabled": false,
      "browser.smartwindow.enabled": false,
      "pdfjs.enableAltText": false,

      // Telemetry and reports (the ones listed in Settings > Privacy).
      "datareporting.healthreport.uploadEnabled": false,
      "datareporting.usage.uploadEnabled": false,
      "datareporting.policy.dataSubmissionEnabled": false,
      "toolkit.telemetry.enabled": false,
      "toolkit.telemetry.unified": false,
      "toolkit.telemetry.archive.enabled": false,
      "toolkit.telemetry.server": "data:,",
      "toolkit.telemetry.newProfilePing.enabled": false,
      "toolkit.telemetry.bhrPing.enabled": false,
      "toolkit.telemetry.firstShutdownPing.enabled": false,
      "toolkit.telemetry.shutdownPingSender.enabled": false,
      "browser.newtabpage.activity-stream.feeds.telemetry": false,
      "browser.newtabpage.activity-stream.telemetry": false,
      "browser.search.serpEventTelemetryCategorization.enabled": false,
      "app.shield.optoutstudies.enabled": false,
      "app.normandy.enabled": false,
      "browser.discovery.enabled": false,

      // New tab: recommended stories (formerly Pocket) and sponsors.
      "browser.newtabpage.activity-stream.feeds.section.topstories": false,
      "browser.newtabpage.activity-stream.showSponsored": false,
      "browser.newtabpage.activity-stream.showSponsoredTopSites": false,
    };
    for (let name in freshProfilePrefs) {
      try {
        let val = freshProfilePrefs[name];
        if (typeof val === "boolean") prefs.setBoolPref(name, val);
        else if (typeof val === "number") prefs.setIntPref(name, val);
        else prefs.setStringPref(name, val);
      } catch(e) {}
    }
  });
})(globalThis.MyFox);
