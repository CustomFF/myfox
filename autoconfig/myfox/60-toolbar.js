// Toolbar: removes the import button, adds the bookmarks-toolbar toggle
// button and keeps its checked state in sync.
(function (MyFox) {
  const { t, whenDelayedStartupDone } = MyFox;

  function initWindow(win) {
    const doc = win.document;
    const sbCtrl = win.SidebarController;
    const CustomizableUI = win.CustomizableUI;

    // Profile-local replacement for the DisableProfileImport policy (we
    // never install policies): Firefox adds an "Import bookmarks"
    // (import-button) widget to the toolbar — catch its addition and
    // remove it right away. The profile button is hidden by the
    // identity.fxaccounts.toolbar.enabled default above.
    let myfoxHiddenWidgets = ["import-button"];
    try {
      if (!globalThis.myHiddenWidgetsListener) {
        globalThis.myHiddenWidgetsListener = {
          onWidgetAdded(widgetId) {
            if (myfoxHiddenWidgets.includes(widgetId)) {
              try { CustomizableUI.removeWidgetFromArea(widgetId); } catch(e) {}
            }
          }
        };
        CustomizableUI.addListener(globalThis.myHiddenWidgetsListener);
      }
      for (let wg of myfoxHiddenWidgets) {
        try { CustomizableUI.removeWidgetFromArea(wg); } catch(e) {}
      }
    } catch(e) {}

    function registerWidget() {
      try {
        if (CustomizableUI) {
          let widget = CustomizableUI.getWidget("toggle-bookmarks-toolbar-button");
          if (widget && widget.provider !== "api") {
            CustomizableUI.destroyWidget("toggle-bookmarks-toolbar-button");
            widget = null;
          }

          if (!widget) {
            CustomizableUI.createWidget({
              id: "toggle-bookmarks-toolbar-button",
              label: t("toolbar.bookmarks.label"),
              tooltiptext: t("toolbar.bookmarks.tooltip"),
              localized: false,
              onCreated(button) {
                const win = button.ownerDocument.defaultView;
                button.setAttribute("class", "toolbarbutton-1 chromeclass-toolbar-additional");
                button.style.listStyleImage = "url('chrome://browser/skin/places/bookmarksToolbar.svg')";
                button.style.fill = "currentColor";
                button.style.mozContextProperties = "fill, fill-opacity, stroke, stroke-opacity";

                const personalToolbar = button.ownerDocument.getElementById("PersonalToolbar");
                if (personalToolbar) {
                  button.toggleAttribute("checked", !personalToolbar.collapsed);
                }

                button.addEventListener("command", (e) => {
                  const personalToolbar = button.ownerDocument.getElementById("PersonalToolbar");
                  if (personalToolbar) {
                    let currentlyCollapsed = personalToolbar.collapsed;
                    CustomizableUI.setToolbarVisibility("PersonalToolbar", currentlyCollapsed);
                  }
                });
              }
            });
          }

          function ensurePlacement() {
            try {
              let placement = CustomizableUI.getPlacementOfWidget("toggle-bookmarks-toolbar-button");
              if (!placement) {
                let position = 1;
                let areaWidgets = CustomizableUI.getWidgetsInArea(CustomizableUI.AREA_NAVBAR);
                for (let i = 0; i < areaWidgets.length; i++) {
                  if (areaWidgets[i].id === "sidebar-button") {
                    position = i + 1;
                    break;
                  }
                }
                CustomizableUI.addWidgetToArea(
                  "toggle-bookmarks-toolbar-button",
                  CustomizableUI.AREA_NAVBAR,
                  position
                );
              }
            } catch(e) {}
          }

          whenDelayedStartupDone(win, ensurePlacement);
        }
      } catch(ex) {}
    }

    function setupBookmarksToolbarObserver() {
      try {
        const personalToolbar = doc.getElementById("PersonalToolbar");
        if (!personalToolbar) return;

        const updateBtnState = () => {
          const btn = doc.getElementById("toggle-bookmarks-toolbar-button");
          if (btn) {
            btn.toggleAttribute("checked", !personalToolbar.collapsed);
          }
        };

        updateBtnState();

        const obs = new win.MutationObserver((mutations) => {
          for (let mutation of mutations) {
            if (mutation.attributeName === "collapsed") {
              updateBtnState();
            }
          }
        });
        obs.observe(personalToolbar, {
          attributes: true,
          attributeFilter: ["collapsed"]
        });

        win.myBookmarksToolbarObserver = obs;
      } catch(e) {}
    }

    if (CustomizableUI) {
      registerWidget();
    } else {
      win.addEventListener("load", function onLoadWidget() {
        win.removeEventListener("load", onLoadWidget);
        registerWidget();
      });
    }

    whenDelayedStartupDone(win, setupBookmarksToolbarObserver);
  }
  MyFox.windowInits.push(initWindow);
})(globalThis.MyFox);
