from django.contrib import admin

from pages import models


class PageAdmin(admin.ModelAdmin):
    prepopulated_fields = {"slug": ("title",)}
    list_display = ('title', 'slug', 'noindex')

    filter_horizontal = ['imgs', ]


class ScreenAdmin(admin.ModelAdmin):
    prepopulated_fields = {"slug": ("title",)}
    list_display = ('title', 'slug')


admin.site.register(models.Page, PageAdmin)
admin.site.register(models.CarouselImg)
admin.site.register(models.OnboardingScreen, ScreenAdmin)
admin.site.register(models.OnboardingRecord)
