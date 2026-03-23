"""Version information for DAS."""

try:
    #  Build system may have written version.py with a new build number.
    from das_server.version import BUILD_NUMBER
except ImportError:
    BUILD_NUMBER = 1

VERSION = (2, 134, 1, "rc", BUILD_NUMBER)

if VERSION[3]:  # pragma: no cover
    __version__ = "{0}.{1}.{2}-{3}.{4}".format(*VERSION)
else:  # pragma: no cover
    __version__ = ".".join(map(str, VERSION[0:3]))
