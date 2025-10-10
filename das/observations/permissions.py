from utils.drf import ModelPermissionsAnyOfView


class SubjectModelPermissions(ModelPermissionsAnyOfView):
    view_perms_any = ("%(app_label)s.view_subject", "%(app_label)s.view_source")
