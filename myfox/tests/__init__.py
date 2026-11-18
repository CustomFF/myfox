import os
import tempfile

if os.name == "nt":
    # A short (8.3) TEMP, as on CI runners, would name temp dirs other than
    # the long paths Windows reports for what's in them.
    tempfile.tempdir = os.path.realpath(tempfile.gettempdir())
