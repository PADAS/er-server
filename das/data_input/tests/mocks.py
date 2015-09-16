from data_input.plugins.plugin import PluginTarget
from data_input.models import PluginConf


class MockConfig(PluginConf):
    class Source(object):
        manufacturer_id = None

    id = None
    plugin_name = None
    configuration = {}
    config_sources = [Source()]


class MockTarget(PluginTarget):
    def _handle_item(self, item):
        print(item)

    def send(self, item):
        pass
