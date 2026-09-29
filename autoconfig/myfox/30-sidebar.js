// Extra sidebar panels (Downloads, Extensions): registration, launcher
// buttons and tooltips, the tools pref, and the hook that runs the panel
// modules whenever a sidebar document loads.
(function (MyFox) {
  const { prefs, t } = MyFox;

  // Sidebar panels Firefox doesn't ship. `name` is the id in the
  // sidebar.main.tools pref; titleKey is the message used for the title and launcher tooltip.
  const EXTRA_SIDEBARS = [
    {
      view: "viewDownloadsSidebar", name: "downloads", url: "about:downloads",
      icon: "chrome://browser/skin/downloads/downloads.svg", l10nId: "navbar-downloads",
      titleKey: "panel.downloads.title",
    },
    {
      view: "viewAddonsSidebar", name: "addons", url: "about:blank?myfox-addons",
      icon: "chrome://mozapps/skin/extensions/extension.svg", l10nId: "",
      titleKey: "panel.addons.title",
    },
    {
      view: "viewTranslationsSidebar", name: "translations", url: "about:blank?myfox-translations",
      icon: "chrome://browser/skin/translations.svg", l10nId: "",
      titleKey: "panel.translations.title",
    },
  ];
  MyFox.EXTRA_SIDEBARS = EXTRA_SIDEBARS;

  // The extra panels need to be in the sidebar tools list once, to start
  // enabled like Firefox's own tools — sidebar.main.tools is Firefox's own
  // enabled-tools list, so it IS the on/off state the customize panel's
  // checkbox writes to. Restoring a name on every change (as this used to
  // do) silently undid that checkbox: it looked unchecked but the panel
  // stayed enabled underneath. Seed it once per profile, like every other
  // pref here (oncePerProfile in 00-common.js), but not via oncePerProfile
  // itself: at myfox.cfg's own load time the pref's default isn't
  // populated yet (empty string), so a plain one-shot would consume the
  // guard before ever adding our names. Retry until the list is actually
  // there, still only ever committing once.
  function seedSidebarTools(win) {
    if (prefs.getBoolPref("myfox.sidebarToolsInitialized", false)) return;
    let val = prefs.getStringPref("sidebar.main.tools", "");
    if (!val) {
      win.setTimeout(() => seedSidebarTools(win), 500);
      return;
    }
    let names = val.split(",");
    let missing = EXTRA_SIDEBARS.map(p => p.name).filter(n => !names.includes(n));
    if (missing.length) {
      prefs.setStringPref("sidebar.main.tools", names.concat(missing).join(","));
    }
    prefs.setBoolPref("myfox.sidebarToolsInitialized", true);
  }

  function initWindow(win) {
    const doc = win.document;
    const sbCtrl = win.SidebarController;
    const CustomizableUI = win.CustomizableUI;

    seedSidebarTools(win);

    // Give the extra panels' buttons in the sidebar launcher a tooltip (they
    // have no l10n label of their own here).
    function patchSidebarButtons() {
      try {
        let sidebarMain = doc.querySelector("sidebar-main");
        if (!sidebarMain || !sidebarMain.shadowRoot) return;

        let shadow = sidebarMain.shadowRoot;

        function updateAll() {
          for (let panel of EXTRA_SIDEBARS) {
            let targetText = t(panel.titleKey);
            for (let btn of shadow.querySelectorAll(`moz-button[view='${panel.view}']`)) {
              if (btn.tooltiptext !== targetText) {
                btn.removeAttribute("data-l10n-id");
                btn.removeAttribute("label");
                btn.tooltiptext = targetText;
                btn.label = undefined;
                btn.setAttribute("tooltiptext", targetText);
              }
            }
          }
        }
        updateAll();

        if (!shadow.myObserverInitialized) {
          shadow.myObserverInitialized = true;
          let observer = new win.MutationObserver(() => {
            try { updateAll(); } catch(e) {}
          });
          observer.observe(shadow, { childList: true, subtree: true, attributes: true, attributeFilter: ["view", "tooltiptext", "data-l10n-id"] });
        }
      } catch(e) {}
    }
    win.setInterval(patchSidebarButtons, 500);

    if (sbCtrl) {
      // Make the sidebars getter always include the extra panels
      const originalSidebarsDesc = Object.getOwnPropertyDescriptor(sbCtrl, "sidebars");
      if (originalSidebarsDesc && originalSidebarsDesc.get && !sbCtrl.mySidebarsGetterPatched) {
        sbCtrl.mySidebarsGetterPatched = true;
        Object.defineProperty(sbCtrl, "sidebars", {
          get() {
            let map = originalSidebarsDesc.get.call(this);
            if (map) {
              for (let panel of EXTRA_SIDEBARS) {
                if (map.has(panel.view)) continue;
                map.set(panel.view, {
                  icon: panel.icon,
                  url: panel.url,
                  title: t(panel.titleKey),
                  ...(panel.l10nId ? { sourceL10nEl: panel.l10nId } : {})
                });
              }
            }
            return map;
          },
          configurable: true,
          enumerable: true
        });
      }

      // Make getTools include the extra panels
      if (sbCtrl.getTools && !sbCtrl.myGetToolsPatched) {
        sbCtrl.myGetToolsPatched = true;
        const originalGetTools = sbCtrl.getTools;
        sbCtrl.getTools = function() {
          let tools = originalGetTools.call(this);
          if (tools) {
            let toolsPref = prefs.getStringPref("sidebar.main.tools", "");
            for (let panel of EXTRA_SIDEBARS) {
              if (tools.some(t => t.commandID === panel.view)) continue;
              tools.push({
                commandID: panel.view,
                view: panel.view,
                name: panel.name,
                iconUrl: panel.icon,
                l10nId: panel.l10nId,
                // The customize panel uses this as the checkbox label.
                tooltiptext: t(panel.titleKey),
                disabled: toolsPref ? !toolsPref.split(",").includes(panel.name) : false,
                hidden: false,
                attention: false
              });
            }
          }
          return tools;
        };
      }
    }

    // Panel-specific patches for the sidebar document: now if one is
    // already loaded, and on every later load (switching panels).
    let sidebar = doc.getElementById("sidebar");
    if (sidebar) {
      const runHooks = () => {
        for (let hook of MyFox.sidebarHooks) {
          try { hook({ win, doc, sbCtrl, sidebar }); } catch(e) {}
        }
      };
      runHooks();
      sidebar.addEventListener("load", function onSidebarLoad(ev) {
        runHooks();
        try {
          win.dispatchEvent(new CustomEvent("sidebar-layout-change"));
        } catch(ex) {}
      }, true);
    }

    if (sbCtrl && !sbCtrl.originalHandleToolbarButtonClick) {
      sbCtrl.originalHandleToolbarButtonClick = sbCtrl.handleToolbarButtonClick;
      sbCtrl.handleToolbarButtonClick = async function() {
        if (this.inSingleTabWindow || this.uninitializing) {
          return;
        }
        if (this.isOpen) {
          this._state.updateVisibility(false);
          this.hide({ dismissPanel: false });
          this.updateToolbarButton();
          return;
        }
        let cmd = this._state.command || this.lastOpenedId || this.DEFAULT_SIDEBAR_ID || "viewHistorySidebar";
        this._state.command = cmd;
        this._state.updateVisibility(true);
        await this.show(cmd);
        this.updateToolbarButton();
      };
    }
  }
  MyFox.windowInits.push(initWindow);
})(globalThis.MyFox);
