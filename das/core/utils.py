from collections import namedtuple
from django.contrib.staticfiles.storage import staticfiles_storage

def message_digest(record):
    return sha1(str(record).encode("utf8")).hexdigest()


class StaticImageFinder(object):
    image_caches = {}
    IMAGE_TYPES = ('svg', 'png', 'jpg')
    StaticImage = namedtuple('StaticImage', ('exists', 'path'))
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
                if staticfiles_storage.exists(file):
                    path = self.web_path.format(file)
                    image_cache[key] = self.StaticImage(True, path)
                    return path
            image_cache[key] = self.StaticImage(False, None)


static_image_finder = StaticImageFinder()
