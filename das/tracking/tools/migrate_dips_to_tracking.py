from django.conf import settings

import tracking.models
import data_input.models
import observations.models

def savannah(plugin_conf):

    conf = plugin_conf.configuration
    defaults = dict(service_username=conf['credentials']['uid'],
                    service_password=conf['credentials']['pwd'],
                    service_api_host=conf['host']
                    )
    p, created = tracking.models.SavannahPlugin.objects.get_or_create(name=plugin_conf.plugin_name,
                                            defaults=defaults)

    if created:
        print('plugin created: ', p.name)
    return p

def inreach_kml(plugin_conf):
    conf = plugin_conf.configuration
    defaults = dict(service_username=conf['username'],
                    service_password=conf['password'],
                    service_share_path=conf['share_path']
                    )
    p, created = tracking.models.InreachKMLPlugin.objects.get_or_create(name=plugin_conf.plugin_name,
                                            defaults=defaults)

    if created:
        print('plugin created: ', p.name)
    return p

def inreach_api(plugin_conf):
    conf = plugin_conf.configuration
    defaults = dict(service_username=conf['username'],
                    service_password=conf['password'],
                    service_api_host=conf['host']
                    )
    p, created = tracking.models.InreachPlugin.objects.get_or_create(name=plugin_conf.plugin_name,
                                            defaults=defaults)

    if created:
        print('plugin created: ', p.name)
    return p

def skygistics(plugin_conf):
    conf = plugin_conf.configuration
    defaults = dict(service_username=conf['credentials']['username'],
                    service_password=conf['credentials']['password'],
                    service_api_url=conf['host']
                    )
    p, created = tracking.models.SkygisticsSatellitePlugin.objects.get_or_create(name=plugin_conf.plugin_name,
                                            defaults=defaults)

    if created:
        print('plugin created: ', p.name)
    return p

def awthttp(plugin_conf):
    conf = plugin_conf.configuration
    defaults = dict(service_api_url=conf['api_url']
                    )
    p, created = tracking.models.AWTHttpPlugin.objects.get_or_create(name=plugin_conf.plugin_name,
                                            defaults=defaults)

    if created:
        print('plugin created: ', p.name)
    return p

def demo(plugin_conf):
    conf = plugin_conf.configuration
    p, created = tracking.models.DemoSourcePlugin.objects.get_or_create(name=plugin_conf.plugin_name,
                                            defaults={})

    if created:
        print('plugin created: ', p.name)
    return p

def firms(plugin_conf):
    conf = plugin_conf.configuration

    additional = dict(polygons=conf['polygons'])

    defaults = dict(service_username=conf['username'],
                    service_password=conf['password'],
                    additional=additional,
                    )
    p, created = tracking.models.FirmsPlugin.objects.get_or_create(name=plugin_conf.plugin_name,
                                            defaults=defaults)

    if created:
        print('plugin created: ', p.name)
    return p


DIPC_2_PLUGIN = {
    'awt-http': awthttp,
    'firms-ftp': firms,
    'inreach-api': inreach_api,
    'inreach-kml': inreach_kml,
    'savannah-tracking': savannah,
    'skygistics': skygistics,
    'demo-wildlife': demo,
}

from django.contrib.contenttypes.models import ContentType
def ensure_source_plugin(dips, tracking_plugin):
    '''
    Associate the dips.source with the new style plugin.
    :param dips:
    :param tracking_plugin:
    :return:
    '''
    src = observations.models.Source.objects.get(id=dips.source_id)


    defaults = dict(
        status='enabled',
        cursor_data=dips.additional
    )


    plugin_type = ContentType.objects.get_for_model(tracking_plugin)
    v, created = tracking.models.SourcePlugin.objects.get_or_create(defaults=defaults,
                                          source=src,
                                          plugin_id=tracking_plugin.id,
                                                       plugin_type=plugin_type)

    print('source-Plugin created? {0}'.format(created))

def migrate():
    dips_list = data_input.models.PluginConfSource.objects.all()

    for dips in dips_list:

        plugin_conf = data_input.models.PluginConf.objects.get(id=dips.plugin_conf_id)

        if hasattr(settings, 'DATA_INPUT_PLUGINS'):
            local_config = settings.DATA_INPUT_PLUGINS.get(plugin_conf.plugin_name)
            plugin_conf.configuration = plugin_conf.configuration or {}
            if local_config:
                plugin_conf.configuration.update(local_config)


        print(plugin_conf.plugin_name, plugin_conf.plugin_class, plugin_conf.configuration)

        f = DIPC_2_PLUGIN[plugin_conf.plugin_class]

        if f is not None:
            tp = f(plugin_conf)

            ensure_source_plugin(dips, tp)


