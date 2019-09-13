import logging

from django.contrib import admin
from django.contrib import messages
from django.utils.translation import gettext as _
from django.urls import reverse
from django.contrib.admin.templatetags.admin_urls import add_preserved_filters
from django.http import HttpResponseRedirect, HttpResponse

import choices.models as models
from django.urls import path

# IS_POPUP_VAR = '_popup'


@admin.register(models.Choice)
class ChoiceAdmin(admin.ModelAdmin):
    change_list_template = "admin/disable_change_list.html"

    actions = ('disable_choices', )
    ordering = ('model', 'field', 'ordernum', 'display')
    list_display = ('model', 'field', 'value', 'display', 'ordernum')
    list_display_links = ('model', 'field')
    search_fields = ('model', 'field', 'value', 'display')
    list_editable = ('value', 'display', 'ordernum')
    exclude = ('delete_on', 'activate' )


    def get_queryset(self, request):
        queryset = super().get_queryset(request)
        queryset = queryset.get_active_choices()
        if not self.has_change_permission(request):
            queryset = queryset.none()
        return queryset

    # def get_disable_choice_queryset(self, request):
    #     queryset = super().get_queryset(request)
    #     # queryset = queryset.get_inactive_choices()
    #     return queryset

    # def get_urls(self):
    #     urls = super().get_urls()
    #     urls_ = [
    #         path('',  self.admin_site.admin_view(self.disable_choice)),
    #         ]
    #     return urls + urls_

    # def disable_choice(self, request):
    # if 'disable_choices' in request.POST:
    #     qs = self.get_disable_choice_queryset(request)
    #     qs.get_active_choices().filter(delete_on___isnull=False)
    # self.message_user(request, 'here i am')
    # return HttpResponseRedirect('.')

    # def delete_queryset(self, request, queryset):
    #     # override this method to customize the deletion process
    #     # for "delete selected objects"
    #     pass
    # def get_urls(self):
    #     urls = super().get_urls()
    #     my_urls = [
    #         path('immortal/', self.set_immortal),
    #         path('mortal/', self.set_mortal),
    #     ]
    #     return my_urls + urls

    # def set_immortal(self, request):
    #     self.model.objects.all().update(is_immortal=True)
    #     self.message_user(request, "All heroes are now immortal")
    #     return HttpResponseRedirect("../")

    # def set_mortal(self, request):
    #     self.model.objects.all().update(is_immortal=False)
    #     self.message_user(request, "All heroes are now mortal")
    #     return HttpResponseRedirect("../"

    def response_delete(self, request, obj_display, obj_id):
        """
        Determine the HttpResponse for the delete_view stage.
        """
        opts = self.model._meta

        # if IS_POPUP_VAR in request.POST:
        #     popup_response_data = json.dumps({
        #         'action': 'delete',
        #         'value': str(obj_id),
        #     })
        #     return TemplateResponse(
        #         request, self.popup_response_template or [
        #             'admin/%s/%s/popup_response.html' %
        #             (opts.app_label, opts.model_name),
        #             'admin/%s/popup_response.html' % opts.app_label,
        #             'admin/popup_response.html',
        #         ], {
        #             'popup_response_data': popup_response_data,
        #         })

        self.message_user(
            request,
            _('The %(name)s "%(obj)s" was deactivated.') % {
                'name': opts.verbose_name,
                'obj': obj_display,
            },
            messages.WARNING,
        )

        if self.has_change_permission(request, None):
            post_url = reverse(
                'admin:%s_%s_changelist' % (opts.app_label, opts.model_name),
                current_app=self.admin_site.name,
            )
            preserved_filters = self.get_preserved_filters(request)
            post_url = add_preserved_filters(
                {
                    'preserved_filters': preserved_filters,
                    'opts': opts
                }, post_url)
        else:
            post_url = reverse('admin:index', current_app=self.admin_site.name)
        return HttpResponseRedirect(post_url)


    def disable_choices(self, request, queryset):
        fmt = 'Successfully disabled {0} {1}.'
        self.message_user(request,
                          fmt.format(len(queryset), self.opts.verbose_name),
                          messages.WARNING)
        return queryset.disable_choices()

    disable_choices.short_description = "disable selected choices"


@admin.register(models.DisableChoice)
class DisableChoiceAdmin(admin.ModelAdmin):
    # actions = ('disable_choices', )
    ordering = ('model', 'field', 'ordernum', 'display', 'delete_on')
    list_display = ('model', 'field', 'value', 'display', 'ordernum',
                    'delete_on', 'activate' )
    list_display_links = ('model', 'field')
    search_fields = ('model', 'field', 'value', 'display')
    list_editable = ('value', 'display', 'ordernum', 'activate')
    list_filter = ('value', 'delete_on', 'field' )

    def get_queryset(self, request):
        queryset = super().get_queryset(request)
        queryset = queryset.get_inactive_choices()
        if not self.has_change_permission(request):
            queryset = queryset.none()
        return queryset

    def has_add_permission(self, request):
        return False

    def save_model(self, request, obj, form, change):
        if change and obj.activate:
            obj.delete_on = None
        super().save_model(request, obj, form, change)


@admin.register(models.DynamicChoice)
class DynamicChoiceAdmin(admin.ModelAdmin):
    ordering = ('id', 'model_name')
    list_display = ('id', 'model_name', 'criteria')
    list_display_links = ('id',)
    search_fields = ('model_name',)


class BaseChoiceAdmin(admin.ModelAdmin):
    ordering = ('ordernum',)
    list_display = ('id', 'name', 'ordernum')
    list_display_links = ('id',)
    search_fields = ('name',)
    list_editable = ('name', 'ordernum')


@admin.register(models.SectionArea)
class SectionAreaAdmin(admin.ModelAdmin):
    pass


@admin.register(models.Station)
class StationAdmin(admin.ModelAdmin):
    pass


@admin.register(models.FenceLocation)
class FenceLocationAdmin(admin.ModelAdmin):
    pass


@admin.register(models.FenceDamage)
class FenceDamageAdmin(admin.ModelAdmin):
    pass


@admin.register(models.KeySpecies)
class KeySpeciesAdmin(admin.ModelAdmin):
    pass


@admin.register(models.Species)
class SpeciesAdmin(admin.ModelAdmin):
    pass


@admin.register(models.AnimalSex)
class AnimalSexAdmin(admin.ModelAdmin):
    pass


@admin.register(models.AnimalAge)
class AnimalAgeAdmin(admin.ModelAdmin):
    pass


@admin.register(models.CarcassAge)
class CarcassAgeAdmin(admin.ModelAdmin):
    pass


@admin.register(models.TrophyStatus)
class TrophyStatusAdmin(admin.ModelAdmin):
    pass


@admin.register(models.CauseOfDeath)
class CauseOfDeathAdmin(admin.ModelAdmin):
    pass


@admin.register(models.InjuryCause)
class InjuryCauseAdmin(admin.ModelAdmin):
    pass


@admin.register(models.InjuryType)
class InjuryTypeAdmin(admin.ModelAdmin):
    pass


@admin.register(models.FireStatus)
class FireStatusAdmin(admin.ModelAdmin):
    pass


@admin.register(models.FireCause)
class FireCauseAdmin(admin.ModelAdmin):
    pass


@admin.register(models.Direction)
class DirectionAdmin(admin.ModelAdmin):
    pass


@admin.register(models.Crops)
class CropsAdmin(admin.ModelAdmin):
    pass


@admin.register(models.TypeOfIllegalActivity)
class TypeOfIllegalActivityAdmin(admin.ModelAdmin):
    pass


@admin.register(models.IllegalActivity)
class IllegalActivityAdmin(admin.ModelAdmin):
    pass


@admin.register(models.SnareAge)
class SnareAgeAdmin(admin.ModelAdmin):
    pass


@admin.register(models.SnareStatus)
class SnareStatusAdmin(admin.ModelAdmin):
    pass


@admin.register(models.PoacherCampAge)
class PoacherCampAgeAdmin(admin.ModelAdmin):
    pass


@admin.register(models.TypeOfShots)
class TypeOfShotsAdmin(admin.ModelAdmin):
    pass


@admin.register(models.TypeOfTrophy)
class TypeOfTrophyAdmin(admin.ModelAdmin):
    pass


@admin.register(models.VehicleTypes)
class VehicleTypesAdmin(admin.ModelAdmin):
    pass


@admin.register(models.IncidentStatus)
class IncidentStatusAdmin(BaseChoiceAdmin):
    pass


@admin.register(models.WeaponTypes)
class WeaponTypesAdmin(admin.ModelAdmin):
    pass


@admin.register(models.TrafficType)
class TrafficTypeAdmin(admin.ModelAdmin):
    pass


@admin.register(models.TrafficActivity)
class TrafficActivityAdmin(admin.ModelAdmin):
    pass


@admin.register(models.AccidentType)
class AccidentTypeAdmin(admin.ModelAdmin):
    pass


@admin.register(models.CriticalSightingType)
class CriticalSightingTypeAdmin(admin.ModelAdmin):
    pass


@admin.register(models.TracksType)
class TracksTypeAdmin(admin.ModelAdmin):
    pass


@admin.register(models.VehicleType)
class VehicleTypeAdmin(admin.ModelAdmin):
    pass


@admin.register(models.MedicalEquipmentRequired)
class MedicalEquipmentRequiredAdmin(admin.ModelAdmin):
    pass


@admin.register(models.MedicalEvacSecurity)
class MedicalEvacSecurityAdmin(admin.ModelAdmin):
    pass


@admin.register(models.DetectionType)
class DetectionTypeAdmin(admin.ModelAdmin):
    pass


@admin.register(models.Nationality)
class NationalityAdmin(admin.ModelAdmin):
    pass


@admin.register(models.Village)
class VillageAdmin(admin.ModelAdmin):
    pass


@admin.register(models.ArrestViolation)
class ArrestViolationAdmin(admin.ModelAdmin):
    pass

# Liwonde specific choices tables


@admin.register(models.AnimalCondition)
class AnimalConditionAdmin(admin.ModelAdmin):
    pass


@admin.register(models.ArrestNationality)
class ArrestNationalityAdmin(admin.ModelAdmin):
    pass


@admin.register(models.ReasonForArrest)
class ReasonForArrestAdmin(admin.ModelAdmin):
    pass


@admin.register(models.ArrestVillageName)
class ArrestVillageNameAdmin(admin.ModelAdmin):
    pass


@admin.register(models.SpoorAge)
class SpoorAgeAdmin(admin.ModelAdmin):
    pass


@admin.register(models.SpoorFootType)
class SpoorFootTypeAdmin(admin.ModelAdmin):
    pass


@admin.register(models.SnareAction)
class SnareActionAdmin(admin.ModelAdmin):
    pass


@admin.register(models.Conservancy)
class ConservancyAdmin(BaseChoiceAdmin):
    pass


@admin.register(models.Team)
class TeamAdmin(BaseChoiceAdmin):
    pass


@admin.register(models.ActionTaken)
class ActionTakenAdmin(BaseChoiceAdmin):
    pass


@admin.register(models.Behavior)
class BehaviorAdmin(BaseChoiceAdmin):
    pass


@admin.register(models.Color)
class ColorAdmin(BaseChoiceAdmin):
    pass


@admin.register(models.ContactType)
class ContactTypeAdmin(BaseChoiceAdmin):
    pass


@admin.register(models.FenceSection)
class FenceSectionAdmin(BaseChoiceAdmin):
    pass


@admin.register(models.Health)
class HealthAdmin(BaseChoiceAdmin):
    pass


@admin.register(models.Livestock)
class LivestockAdmin(BaseChoiceAdmin):
    pass


@admin.register(models.PoachingMean)
class PoachingMeanAdmin(BaseChoiceAdmin):
    pass


@admin.register(models.Tribe)
class TribeAdmin(BaseChoiceAdmin):
    pass


@admin.register(models.WildlifeGap)
class WildlifeGapAdmin(BaseChoiceAdmin):
    pass
