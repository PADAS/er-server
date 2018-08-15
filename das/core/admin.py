from django.contrib import admin
# Register your models here.


class HierarchyModelAdmin(admin.ModelAdmin):
    pass


class InlineExtraDynamicMixin:
    '''
    This allows me to override the 'number of extra inline forms' depending on whether the
    containing object already exists.
    Inheriting class should include `extra` if the default is not desired.
    '''
    extra = 1

    def get_extra(self, request, obj=None, **kwargs):
        if obj:
            return 0
        return self.extra
