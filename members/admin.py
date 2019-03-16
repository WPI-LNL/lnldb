from django.contrib import admin

from . import models

class TrainingTypeAdmin(admin.ModelAdmin):
    list_display = 'name', 'external'

class TraineeInline(admin.StackedInline):
    model = models.Trainee
    extra = 0

class TrainingAdmin(admin.ModelAdmin):
    inlines = TraineeInline,
    readonly_fields = 'recorded_by', 'recorded_on'
    fields = 'recorded_by', 'recorded_on', 'training_type', 'date', 'trainer', 'expiration_date', 'notes'

    def get_readonly_fields(self, request, obj=None):
        if obj: # editing an existing object
            return self.readonly_fields + ('training_type',)
        return self.readonly_fields

    def save_model(self, request, obj, form, change):
        if obj.recorded_by is None:
            obj.recorded_by = request.user
        obj.save()

admin.site.register(models.TrainingType, TrainingTypeAdmin)
admin.site.register(models.Training, TrainingAdmin)