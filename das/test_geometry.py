from osgeo import ogr


def make_geom():
    geom = ogr.Geometry(ogr.wkbPoint)
    geom.AddPoint_2D(0, 0)
    return geom


def gen_list(N):
    for i in range(N):
        geom = make_geom()
        yield i


N = 10
print('gen', list(gen_list(N)))
