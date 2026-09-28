// Registers chrome/agent/*.css as agent sheets.
(function (MyFox) {
  const { Ci, ios, sss, profileDir } = MyFox;

  // Agent sheets: every chrome/agent/*.css, in file-name order (the numeric
  // prefixes fix the cascade order). Agent origin is what reaches into shadow
  // DOM and beats the documents' own styles; userChrome.css can't.
  let agentDir = profileDir.clone();
  agentDir.append("chrome");
  agentDir.append("agent");
  if (agentDir.exists() && agentDir.isDirectory()) {
    let agentFiles = [];
    let entries = agentDir.directoryEntries;
    while (entries.hasMoreElements()) {
      let f = entries.getNext().QueryInterface(Ci.nsIFile);
      if (f.leafName.endsWith(".css")) agentFiles.push(f);
    }
    agentFiles.sort((a, b) => (a.leafName < b.leafName ? -1 : a.leafName > b.leafName ? 1 : 0));
    for (let f of agentFiles) {
      let fileURI = ios.newFileURI(f);
      if (!sss.sheetRegistered(fileURI, sss.AGENT_SHEET)) {
        sss.loadAndRegisterSheet(fileURI, sss.AGENT_SHEET);
      }
    }
  }
})(globalThis.MyFox);
