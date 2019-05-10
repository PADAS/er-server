from collections import namedtuple
from django.contrib.staticfiles.storage import staticfiles_storage


class StaticImageFinder(object):
    image_caches = {}
    IMAGE_TYPES = ('svg', 'png', 'jpg')
    StaticImage = namedtuple('StaticImage', ('exists', 'path'))
    static_paths = ('{0}', 'sprite-src/{0}')
    web_path = '/static/{0}'
    file_format = '{key}.{type}'

    def get_marker_icon(self, keys, image_types=IMAGE_TYPES):

        image_cache = self.image_caches.setdefault(image_types, {})

        for key in keys:
            static_image = image_cache.get(key, None)
            if static_image:
                if static_image.exists:
                    return static_image.path
                continue
            for t in image_types:
                file = self.file_format.format(**dict(key=key, type=t))
                for static_path in self.static_paths:
                    static_file = static_path.format(file)
                    if staticfiles_storage.exists(static_file):
                        path = self.web_path.format(static_file)
                        image_cache[key] = self.StaticImage(True, path)
                        return path
            image_cache[key] = self.StaticImage(False, None)


static_image_finder = StaticImageFinder()
