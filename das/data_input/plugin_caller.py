__author__ = 'chris'

from data_input.plugins import savanna

def call_plugin():


    sp = savanna.SavannaPlugin()

    rs = sp._fetch()

    for x in rs:
        obs = sp._transform(x)

