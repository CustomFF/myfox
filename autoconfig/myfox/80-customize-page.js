// Sidebar customize page: adds the launcher-above-sidebar checkbox and keeps
// the extra panels' labels.
(function (MyFox) {
  const { prefs, t, notifyLayoutChange } = MyFox;

  MyFox.documentHooks.push(win => {
    if (win.location.href !== "chrome://browser/content/sidebar/sidebar-customize.html") return;
    let originalDefine = win.customElements.define;
    win.customElements.define = function(name, constructor) {
      if (name === "sidebar-customize") {
        let originalUpdated = constructor.prototype.updated;
        constructor.prototype.updated = function(changedProperties) {
          if (originalUpdated) {
            originalUpdated.call(this, changedProperties);
          }
          try {
            let shadow = this.shadowRoot;
            let fieldset = shadow ? shadow.querySelector(".customize-group.no-end-margin") : null;
            if (fieldset) {
              // Its legend repeats the panel title; the stock style hides it.
              fieldset.classList.add("no-label");
              let downloadsCheckbox = shadow.querySelector('moz-checkbox[name="downloads"]') || shadow.getElementById("downloads");
              if (downloadsCheckbox) {
                downloadsCheckbox.setAttribute("label", t("panel.downloads.title"));
                downloadsCheckbox.removeAttribute("data-l10n-id");
              }

              let checkbox = shadow.getElementById("custom-launcher-above-sidebar");
              if (!checkbox) {
                checkbox = this.ownerDocument.createElement("moz-checkbox");
                checkbox.id = "custom-launcher-above-sidebar";
                checkbox.setAttribute("type", "checkbox");
                checkbox.setAttribute("name", "launcherAboveSidebar");
                checkbox.setAttribute("label", t("customize.launcherAbove"));

                // Its own group right under "open tools from the sidebar", which
                // it depends on (with that off the buttons are gone altogether).
                // Not nested in that group: a nested control inherits its
                // "disabled" and this one stays usable with vertical tabs.
                let toolsGroup = shadow.getElementById("open-tools-from-sidebar")?.closest("moz-fieldset");
                let group = this.ownerDocument.createElement("moz-fieldset");
                group.className = "customize-group medium-top-margin no-label";
                group.appendChild(checkbox);
                if (toolsGroup) {
                  toolsGroup.after(group);
                } else {
                  fieldset.after(group);
                }
              }

              let enabled = prefs.getBoolPref("sidebar.launcherAboveSidebar", false);

              let expandOnHover = false;
              try {
                expandOnHover = this.getWindow().SidebarController._state.revampVisibility === "expand-on-hover";
              } catch(e) {}

              checkbox.checked = enabled;
              checkbox.toggleAttribute("checked", enabled);
              // Same rule as the stock "open tools" checkbox: always on with
              // vertical tabs, otherwise on unless the launcher is hidden.
              let toolsShown = this.verticalTabsEnabled || this.visibility !== "hide-launcher";
              let unavailable = expandOnHover || !toolsShown;
              checkbox.disabled = unavailable;
              checkbox.toggleAttribute("disabled", unavailable);

              if (!checkbox.hasListener) {
                checkbox.hasListener = true;
                checkbox.addEventListener("change", (e) => {
                  let checked = e.target.checked;
                  prefs.setBoolPref("sidebar.launcherAboveSidebar", checked);
                  e.target.toggleAttribute("checked", checked);
                  notifyLayoutChange();
                });
              }
            }
          } catch(ex) {}
        };
      }
      return originalDefine.call(this, name, constructor);
    };
  });
})(globalThis.MyFox);
