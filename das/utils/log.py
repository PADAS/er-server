import logging
import sys


def log_stdout(level=logging.DEBUG):
    soh = logging.StreamHandler(sys.stdout)
    fmt = logging.Formatter(
        '%(asctime)s %(levelname)s %(processName)s %(thread)d %(name)s %(message)s')
    soh.setLevel(level)
    soh.setFormatter(fmt)
    logger = logging.getLogger()
    logger.addHandler(soh)
    logger.setLevel(level)


def log_file(filename, level=logging.DEBUG):
    lh = logging.FileHandler(filename)
    fmt = logging.Formatter(
        '%(asctime)s mw %(levelname)s %(processName)s %(thread)d %(name)s %(message)s')
    lh.setFormatter(fmt)
    lh.setLevel(level)
    logger = logging.getLogger()
    logger.addHandler(lh)
    logger.setLevel(level)
