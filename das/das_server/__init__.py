try:
    # Build system may have written version.py with a new build number.
    from .version import BUILD_NUMBER
except ImportError:
    BUILD_NUMBER = 1

VERSION = (0, 1, BUILD_NUMBER, 'alpha')

if VERSION[-1] != "final": # pragma: no cover
    __version__ = '.'.join(map(str, VERSION))
else: # pragma: no cover
    __version__ = '.'.join(map(str, VERSION[:-1]))

