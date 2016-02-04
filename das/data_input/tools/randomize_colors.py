import django
django.setup()
import observations.models
import random

def gen_random_rgb():
    return ','.join([str(random.randint(0,255)) for i in range(3)])

cur = observations.models.Subject.objects.all()

for sub in cur:
    sub.additional['rgb'] = gen_random_rgb()
    sub.save()
qq