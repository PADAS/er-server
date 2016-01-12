import django
django.setup()
import observations.models
import random

def gen_random_rgb():
    return ','.join([str(random.randint(0,255)) for i in range(3)])

cur = observations.models.Subject.objects.filter(subject_type='person')

for sub in cur:
    print(sub.additional)

    if not 'species' in sub.additional:
        sub.additional['species'] = 'Ranger'
        sub.save()
    # sub.additional['rgb'] = gen_random_rgb()
    # sub.save()







