"""Daily cookie export for this PC (no Chrome restart needed).

Reads the full cookie jar through the Muse Browser Control extension's
already-granted debugger permission (CDP Storage.getCookies via the local
daemon at 127.0.0.1:18010), then writes Downloads/cookies-export.txt in
Netscape cookies.txt format. Previous exports are deleted first, so there is
always exactly one current file (Rehan's rule).

Run daily via Windows Scheduled Task "MuseCookieExport" (04:00).
"""
import datetime
import glob
import json
import os
import urllib.request

DAEMON = "http://127.0.0.1:18010/tool"


def call_tool(tool, args):
    req = urllib.request.Request(
        DAEMON,
        data=json.dumps({"tool": tool, "args": args}).encode(),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=180) as r:
        return json.load(r)


def netscape_line(c):
    domain = c.get("domain", "") or ""
    flag = "TRUE" if domain.startswith(".") else "FALSE"
    path = c.get("path", "/") or "/"
    secure = "TRUE" if c.get("secure") else "FALSE"
    expires = 0 if c.get("session") else int(c.get("expires", 0) or 0)
    name = (c.get("name", "") or "").replace("\t", " ").replace("\n", " ")
    value = (c.get("value", "") or "").replace("\t", " ").replace("\n", " ")
    return "\t".join([domain, flag, path, secure, str(expires), name, value])


def main():
    res = call_tool("cookies.export_cdp", {})
    if not res.get("ok"):
        raise RuntimeError("cookie export failed: %s" % res.get("error"))
    cookies = res["result"]["cookies"]
    dl = os.environ.get("MUSE_COOKIE_DIR") or os.path.join(
        os.environ.get("USERPROFILE") or os.path.expanduser("~"), "Downloads"
    )
    os.makedirs(dl, exist_ok=True)
    for f in glob.glob(os.path.join(dl, "cookies-export*.txt")):
        try:
            os.remove(f)
        except OSError:
            pass
    out = os.path.join(dl, "cookies-export.txt")
    with open(out, "w", encoding="utf-8", newline="") as fh:
        fh.write("# Netscape HTTP Cookie File\n")
        fh.write(
            "# Exported %s by Muse Browser Control (CDP)\n"
            % datetime.datetime.now().isoformat(timespec="seconds")
        )
        for c in cookies:
            fh.write(netscape_line(c) + "\n")
    print("exported %d cookies -> %s" % (len(cookies), out))


if __name__ == "__main__":
    main()
