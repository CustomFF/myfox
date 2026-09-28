// Extensions sidebar (see injectAddonsPanel).
(function (MyFox) {
  const { t, wrapSearchWithClear, createOwnPanel } = MyFox;

  // Builds the add-ons sidebar's UI in a blank page: a compact list of
  // installed extensions with an on/off switch, a search box that filters
  // the list and searches addons.mozilla.org on Enter, and a link to the
  // full page. It is deliberately not about:addons: that page answers
  // Firefox's "is the add-ons manager open?" ping, so "Add-ons and
  // themes" would try to reuse the sidebar instead of opening a tab.
  // Styled by chrome/agent/25-addons-sidebar.css.
  function injectAddonsPanel(sidebarDoc, win, doc, sbCtrl) {
    if (!sidebarDoc || !/^about:blank\?myfox-addons/.test(sidebarDoc.documentURI)) return;
    if (sidebarDoc.getElementById("myfox-addons-panel")) return;

    const sbWin = sidebarDoc.defaultView;
    const { AddonManager } = win.ChromeUtils.importESModule("resource://gre/modules/AddonManager.sys.mjs");
    let { panel, mk } = createOwnPanel(sidebarDoc, win, doc, sbCtrl, "myfox-addons-panel", t("panel.addons.title"));

    // The same search box and toggle the browser's own pages use.
    for (let module of ["moz-input-search", "moz-toggle"]) {
      try {
        sbWin.ChromeUtils.importESModule(
          "chrome://global/content/elements/" + module + ".mjs", { global: "current" });
      } catch(e) {}
    }
    let search = mk("moz-input-search", "myfox-addons-search");
    search.setAttribute("placeholder", t("addons.search"));
    panel.appendChild(wrapSearchWithClear(sidebarDoc, search, t("common.clear")));

    let list = mk("ul", "myfox-addons-list");
    panel.appendChild(list);

    let footer = mk("div", "myfox-addons-footer");
    let manage = mk("button", "myfox-addons-manage");
    manage.textContent = t("addons.manage");
    manage.addEventListener("click", () => {
      try { win.BrowserAddonUI.openAddonsMgr("addons://list/extension"); } catch(ex) {}
    });
    footer.appendChild(manage);
    panel.appendChild(footer);

    const openAmo = (path) => {
      let loc = win.Services.locale.appLocaleAsBCP47;
      win.openTrustedLinkIn("https://addons.mozilla.org/" + loc + path, "tab");
    };
    const openAmoSearch = (query) =>
      openAmo("/firefox/search/?type=extension&q=" + encodeURIComponent(query));

    // Per-row "..." menu: one floating element reused for every row.
    let menu = mk("div", "myfox-addons-menu");
    menu.hidden = true;
    panel.appendChild(menu);
    let menuAnchor = null;
    const closeMenu = () => { menu.hidden = true; menuAnchor = null; };
    const openMgr = (view) => {
      try { win.BrowserAddonUI.openAddonsMgr(view); } catch(ex) {}
    };
    // Removal is postponed like on about:addons: the row stays with an "Undo"
    // button until it is undone or the panel is left.
    let ourPending = new Set();
    async function removeAddon(addon) {
      try {
        let { remove, report } = await win.BrowserAddonUI.promptRemoveExtension(addon);
        if (!remove) return;
        await addon.uninstall(true);
        ourPending.add(addon);
        if (report) await win.BrowserAddonUI.reportAddon(addon.id, "uninstall");
      } catch(ex) {}
    }
    function showMenu(addon, anchor) {
      if (!menu.hidden && menuAnchor === anchor) { closeMenu(); return; }
      menu.textContent = "";
      const item = (label, fn, disabled) => {
        let b = mk("button", null, "myfox-menu-item");
        b.textContent = label;
        b.disabled = !!disabled;
        b.addEventListener("click", () => { closeMenu(); fn(); });
        menu.appendChild(b);
      };
      let view = "addons://detail/" + encodeURIComponent(addon.id);
      if (addon.optionsURL) {
        item(t("addons.menu.preferences"), () => openMgr(view + "/preferences"));
      }
      item(t("addons.menu.manage"), () => openMgr(view));
      item(t("addons.menu.remove"), () => removeAddon(addon),
        !(addon.permissions & AddonManager.PERM_CAN_UNINSTALL));
      menu.hidden = false;
      menuAnchor = anchor;
      // Under the button, right-aligned; above it if there is no room.
      let r = anchor.getBoundingClientRect();
      let mw = menu.offsetWidth, mh = menu.offsetHeight;
      let vw = sbWin.innerWidth, vh = sbWin.innerHeight;
      let top = r.bottom + 2;
      if (top + mh > vh - 4) top = Math.max(4, r.top - mh - 2);
      menu.style.left = Math.max(4, Math.min(r.right - mw, vw - mw - 4)) + "px";
      menu.style.top = top + "px";
    }
    sidebarDoc.addEventListener("click", ev => {
      if (!menu.hidden && !menu.contains(ev.target) && !ev.target.closest(".myfox-addon-more")) closeMenu();
    }, true);
    sidebarDoc.addEventListener("keydown", ev => { if (ev.key === "Escape") closeMenu(); });
    sbWin.addEventListener("blur", closeMenu);
    list.addEventListener("scroll", closeMenu);

    let renderToken = 0;
    async function render() {
      let token = ++renderToken;
      let addons = (await AddonManager.getAddonsByTypes(["extension"]))
        .filter(a => !a.hidden && !a.isSystem);
      if (token !== renderToken) return;
      // Enabled first, then disabled; each group by name.
      addons.sort((a, b) =>
        (a.userDisabled - b.userDisabled) ||
        a.name.localeCompare(b.name));
      let query = search.value.toLowerCase().trim();
      closeMenu();
      list.textContent = "";
      for (let addon of addons) {
        let li = mk("li", null, "myfox-addon");
        if (addon.userDisabled) li.classList.add("disabled");
        if (addon.pendingOperations & AddonManager.PENDING_UNINSTALL) {
          // Removed, but can still be undone.
          li.classList.add("removed");
          li.dataset.name = addon.name.toLowerCase();
          li.hidden = !!query && !addon.name.toLowerCase().includes(query);
          let removedIcon = mk("img", null, "myfox-addon-icon");
          removedIcon.src = addon.iconURL || "chrome://mozapps/skin/extensions/extensionGeneric.svg";
          li.appendChild(removedIcon);
          let text = mk("span", null, "myfox-addon-name");
          text.textContent = addon.name;
          text.title = addon.name;
          li.appendChild(text);
          let label = mk("span", null, "myfox-removed-label");
          label.textContent = t("addons.removed");
          li.appendChild(label);
          let undo = mk("button", null, "myfox-addon-more");
          undo.title = t("addons.undo");
          let undoImg = mk("img");
          undoImg.src = "chrome://global/skin/icons/undo.svg";
          undo.appendChild(undoImg);
          undo.addEventListener("click", () => {
            try { addon.cancelUninstall(); } catch(ex) {}
          });
          li.appendChild(undo);
          list.appendChild(li);
          continue;
        }
        li.hidden = !!query && !addon.name.toLowerCase().includes(query);
        li.dataset.name = addon.name.toLowerCase();

        let icon = mk("img", null, "myfox-addon-icon");
        icon.src = addon.iconURL || "chrome://mozapps/skin/extensions/extensionGeneric.svg";
        li.appendChild(icon);

        let name = mk("span", null, "myfox-addon-name");
        name.textContent = addon.name;
        // The tooltip is the add-on's description (the name is on the row).
        li.title = addon.description || addon.name;
        li.appendChild(name);

        let sw = mk("moz-toggle", null, "myfox-toggle");
        if (!addon.userDisabled) sw.setAttribute("pressed", "");
        if (!(addon.permissions & AddonManager.PERM_CAN_DISABLE)
            && !(addon.permissions & AddonManager.PERM_CAN_ENABLE)) {
          sw.setAttribute("disabled", "");
        }
        sw.setAttribute("aria-label", addon.name);
        // The tooltip names the action the click will do.
        const setTip = () => {
          sw.title = sw.hasAttribute("pressed")
            ? t("addons.tip.disable")
            : t("addons.tip.enable");
        };
        setTip();
        sw.addEventListener("toggle", async () => {
          setTip();
          try {
            if (sw.pressed) await addon.enable(); else await addon.disable();
          } catch(ex) {
            sw.pressed = !addon.userDisabled;
            setTip();
          }
        });
        // Toggling must not open the add-on's details page.
        sw.addEventListener("click", ev => ev.stopPropagation());
        li.appendChild(sw);

        let more = mk("button", null, "myfox-addon-more");
        more.title = t("addons.more");
        let moreImg = mk("img");
        moreImg.src = "chrome://global/skin/icons/more.svg";
        more.appendChild(moreImg);
        more.addEventListener("click", ev => { ev.stopPropagation(); showMenu(addon, more); });
        li.appendChild(more);

        li.addEventListener("click", () => {
          try { win.BrowserAddonUI.openAddonsMgr("addons://detail/" + encodeURIComponent(addon.id)); } catch(ex) {}
        });
        list.appendChild(li);
      }
      list.hidden = addons.length === 0;
    }

    // Shown instead of the list while nothing is installed.
    let empty = mk("div", "myfox-addons-empty");
    let emptyImg = mk("img", null, "myfox-empty-img");
    emptyImg.src = "chrome://mozapps/skin/extensions/kit-addons.svg";
    empty.appendChild(emptyImg);
    let emptyTitle = mk("h3");
    emptyTitle.textContent = t("addons.empty.title");
    empty.appendChild(emptyTitle);
    let emptyText = mk("p");
    emptyText.textContent = t("addons.empty.text");
    empty.appendChild(emptyText);
    let emptyBtn = mk("button");
    emptyBtn.textContent = t("addons.empty.button");
    emptyBtn.addEventListener("click", () => openAmo("/firefox/extensions/"));
    empty.appendChild(emptyBtn);
    empty.hidden = true;
    panel.insertBefore(empty, footer);

    // "Search on addons.mozilla.org" row, shown while a query is typed.
    let amoRow = mk("button", "myfox-addons-amo");
    let amoIcon = mk("img");
    amoIcon.src = "chrome://global/skin/icons/search-glass.svg";
    let amoText = mk("span");
    amoRow.appendChild(amoIcon);
    amoRow.appendChild(amoText);
    amoRow.hidden = true;
    amoRow.addEventListener("click", () => openAmoSearch(search.value.trim()));
    panel.insertBefore(amoRow, footer);

    const applyFilter = () => {
      let query = search.value.toLowerCase().trim();
      for (let li of list.children) {
        li.hidden = !!query && !li.dataset.name.includes(query);
      }
      amoRow.hidden = !query;
      empty.hidden = list.children.length > 0 || !!query;
      amoText.textContent = t("addons.amo", search.value.trim());
    };
    search.addEventListener("input", applyFilter);
    search.addEventListener("keydown", ev => {
      if (ev.key === "Enter" && search.value.trim()) openAmoSearch(search.value.trim());
      if (ev.key === "Escape" && search.value) { search.value = ""; applyFilter(); }
    });

    let listener = {};
    // Removing an add-on on about:addons only marks it "pending uninstall"
    // (it can be undone), so react to that and to the undo as well.
    for (let ev of ["onEnabled", "onDisabled", "onInstalled", "onUninstalled",
        "onUninstalling", "onOperationCancelled"]) {
      listener[ev] = () => { render().then(applyFilter).catch(() => {}); };
    }
    AddonManager.addAddonListener(listener);
    sbWin.addEventListener("unload", () => {
      try { AddonManager.removeAddonListener(listener); } catch(ex) {}
      // Leaving the panel makes our postponed removals final, as leaving
      // about:addons does.
      for (let addon of ourPending) {
        try {
          if (addon.pendingOperations & AddonManager.PENDING_UNINSTALL) addon.uninstall();
        } catch(ex) {}
      }
    });

    sidebarDoc.body.appendChild(panel);
    // Like the built-in panels: the search box is ready for typing.
    sbWin.setTimeout(() => { try { search.focus(); } catch(e) {} }, 0);
    render().then(applyFilter).catch(() => {});
  }

  MyFox.sidebarHooks.push(({ win, doc, sbCtrl, sidebar }) =>
    injectAddonsPanel(sidebar.contentDocument, win, doc, sbCtrl));
})(globalThis.MyFox);
