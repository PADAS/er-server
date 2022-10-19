import functools


def singleton(cls):
    instances = {}

    @functools.wraps(cls)
    def instance_builder(*args, **kwargs):
        if not cls in instances:
            instances[cls] = cls(*args, **kwargs)
        return instances[cls]

    return instance_builder
