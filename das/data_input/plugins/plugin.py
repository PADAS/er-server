import logging
from django.conf import settings
import observations
from functools import namedtuple
from abc import ABCMeta, abstractmethod
from das_server import celery

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


class DasPlugin(metaclass=ABCMeta):
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
        if hasattr(settings, 'DATA_INPUT_PLUGINS'):
            local_config = settings.DATA_INPUT_PLUGINS.get(self.config.plugin_name)
            self.config.configuration = self.config.configuration or {}
            if local_config:
                self.config.configuration.update(local_config)
        self.target = target

        self.logger = logging.getLogger(self.__class__.__name__)
        self.initConfig()


    @abstractmethod
    def initConfig(self):
        pass

    @abstractmethod
    def _fetch(self, *args, **kwargs):
        """
        Return a generator giving data
        """
        raise NotImplementedError('Subclass must implement _fetch')

    @abstractmethod
    def _transform(self, *args, **kwargs):
        """
        transform the fetched data set to the insert format
        """
        raise NotImplementedError('Subclass must implement _transform')

    # @abstractmethod
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
            try:
                t = self._transform(item)
                self._insert(t)
            except Exception as e:
                self.logger.exception('Failed in transforming and saving observation. %s', t)

    def notify(self, source_id):
        # TODO: Move this outside the plugin.
        try:
            celery.app.send_task('analyzers.tasks.handle_source', (str(source_id),))
        except Exception as e:
            pass
        return True



class DasPlugin2(object):
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
        if hasattr(settings, 'DATA_INPUT_PLUGINS'):
            local_config = settings.DATA_INPUT_PLUGINS.get(self.config.plugin_name)
            self.config.configuration = self.config.configuration or {}
            if local_config:
                self.config.configuration.update(local_config)

        self.cursor_pointer = None

    def cursor(self, *args, **kwargs):
        """
        Return a generator giving data
        """
        raise NotImplementedError('Subclass must implement cursor')

    def get_savepoint(self):
        return self.cursor_pointer



class PluginTarget(object):
    def __init__(self, config=None):
        self.__config = config
        self.logger = logging.getLogger(self.__class__.__name__)

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
                self.logger.info("Target received %d messages", cnt)
            except Exception as e:
                self.logger.exception("Exception in plugin handler.")

        r = _()
        next(r)
        self._r = r
        return r

    def __enter__(self):
        return self._start()

    def __exit__(self, ex_type, exc_value, traceback):
        self.logger.debug("Exiting. %s %s %s", ex_type, exc_value, traceback)
        self._r.close()
        return True

'''
Default Classes
'''
class DasDefaultTarget(PluginTarget):

    def _handle_item(self, item):
        observations.models.Observation.objects.add_observation(item)

'''
Observation Football
'''
Obs = namedtuple('Obs', ('source', 'latitude', 'longitude', 'recorded_at', 'additional'))


