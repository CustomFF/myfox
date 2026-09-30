"""Firefox tarball download/extract, language/arch detection, .desktop entry.

TODO(pass 2): port lib/firefox.sh — install_dir_validate, firefox_detect_lang,
firefox_install_tarball (urllib instead of curl, tarfile instead of tar/xz),
firefox_create_desktop_entry (the MOZ_APP_LAUNCHER/WM_CLASS wrapper script —
domain knowledge, not bash-specific, carries over almost as-is).
"""

from __future__ import annotations


def is_supported_arch() -> bool:
    raise NotImplementedError
