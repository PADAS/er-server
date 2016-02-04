import random
def gen_random_rgb():
    return ','.join([str(random.randint(0,255)) for i in range(3)])

