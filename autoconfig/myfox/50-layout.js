// Launcher row above the sidebar: moves #sidebar-container into the sidebar
// box and keeps it there as prefs and the DOM change.
(function (MyFox) {
  const { prefs } = MyFox;

  function initWindow(win) {
    const doc = win.document;

    function setupLayoutAndObserver(w, container, box, browser) {
    let observer = null;
      try {
        function checkAndInjectStyles() {
          try {
            let sidebarMain = container.querySelector("sidebar-main");
            if (sidebarMain && sidebarMain.shadowRoot) {
              if (!sidebarMain.shadowRoot.getElementById("custom-horizontal-styles")) {
                let style = w.document.createElement("style");
                style.id = "custom-horizontal-styles";
                style.textContent = `
                  :host([custom-launcher="true"]) {
                      height: auto !important;
                  }
                  :host([custom-launcher="true"]) .wrapper {
                      display: flex !important;
                      flex-direction: column !important;
                      height: auto !important;
                  }
                  :host([custom-launcher="true"]) .buttons-wrapper {
                      order: -1 !important;
                      display: flex !important;
                      flex-direction: row !important;
                      flex-wrap: wrap !important;
                      align-items: center !important;
                      justify-content: start !important;
                      width: 100% !important;
                      height: auto !important;
                      min-height: auto !important;
                      max-height: none !important;
                      padding: 2px 2px 2px 5px !important;
                      position: relative !important;
                      overflow: visible !important;
                  }
                  :host([custom-launcher="true"]) .actions-list {
                      display: flex !important;
                      flex-direction: row !important;
                      flex-wrap: wrap !important;
                      align-items: center !important;
                      width: 100% !important;
                      height: auto !important;
                      min-height: auto !important;
                      max-height: none !important;
                      padding-left: 0px !important;
                      margin-left: 0px !important;
                      overflow: visible !important;
                  }
                  :host([custom-launcher="true"]) .tools-and-extensions {
                      display: flex !important;
                      flex-direction: row !important;
                      flex-wrap: wrap !important;
                      align-items: center !important;
                      width: 100% !important;
                      height: auto !important;
                      min-height: auto !important;
                      max-height: none !important;
                      padding-left: 0px !important;
                      margin-left: 0px !important;
                      padding-right: 0px !important;
                      overflow: visible !important;
                  }
                  :host([custom-launcher="true"]) .bottom-actions,
                  :host([custom-launcher="true"]) .overflow-button {
                      display: none !important;
                  }
                  :host([custom-launcher="true"]) .buttons-wrapper moz-button,
                  :host([custom-launcher="true"]) .actions-list moz-button {
                      width: 24px !important;
                      height: 24px !important;
                      min-width: 24px !important;
                      min-height: 24px !important;
                      padding: 0 !important;
                      margin: 2px 4px 2px 0px !important;
                      --button-size-icon: 24px !important;
                      --button-min-height: 24px !important;
                      --button-padding-inline: 0px !important;
                      --button-padding: 0px !important;
                      box-sizing: border-box !important;
                  }
                  :host([custom-launcher="true"]) .actions-list > moz-button {
                      --button-outer-padding-block-start: var(--space-xxsmall) !important;
                      --button-outer-padding-block-end: var(--space-xxsmall) !important;
                  }
                  :host([custom-launcher="true"]) slot[name="tabstrip"] {
                      order: 1 !important;
                  }
                  :host([custom-launcher="true"]) splitter {
                      display: none !important;
                  }
                `;
                sidebarMain.shadowRoot.appendChild(style);
              }
            }
          } catch(e) {}
        }
        function updateLayout() {
          try {
            checkAndInjectStyles();
            let vertical = prefs.getBoolPref("sidebar.verticalTabs", false);
            let customLayout = prefs.getBoolPref("sidebar.launcherAboveSidebar", false);
            let expandOnHover = false;
            try {
              expandOnHover = (w.SidebarController && w.SidebarController._state && w.SidebarController._state.revampVisibility === "expand-on-hover");
            } catch(e) {}

            if (expandOnHover) {
              customLayout = false;
            }

            let sidebarMain = container.querySelector("sidebar-main");

            if (vertical) {
              box.removeAttribute("custom-launcher");
              if (customLayout) {
                if (sidebarMain) {
                  sidebarMain.setAttribute("custom-launcher", "true");
                }
              } else {
                if (sidebarMain) {
                  sidebarMain.removeAttribute("custom-launcher");
                }
              }
              if (container.parentNode !== browser) {
                if (observer) observer.disconnect();
                browser.insertBefore(container, browser.firstChild);
                if (observer) {
                  observer.observe(browser, { childList: true });
                  observer.observe(box, { childList: true });
                }
              }
            } else {
              if (customLayout) {
                box.setAttribute("custom-launcher", "true");
                if (sidebarMain) {
                  sidebarMain.setAttribute("custom-launcher", "true");
                }
                if (container.parentNode !== box) {
                  if (observer) observer.disconnect();
                  box.insertBefore(container, box.firstChild);
                  if (observer) {
                    observer.observe(browser, { childList: true });
                    observer.observe(box, { childList: true });
                  }
                }
              } else {
                box.removeAttribute("custom-launcher");
                if (sidebarMain) {
                  sidebarMain.removeAttribute("custom-launcher");
                }
                if (container.parentNode !== browser) {
                  if (observer) observer.disconnect();
                  browser.insertBefore(container, browser.firstChild);
                  if (observer) {
                    observer.observe(browser, { childList: true });
                    observer.observe(box, { childList: true });
                  }
                }
              }
            }
          } catch(e) {}
        }

        observer = new w.MutationObserver((mutations) => {
          updateLayout();
        });

        updateLayout();

        observer.observe(browser, { childList: true });
        observer.observe(box, { childList: true });
        observer.observe(container, { childList: true });

        let prefObserver = {
          observe(subject, topic, data) {
            try {
              updateLayout();
            } catch(e) {}
          }
        };
        prefs.addObserver("sidebar.verticalTabs", prefObserver, false);
        prefs.addObserver("sidebar.launcherAboveSidebar", prefObserver, false);
        prefs.addObserver("sidebar.expandOnHover", prefObserver, false);
        box.addEventListener("sidebar-show", updateLayout);
        w.addEventListener("sidebar-layout-change", updateLayout);

        w.addEventListener("unload", function onUnload() {
          try {
            w.removeEventListener("unload", onUnload);
            if (observer) observer.disconnect();
            prefs.removeObserver("sidebar.verticalTabs", prefObserver);
            prefs.removeObserver("sidebar.launcherAboveSidebar", prefObserver);
            prefs.removeObserver("sidebar.expandOnHover", prefObserver);
            w.removeEventListener("sidebar-layout-change", updateLayout);
          } catch(e) {}
        });
      } catch(e) {}
    }

    let container = doc.getElementById("sidebar-container");
    let box = doc.getElementById("sidebar-box");
    let browser = doc.getElementById("browser");

    if (container && box && browser) {
      setupLayoutAndObserver(win, container, box, browser);
    } else {
      let parentToObserve = doc.getElementById("browser") || doc.documentElement;
      let docObserver = new win.MutationObserver((mutations, obs) => {
        try {
          let c = doc.getElementById("sidebar-container");
          let b = doc.getElementById("sidebar-box");
          let br = doc.getElementById("browser");
          if (c && b && br) {
            obs.disconnect();
            setupLayoutAndObserver(win, c, b, br);
          }
        } catch(e) {}
      });
      docObserver.observe(parentToObserve, { childList: true, subtree: true });
    }
  }
  MyFox.windowInits.push(initWindow);
})(globalThis.MyFox);
