// Downloads sidebar: about:downloads has no header or footer of its own in a
// sidebar, so build them. Styled by chrome/agent/20-downloads-sidebar.css.
(function (MyFox) {
  const { tr, wrapSearchWithClear } = MyFox;

  // Builds the downloads sidebar's own header (title, close button,
  // search box) and footer ("Clear downloads") — about:downloads has none
  // in a sidebar. Styled by chrome/agent/20-downloads-sidebar.css.
  function injectSearch(sidebarDoc, sbCtrl, doc) {
    if (!sidebarDoc || sidebarDoc.location.href !== "about:downloads") return;
    if (sidebarDoc.getElementById("downloads-sidebar-header")) return;

    let rootEl = sidebarDoc.documentElement;
    let header = sidebarDoc.createElementNS("http://www.w3.org/1999/xhtml", "div");
    header.id = "downloads-sidebar-header";

    let titleRow = sidebarDoc.createElementNS("http://www.w3.org/1999/xhtml", "div");
    titleRow.className = "downloads-sidebar-title-row";

    let h4 = sidebarDoc.createElementNS("http://www.w3.org/1999/xhtml", "h4");
    h4.textContent = tr(doc, "Загрузки", "Downloads");
    titleRow.appendChild(h4);

    let closeBtn = sidebarDoc.createXULElement("toolbarbutton");
    closeBtn.id = "downloads-sidebar-close";
    closeBtn.setAttribute("data-l10n-id", "close-button");
    let img = sidebarDoc.createXULElement("image");
    img.setAttribute("src", "chrome://global/skin/icons/close.svg");
    closeBtn.appendChild(img);
    closeBtn.addEventListener("click", function() {
      try {
        if (sbCtrl) sbCtrl.hide();
      } catch(ex) {}
    });
    titleRow.appendChild(closeBtn);
    header.appendChild(titleRow);

    // Search input inside the header
    let searchContainer = sidebarDoc.createElementNS("http://www.w3.org/1999/xhtml", "div");
    searchContainer.id = "downloads-sidebar-search-container";

    // The same search box the history and bookmarks panels use.
    try {
      sidebarDoc.defaultView.ChromeUtils.importESModule(
        "chrome://global/content/elements/moz-input-search.mjs", { global: "current" });
    } catch(e) {}
    let searchInput = sidebarDoc.createElementNS("http://www.w3.org/1999/xhtml", "moz-input-search");
    searchInput.id = "downloads-sidebar-search";
    searchInput.setAttribute("placeholder", tr(doc, "Поиск в загрузках", "Search downloads"));
    searchContainer.appendChild(wrapSearchWithClear(sidebarDoc, searchInput, tr(doc, "Очистить", "Clear")));
    header.appendChild(searchContainer);

    const filterDownloads = () => {
      try {
        let query = searchInput.value.toLowerCase().trim();
        let list = sidebarDoc.getElementById("downloadsListBox");
        if (!list) return;
        for (let item of list.children) {
          if (item.tagName.toLowerCase() === "richlistitem" && item.classList.contains("download")) {
            let target = item.querySelector(".downloadTarget");
            let text = target ? (target.value || target.textContent) : "";
            if (text.toLowerCase().includes(query)) {
              item.style.setProperty("display", "", "important");
            } else {
              item.style.setProperty("display", "none", "important");
            }
          }
        }
      } catch(e) {}
    };

    searchInput.addEventListener("input", filterDownloads);

    rootEl.insertBefore(header, rootEl.firstChild);
    // Like the built-in panels: the search box is ready for typing.
    sidebarDoc.defaultView.setTimeout(() => { try { searchInput.focus(); } catch(e) {} }, 0);

    // Keep the filter applied as downloads come and go, and show the search
    // box only while there is something to search.
    let list = sidebarDoc.getElementById("downloadsListBox");
    const updateSearchVisibility = () => {
      let any = !!(list && list.querySelector("richlistitem.download"));
      searchContainer.hidden = !any;
      if (!any && searchInput.value) {
        // A stale filter would hide the next download that shows up.
        searchInput.value = "";
        searchInput.dispatchEvent(new sidebarDoc.defaultView.Event("input", { bubbles: true }));
      }
    };
    updateSearchVisibility();
    if (list) {
      let listObserver = new sidebarDoc.defaultView.MutationObserver(() => {
        filterDownloads();
        updateSearchVisibility();
      });
      listObserver.observe(list, { childList: true });
    }

    // Footer at the bottom
    let footer = sidebarDoc.createElementNS("http://www.w3.org/1999/xhtml", "div");
    footer.id = "downloads-sidebar-footer";

    let clearBtn = sidebarDoc.createElementNS("http://www.w3.org/1999/xhtml", "button");
    clearBtn.id = "downloads-sidebar-clear-btn";

    if (sidebarDoc.l10n) {
      sidebarDoc.l10n.formatMessages([{
        id: "downloads-cmd-clear-downloads",
        args: null
      }]).then(msgs => {
        if (msgs && msgs[0] && msgs[0].attributes) {
          let labelAttr = msgs[0].attributes.find(a => a.name === "label");
          if (labelAttr) {
            clearBtn.textContent = labelAttr.value;
          }
        }
      }).catch(e => {
        clearBtn.textContent = tr(sidebarDoc, "Очистить загрузки", "Clear Downloads");
      });
    } else {
      clearBtn.textContent = tr(sidebarDoc, "Очистить загрузки", "Clear Downloads");
    }

    clearBtn.addEventListener("click", function() {
      try {
        let cmd = sidebarDoc.getElementById("downloadsCmd_clearDownloads");
        if (cmd) {
          cmd.doCommand();
        }
      } catch(ex) {}
    });
    footer.appendChild(clearBtn);
    rootEl.appendChild(footer);
  }

  MyFox.sidebarHooks.push(({ sbCtrl, sidebar, doc }) => injectSearch(sidebar.contentDocument, sbCtrl, doc));
})(globalThis.MyFox);
