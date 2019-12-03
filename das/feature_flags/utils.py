from feature_flags.models import FeatureFlag


def check_flag(flag):
    flag = FeatureFlag.objects.get(name=flag)
    return flag.value
