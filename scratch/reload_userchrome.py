import socket
import json
import sys
import os
import shutil

def send_msg(sock, msg):
    data = json.dumps(msg).encode('utf-8')
    payload = f"{len(data)}:{data.decode('utf-8')}".encode('utf-8')
    sock.sendall(payload)

def read_msg(sock):
    len_bytes = b''
    while True:
        char = sock.recv(1)
        if not char:
            return None
        if char == b':':
            break
        len_bytes += char
    try:
        length = int(len_bytes.decode('utf-8'))
    except ValueError:
        return None
    data = b''
    while len(data) < length:
        chunk = sock.recv(length - len(data))
        if not chunk:
            return None
        data += chunk
    return json.loads(data.decode('utf-8'))

def main():
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    print("Connecting to RDP proxy at 127.0.0.1:34376...")
    try:
        sock.connect(('127.0.0.1', 34376))
    except Exception as e:
        print(f"Error connecting: {e}")
        sys.exit(1)
    
    # Read greeting
    greeting = read_msg(sock)
    
    # 1. Get parent process descriptor (ID is 0)
    send_msg(sock, {"to": "root", "type": "getProcess", "id": 0})
    p_info = read_msg(sock)
    desc = p_info.get("processDescriptor", {}).get("actor")
    if not desc:
        print("Error: Could not get parent process descriptor.")
        sock.close()
        sys.exit(1)
    
    # 2. Get target from descriptor
    send_msg(sock, {"to": desc, "type": "getTarget"})
    target_info = None
    while True:
        msg = read_msg(sock)
        if msg is None:
            break
        if msg.get("from") == desc:
            target_info = msg
            break
            
    if not target_info or "process" not in target_info:
        print("Error: Could not get target info.")
        sock.close()
        sys.exit(1)
        
    console_actor = target_info["process"]["consoleActor"]
    print(f"Found consoleActor: {console_actor}")
    
    # Query profile directory path
    get_path_js = 'Components.classes["@mozilla.org/file/directory_service;1"].getService(Components.interfaces.nsIProperties).get("ProfD", Components.interfaces.nsIFile).path'
    send_msg(sock, {
        "to": console_actor,
        "type": "evaluateJSAsync",
        "text": get_path_js
    })
    
    eval_resp = None
    while True:
        msg = read_msg(sock)
        if msg is None:
            break
        if msg.get("from") == console_actor and "resultID" in msg:
            eval_resp = msg
            break
            
    if not eval_resp:
        print("Error: Could not query profile path.")
        sock.close()
        sys.exit(1)
        
    result_id = eval_resp["resultID"]
    result = None
    while True:
        msg = read_msg(sock)
        if msg is None:
            break
        if msg.get("type") == "evaluationResult" and msg.get("resultID") == result_id:
            result = msg
            break
            
    profile_path = result.get("result") if result else None
    if not profile_path:
        print("Error: Did not receive profile path.")
        sock.close()
        sys.exit(1)
        
    print(f"Profile path: {profile_path}")
    
    # Sync files on disk for persistence on restart
    workspace_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    workspace_chrome = os.path.join(workspace_root, "chrome")
    profile_chrome = os.path.join(profile_path, "chrome")
    
    if not os.path.exists(profile_chrome):
        os.makedirs(profile_chrome, exist_ok=True)
        
    files_to_sync = ["userChrome.css", "agent_overrides.css"]
    for fname in files_to_sync:
        src = os.path.join(workspace_chrome, fname)
        dst = os.path.join(profile_chrome, fname)
        if os.path.exists(src):
            shutil.copy2(src, dst)
            print(f"Synced {fname} to profile.")
            
    # Read stylesheet contents for data URI injection
    with open(os.path.join(workspace_chrome, "userChrome.css"), "r", encoding="utf-8") as f:
        userchrome_css = f.read()
        
    # Strip @import statements from the data URI content to prevent Gecko security blocks
    import re
    userchrome_css = re.sub(r'@import\s+url\([^)]+\)[^;]*;', '', userchrome_css)
    with open(os.path.join(workspace_chrome, "agent_overrides.css"), "r", encoding="utf-8") as f:
        sidebar_agent_css = f.read()
    
    # JS Code to dynamically reload stylesheets using data URIs to bypass caching
    js_code = """
    (function(chromeCSS, agentCSS) {
      try {
        const { classes: Cc, interfaces: Ci } = Components;
        const sss = Cc["@mozilla.org/content/style-sheet-service;1"].getService(Ci.nsIStyleSheetService);
        const ios = Cc["@mozilla.org/network/io-service;1"].getService(Ci.nsIIOService);
        const wm = Cc["@mozilla.org/appshell/window-mediator;1"].getService(Ci.nsIWindowMediator);
        
        const win = wm.getMostRecentWindow("navigator:browser");
        if (!win) return "Error: No browser window";
        
        // 1. Unregister previous userChrome data URI if exists
        if (win.myfoxLastUserURI) {
          try {
            const prevURI = ios.newURI(win.myfoxLastUserURI);
            if (sss.sheetRegistered(prevURI, sss.USER_SHEET)) {
              sss.unregisterSheet(prevURI, sss.USER_SHEET);
            }
          } catch(e) {}
        }
        
        // 2. Unregister previous agent data URI if exists
        if (win.myfoxLastAgentURI) {
          try {
            const prevURI = ios.newURI(win.myfoxLastAgentURI);
            if (sss.sheetRegistered(prevURI, sss.AGENT_SHEET)) {
              sss.unregisterSheet(prevURI, sss.AGENT_SHEET);
            }
          } catch(e) {}
        }
        
        // 3. Register new userChrome.css content
        const chromeURIStr = "data:text/css;charset=utf-8," + encodeURIComponent(chromeCSS);
        const chromeURI = ios.newURI(chromeURIStr);
        sss.loadAndRegisterSheet(chromeURI, sss.USER_SHEET);
        win.myfoxLastUserURI = chromeURIStr;
        
        // 4. Register new agent_overrides.css content
        const agentURIStr = "data:text/css;charset=utf-8," + encodeURIComponent(agentCSS);
        const agentURI = ios.newURI(agentURIStr);
        sss.loadAndRegisterSheet(agentURI, sss.AGENT_SHEET);
        win.myfoxLastAgentURI = agentURIStr;
        
        return "Reload OK";
      } catch (e) {
        return "Reload Error: " + e.toString();
      }
    })(__CHROME_CSS__, __AGENT_CSS__);
    """.replace("__CHROME_CSS__", json.dumps(userchrome_css)).replace("__AGENT_CSS__", json.dumps(sidebar_agent_css))
    
    # 3. Send evaluateJSAsync
    send_msg(sock, {
        "to": console_actor,
        "type": "evaluateJSAsync",
        "text": js_code
    })
    
    # Read response containing resultID
    eval_resp = None
    while True:
        msg = read_msg(sock)
        if msg is None:
            break
        if msg.get("from") == console_actor and "resultID" in msg:
            eval_resp = msg
            break
            
    if not eval_resp:
        print("Error: No eval response received.")
        sock.close()
        sys.exit(1)
        
    result_id = eval_resp["resultID"]
    
    # 4. Wait for evaluationResult
    result = None
    while True:
        msg = read_msg(sock)
        if msg is None:
            break
        if msg.get("type") == "evaluationResult" and msg.get("resultID") == result_id:
            result = msg
            break
            
    if result:
        print("Response:", result.get("result"))
        if "exception" in result:
            print("Exception:", result.get("exceptionMessage"))
    else:
        print("Error: Did not receive evaluation result.")
        
    sock.close()

if __name__ == '__main__':
    main()
