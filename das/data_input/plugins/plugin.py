class Plugin:
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

    def execute(self):
        # self._fetch()
        # self._transform()
        # self._insert()
        pass

    def _fetch(self):
        """
        use the plugin configuration to go get a data set
        """
        pass

    def _transform(self):
        """
        transform the fetched data set to the insert format
        """
        pass

    def _insert(self):
        """
        pass the transformed data set to the insert target
        """
        pass


