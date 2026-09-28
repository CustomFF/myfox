// Firefox Translations sidebar: the about:translations page inside a panel.
(function (MyFox) {
  const { t, createOwnPanel, themeScheme } = MyFox;

  // Firefox's own panels load into a non-remote browser, where the page's
  // content-process actor never attaches and about:translations stays blank.
  // So the panel is a blank page (like the Extensions one) that hosts a real
  // remote <browser> showing the page. The page is fitted to the narrow width
  // by chrome/agent/26-translations-sidebar.css.
  function injectTranslationsPanel(sidebarDoc, win, doc, sbCtrl) {
    if (!sidebarDoc || !/^about:blank\?myfox-translations/.test(sidebarDoc.documentURI)) return;
    if (sidebarDoc.getElementById("myfox-translations-panel")) return;

    const sbWin = sidebarDoc.defaultView;
    let { panel, onThemeChange } = createOwnPanel(sidebarDoc, win, doc, sbCtrl,
      "myfox-translations-panel", t("panel.translations.title"));
    sidebarDoc.body.appendChild(panel);

    // <browser> is defined by the toolkit's custom-elements bundle, which a
    // blank page doesn't load by itself.
    if (!sbWin.customElements.get("browser")) {
      try {
        Services.scriptloader.loadSubScript("chrome://global/content/customElements.js", sbWin);
      } catch(e) {}
    }
    let browser = sidebarDoc.createXULElement("browser");
    browser.id = "myfox-translations-browser";
    browser.setAttribute("type", "content");
    browser.setAttribute("remote", "true");
    browser.setAttribute("maychangeremoteness", "true");
    browser.setAttribute("disableglobalhistory", "true");
    // Let the panel's own background show through the page.
    browser.setAttribute("transparent", "true");
    panel.appendChild(browser);
    // The page follows the browser theme like the rest of the panel, not the
    // "website appearance" setting that governs web content.
    const applyScheme = () => {
      try {
        browser.browsingContext.prefersColorSchemeOverride = themeScheme(win, doc);
      } catch(e) {}
    };
    applyScheme();
    onThemeChange(applyScheme);
    browser.loadURI(Services.io.newURI("about:translations"), {
      triggeringPrincipal: Services.scriptSecurityManager.getSystemPrincipal(),
    });
    // Like the built-in panels: ready for input once it is shown.
    sbWin.setTimeout(() => { try { browser.focus(); } catch(e) {} }, 0);
  }

  MyFox.sidebarHooks.push(({ win, doc, sbCtrl, sidebar }) =>
    injectTranslationsPanel(sidebar.contentDocument, win, doc, sbCtrl));
})(globalThis.MyFox);
