def coroutine(func):
    def functor(*args, **kwargs):
        c = func(*args, **kwargs)
        c.send(None)
        return c
    return functor


@coroutine
def broadcast(targets):
    while True:
        item = (yield)
        for target in targets:
            target.send(item)


@coroutine
def accumulator(accumulation, func):
    while True:
        item = yield accumulation
        if item:
            func(accumulation, item)
