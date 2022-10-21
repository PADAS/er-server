import logging
import sys

from pythonjsonlogger.jsonlogger import JsonFormatter


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


# utility to flatten nested dictionaries into unique k:v pairs
# so that they can be used in elasticsearch
def flatten_keys(d, parent_key='', sep='.'):
    items = []
    for k, v in d.items():
        new_key = parent_key + sep + k if parent_key else k
        if isinstance(v, dict):
            items.extend(flatten_keys(v, new_key, sep=sep).items())
        else:
            items.append((new_key, v))
    return dict(items)


class CloudLogsJsonFormatter(JsonFormatter):
    def process_log_record(self, log_record):
        log_record['severity'] = log_record['levelname']
        del log_record['levelname']
        return super().process_log_record(log_record)
