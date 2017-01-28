from collections import namedtuple
from django.contrib.staticfiles.storage import staticfiles_storage

class StaticImageFinder(object):
    image_cache = {}
    IMAGE_TYPES = ('svg', 'png', 'jpg')
    StaticImage = namedtuple('StaticImage', ('exists', 'path'))
    web_path = '/static/{0}'
    file_format = '{key}.{type}'

    def get_marker_icon(self, keys):

        for key in keys:
            static_image = self.image_cache.get(key, None)
            if static_image:
                if static_image.exists:
                    return static_image.path
                continue
            for t in self.IMAGE_TYPES:
                file = self.file_format.format(**dict(key=key, type=t))
                if staticfiles_storage.exists(file):
                    path = self.web_path.format(file)
                    self.image_cache[key] = self.StaticImage(True, path)
                    return path
            self.image_cache[key] = self.StaticImage(False, None)

static_image_finder = StaticImageFinder()
