class RoutingKeysConstants(object):

    # def __setattr__(self, name, value):
    #     raise Exception()

    NEW_SOURCE_TRACKS = 'das.tracking.source.observations.new'


routing_keys = RoutingKeysConstants()



if __name__ == '__main__':
    routing_keys.NEW_SOURCE_TRACKS = 'abce'
    print(routing_keys.NEW_SOURCE_TRACKS)


    r2 = RoutingKeysConstants()

    print(r2.NEW_SOURCE_TRACKS)