from django import template
register = template.Library()


@register.filter()
def divide(n1, n2):
    try:
        return n1 / n2
    except ZeroDivisionError:
        return None


@register.filter()
def percentof(amount, total):
    try:
        return '{:.1f}%'.format(amount / total * 100)
    except ZeroDivisionError:
        return None


@register.filter()
def to_tuple(value):
    return tuple(value)


@register.filter()
def receive_data(value, index):
    return value[index]


@register.filter()
def span_id(index):
    return f'transform_key-{index}'
