class DasPluginConfigurationError(Exception):
    """
    
    """
    pass


class DasPluginFetchError(Exception):
    pass


class DasPluginTransformationError(Exception):
    pass


class DasPluginInsertError(Exception):
    pass


class DasPlugin(object):
    """
    the basic skeleton for a data input plugin:
        the scheduler will create the instance, optionally passing
        configuration (connection) data and an insert target
    """

    def __init__(self, config=None, target=None):
        """
        :param config:  plugin configuration
        :param target:  insert target
        :return:  no
        """
        self.config = config
        self.target = target

    def _fetch(self, *args, **kwargs):
        """
        Return a generator giving data
        """
        raise NotImplementedError('Subclass must implement _fetch')

    def _transform(self, *args, **kwargs):
        """
        transform the fetched data set to the insert format
        """
        raise NotImplementedError('Subclass must implement _transform')

    def _insert(self, item, *args, **kwargs):
        """
        pass the transformed data set to the insert target
        """
        if self.target is not None:
            self.target.send(item)

    def execute(self):
        '''
        Default behavior for a plugin will be to iterate on fetched items, transform and insert each.
        :return:
        '''
        for item in self._fetch():
            t = self._transform(item)
            self._insert(t)


class PluginTarget(object):
    def __init__(self, config=None):
        self.__config = config

    def _handle_item(self, item):
        '''
        Subclass must implement _handle_item.
        :param item:
        :return:
        '''
        raise NotImplementedError('Subclasses must implement _handle_item')

    def _start(self):
        '''
        Subclass may implement _start.
        :return: coroutine with wraps _handle_item.
        '''

        def _():
            cnt = 0
            try:
                while True:
                    item = (yield)
                    self._handle_item(item)
                    cnt += 1
            except GeneratorExit:
                print("You sent %d messages" % (cnt,))

        r = _()
        next(r)
        self._r = r
        return r

    def __enter__(self):
        return self._start()

    def __exit__(self, ex_type, exc_value, traceback):
        print("Exiting. %s %s %s" % (ex_type, exc_value, traceback))
        self._r.close()
        return True


