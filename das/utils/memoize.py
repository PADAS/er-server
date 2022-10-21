
def memoize(f):
    '''
    Memoize for single-argument function F(hashable)
    '''

    class memoize(dict):
        def __missing__(self, key):
            ret = self[key] = f(key)
            return ret

    return memoize().__getitem__
