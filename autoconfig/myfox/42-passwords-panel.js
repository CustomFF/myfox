// Password manager sidebar (megalist).
(function (MyFox) {

  // Password-card height the megalist virtual list assumes; must match the
  // 132px card step in chrome/agent/60-password-manager.css.
  const MEGALIST_CARD_HEIGHT = 132;
  const MEGALIST_ALERT_EXTRA_HEIGHT = 51;

  // The password manager sidebar (megalist) is a virtual list: it doesn't
  // measure cards, it sizes the not-yet-rendered chunks from constants
  // hardcoded in its script (215+13px per card). Our CSS makes the card
  // more compact (chrome/agent/60-password-manager.css), so keep the
  // constants in sync — otherwise scrolling jumps on long lists. Done
  // once when the panel loads, no polling.
  function patchMegalistHeights(sbWin) {
    try {
      if (!sbWin || !/megalist/.test(sbWin.document.documentURI)) return;
      sbWin.customElements.whenDefined("password-card").then(() => {
        try {
          let PC = sbWin.customElements.get("password-card");
          PC.DEFAULT_PASSWORD_CARD_HEIGHT = MEGALIST_CARD_HEIGHT;
          PC.WITH_ALERT_PASSWORD_CARD_HEIGHT = MEGALIST_CARD_HEIGHT + MEGALIST_ALERT_EXTRA_HEIGHT;
        } catch(e) {}
      });
    } catch(e) {}
  }

  MyFox.sidebarHooks.push(({ sidebar }) => patchMegalistHeights(sidebar.contentWindow));
})(globalThis.MyFox);
