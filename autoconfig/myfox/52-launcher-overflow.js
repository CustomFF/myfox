// The launcher row above the sidebar (50-layout.js) is a single row of a fixed
// height: wrapping it would push the tabs below it around. What doesn't fit
// goes behind the stock "more tools" button, into a menu. The stock overflow
// logic measures height and is switched off for a horizontal row, hence this.
(function (MyFox) {
  const LEFT_PADDING = 5;   // .buttons-wrapper padding-left
  const SLOT = 28;          // a 24px button plus its 4px margin
  const CORNER = 30;        // room kept for the pinned corner button

  function initWindow(win) {
    const doc = win.document;
    let scheduled = false;

    const launcher = () => doc.querySelector("sidebar-main");
    const toolButtons = sr =>
      [...sr.querySelectorAll("moz-button[view]")].filter(b => b.getAttribute("view") !== "viewCustomizeSidebar");

    function update() {
      scheduled = false;
      try {
        let host = launcher();
        if (!host || !host.shadowRoot) return;
        let sr = host.shadowRoot;
        attach(sr, host);
        let customize = sr.querySelector('moz-button[view="viewCustomizeSidebar"]');
        let tools = toolButtons(sr);
        if (host.getAttribute("custom-launcher") !== "true") {
          host.removeAttribute("myfox-overflow");
          for (let b of tools) b.removeAttribute("myfox-overflowed");
          if (customize) customize.removeAttribute("myfox-overflowed");
          return;
        }
        let width = host.getBoundingClientRect().width;
        let fits = LEFT_PADDING + tools.length * SLOT + CORNER <= width;
        let capacity = fits ? tools.length
          : Math.max(0, Math.floor((width - LEFT_PADDING - CORNER) / SLOT));
        tools.forEach((b, i) => b.toggleAttribute("myfox-overflowed", i >= capacity));
        // In overflow mode "customize" moves into the menu, like the stock one.
        if (customize) customize.toggleAttribute("myfox-overflowed", !fits);
        host.toggleAttribute("myfox-overflow", !fits);
      } catch(e) {}
    }
    const schedule = () => {
      if (scheduled) return;
      scheduled = true;
      win.requestAnimationFrame(update);
    };

    let attachedRoot = null;
    function attach(sr, host) {
      if (attachedRoot === sr) return;
      attachedRoot = sr;
      // The stock "more tools" button would open the stock overflow panel;
      // open ours instead.
      sr.addEventListener("click", ev => {
        try {
          let more = ev.composedPath().find(e => e.classList && e.classList.contains("more-tools-button"));
          if (more && host.hasAttribute("myfox-overflow")) {
            ev.stopImmediatePropagation();
            ev.preventDefault();
            openMenu(sr, more);
          }
        } catch(e) {}
      }, true);
      // The shadow DOM is re-rendered by the launcher; re-measure when its
      // buttons change (our own marks are not in the filter).
      new win.MutationObserver(schedule).observe(sr, {
        childList: true, subtree: true, attributes: true, attributeFilter: ["view", "hidden"],
      });
    }

    function openMenu(sr, anchor) {
      let customize = sr.querySelector('moz-button[view="viewCustomizeSidebar"]');
      let entries = toolButtons(sr).filter(b => b.hasAttribute("myfox-overflowed"));
      // Sidebar settings closes the list, as in the stock menu.
      if (customize) entries.push(customize);

      let menu = doc.getElementById("myfox-launcher-overflow-menu");
      if (!menu) {
        menu = doc.createXULElement("menupopup");
        menu.id = "myfox-launcher-overflow-menu";
        (doc.getElementById("mainPopupSet") || doc.documentElement).appendChild(menu);
      }
      menu.textContent = "";
      for (let button of entries) {
        let item = doc.createXULElement("menuitem");
        item.setAttribute("class", "menuitem-iconic");
        item.setAttribute("label", button.title || button.getAttribute("tooltiptext") || button.getAttribute("view"));
        let icon = button.iconSrc || button.getAttribute("iconsrc");
        if (icon) item.setAttribute("image", icon);
        item.addEventListener("command", () => button.click());
        if (button === customize && menu.firstChild) menu.appendChild(doc.createXULElement("menuseparator"));
        menu.appendChild(item);
      }
      // Open toward the middle of the window: in a narrow strip at the edge
      // the menu (wider than the strip) would otherwise be pushed off-screen.
      let leftHalf = anchor.getBoundingClientRect().x < win.innerWidth / 2;
      menu.openPopup(anchor, leftHalf ? "after_start" : "after_end", 0, 0, false, false);
    }

    // The width changes with the sidebar; the buttons and the mode change
    // with the layout (50-layout.js) and the tools list.
    let ro = new win.ResizeObserver(schedule);
    const observeLauncher = () => {
      let host = launcher();
      if (host && !host.myfoxOverflowObserved) {
        host.myfoxOverflowObserved = true;
        ro.observe(host);
        new win.MutationObserver(schedule).observe(host, { attributes: true, attributeFilter: ["custom-launcher"] });
      }
      schedule();
    };
    MyFox.whenDelayedStartupDone(win, () => {
      observeLauncher();
      // The launcher can be (re)created later; check now and then, cheaply.
      win.addEventListener("sidebar-layout-change", observeLauncher);
      let box = doc.getElementById("sidebar-box");
      if (box) box.addEventListener("sidebar-show", observeLauncher);
    });
  }
  MyFox.windowInits.push(initWindow);
})(globalThis.MyFox);
