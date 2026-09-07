import socket
import json
import sys

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
    try:
        sock.connect(('127.0.0.1', 34376))
    except Exception as e:
        print(f"Error connecting: {e}")
        sys.exit(1)
    
    read_msg(sock) # greeting
    
    send_msg(sock, {"to": "root", "type": "getProcess", "id": 0})
    p_info = read_msg(sock)
    desc = p_info.get("processDescriptor", {}).get("actor")
    
    send_msg(sock, {"to": desc, "type": "getTarget"})
    target_info = None
    while True:
        msg = read_msg(sock)
        if msg is None:
            break
        if msg.get("from") == desc:
            target_info = msg
            break
            
    console_actor = target_info["process"]["consoleActor"]
    
    js_code = """
    (function() {
      try {
        const { classes: Cc, interfaces: Ci } = Components;
        const wm = Cc["@mozilla.org/appshell/window-mediator;1"].getService(Ci.nsIWindowMediator);
        const win = wm.getMostRecentWindow("navigator:browser");
        if (!win) return "Error: No browser window found";
        
        const doc = win.document;
        // Find a visible badge in the nav-bar
        const badges = doc.querySelectorAll("#nav-bar-customization-target .toolbarbutton-badge");
        let badgeEl = null;
        for (let b of badges) {
          if (win.getComputedStyle(b).display !== "none") {
            badgeEl = b;
            break;
          }
        }
        if (!badgeEl) return "Error: No visible badge found on the navbar";
        
        const ublockBtn = badgeEl.closest("toolbarbutton") || badgeEl.closest("toolbaritem");
        if (!ublockBtn) return "Error: Button containing badge not found";
        
        let res = {};
        res.btnId = ublockBtn.id;
        res.btnTagName = ublockBtn.tagName;
        res.btnHTML = ublockBtn.outerHTML;
        
        const badgeStack = ublockBtn.querySelector(".toolbarbutton-badge-stack");
        const icon = ublockBtn.querySelector(".toolbarbutton-icon");
        const badge = badgeEl;
        
        const getStyles = (el) => {
          if (!el) return null;
          const s = win.getComputedStyle(el);
          return {
            display: s.display,
            position: s.position,
            overflow: s.overflow,
            top: s.top,
            right: s.right,
            bottom: s.bottom,
            left: s.left,
            margin: s.margin,
            padding: s.padding,
            width: s.width,
            height: s.height,
            maxHeight: s.maxHeight,
            minHeight: s.minHeight
          };
        };
        
        res.btnStyles = getStyles(ublockBtn);
        res.badgeStackStyles = getStyles(badgeStack);
        res.iconStyles = getStyles(icon);
        res.badgeStyles = getStyles(badge);
        
        if (badge) {
          res.badgeText = badge.textContent || badge.getAttribute("badge") || "";
          res.badgeHidden = badge.hidden || badge.getAttribute("hidden");
        }
        
        return JSON.stringify(res);
      } catch(e) {
        return "Error: " + e.toString();
      }
    })()
    """
    
    send_msg(sock, {
        "to": console_actor,
        "type": "evaluateJSAsync",
        "text": js_code
    })
    
    eval_resp = None
    while True:
        msg = read_msg(sock)
        if msg is None:
            break
        if msg.get("from") == console_actor and "resultID" in msg:
            eval_resp = msg
            break
            
    result_id = eval_resp["resultID"]
    
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
    sock.close()

if __name__ == '__main__':
    main()
