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
  ];
  MyFox.EXTRA_SIDEBARS = EXTRA_SIDEBARS;

  // The extra panels must stay in the sidebar tools list: they hang off it,
  // and whenever Firefox adds any new sidebar panel it rewrites
  // sidebar.main.tools and drops them — so put them back at startup and on
  // every change of the pref.
  try {
    function ensureExtraToolsInPref() {
      let val = prefs.getStringPref("sidebar.main.tools", "");
      if (!val) return;
      let names = val.split(",");
      let missing = EXTRA_SIDEBARS.map(p => p.name).filter(n => !names.includes(n));
      if (missing.length) {
        prefs.setStringPref("sidebar.main.tools", names.concat(missing).join(","));
      }
    }
    ensureExtraToolsInPref();
    if (!globalThis.myExtraToolsObserver) {
      globalThis.myExtraToolsObserver = {
        observe() {
          try {
            ensureExtraToolsInPref();
          } catch(e) {}
        }
      };
      prefs.addObserver("sidebar.main.tools", globalThis.myExtraToolsObserver);
    }
  } catch(e) {}

  function initWindow(win) {
    const doc = win.document;
    const sbCtrl = win.SidebarController;
    const CustomizableUI = win.CustomizableUI;

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
