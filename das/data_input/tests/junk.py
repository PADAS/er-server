class Target(object):

    def __init__(self, config=None):
        self.__config = config

    def __enter__(self):
        print("Helo")

        def _():
            cnt = 0
            try:
                while True:
                    item = (yield)
                    print(item)
                    cnt += 1
            except GeneratorExit:
                print("You sent %d messages" % (cnt,))
        r = _()
        next(r)
        self._r = r
        return r

    def __exit__(self, ex_type, exc_value, traceback):
        print("Exiting. %s %s %s" % (ex_type, exc_value, traceback))
        self._r.close()
        return True



if __name__ == '__main__':

    with Target() as consumer:
        for x in range(0, 10):
            consumer.send(x)

        raise ValueError('something is wrong.')

    x = input()


