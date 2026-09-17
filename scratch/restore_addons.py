#!/usr/bin/env python3
"""restore_addons.py — восстановление аддонов профиля после zloj uninstall.

Читает локальный кэш синка weave/addonsreconciler.json, берёт УСТАНОВЛЕННЫЕ
аддоны (installed=true, enabled=true), отфильтровывает системные и качает XPI
с AMO в <profile>/extensions/<id>.xpi. Firefox при первом старте профиля
поставит их обратно тихо.

Usage:
  restore_addons.py <profile_dir> [--dry-run]
"""
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

UA = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) myfox-restore"}

SYSTEM_MARKERS = (
    "@mozilla.org", "@mozilla.com", "@mozilla.net",
    "gmp-", "langpack-", "@search.mozilla.org",
)
# аддоны, которых нет/больше нельзя качать с AMO — ставить вручную
FORCE_SKIP = {
    "uMatrix@raymondhill.net",   # снят с AMO
    "jid0-GjwrPchS3Ugt7xydvqVK4DQk8Ls@jetpack",
}


def is_system(aid):
    if aid in FORCE_SKIP:
        return True
    return any(m in aid for m in SYSTEM_MARKERS)


def fetch(url, binary=False):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=60) as r:
        return r.read() if binary else json.load(r)


def addon_download_url(aid):
    api = "https://addons.mozilla.org/api/v5/addons/addon/" + urllib.parse.quote(aid, safe="")
    try:
        data = fetch(api)
    except urllib.error.HTTPError as e:
        return None, f"HTTP {e.code}"
    cv = data.get("current_version")
    if not cv:
        return None, "no current_version"
    f = cv.get("file") or {}
    url = f.get("url")
    if not url:
        return None, "no file.url"
    return url, None


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return 1
    prof = sys.argv[1]
    dry = "--dry-run" in sys.argv
    rec = os.path.join(prof, "weave", "addonsreconciler.json")
    if not os.path.isfile(rec):
        print(f"not found: {rec}")
        return 1

    data = json.load(open(rec))
    adds = data.get("addons", {})
    ids = []
    for aid, rec_ in adds.items():
        # Проверка installed НЕ сработает: после удаления файлов Firefox сам
        # переписал реестр, пометив все снесённые как installed=false. Берём
        # все известные пользовательские ID (включая когда-то отключённые).
        if is_system(aid):
            continue
        ids.append(aid)

    ids.sort()
    print(f"аддонов к восстановлению: {len(ids)}")
    for i in ids:
        print("  ", i)

    if dry:
        return 0

    ext = os.path.join(prof, "extensions")
    os.makedirs(ext, exist_ok=True)
    ok, fail = 0, []
    for aid in ids:
        url, err = addon_download_url(aid)
        if err:
            fail.append((aid, err))
            print(f"  [skip] {aid}: {err}")
            continue
        out = os.path.join(ext, aid + ".xpi")
        try:
            xpi = fetch(url, binary=True)
            if xpi[:2] != b"PK":
                fail.append((aid, "not an XPI"))
                print(f"  [skip] {aid}: download is not XPI")
                continue
            with open(out, "wb") as fh:
                fh.write(xpi)
            ok += 1
            print(f"  [ok]   {aid}")
        except Exception as e:  # noqa: BLE001
            fail.append((aid, str(e)))
            print(f"  [fail] {aid}: {e}")
        time.sleep(0.3)

    print(f"\nготово: восстановлено {ok}, пропущено {len(fail)}")
    for aid, why in fail:
        print(f"  - {aid}: {why}")
    return 0


if __name__ == "__main__":
    sys.exit(main())