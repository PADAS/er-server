try:
    #  Build system may have written version.py with a new build number.
    from .version import BUILD_NUMBER
except ImportError:
    BUILD_NUMBER = 1

VERSION = (2, 137, 1, "dev", BUILD_NUMBER)

if VERSION[3]:  # pragma: no cover
    __version__ = "{0}.{1}.{2}-{3}.{4}".format(*VERSION)
else:  # pragma: no cover
    __version__ = ".".join(map(str, VERSION[0:3]))

# Allow environment variable to override version
import os

__version__ = os.getenv("VERSION", __version__)
