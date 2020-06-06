from django.contrib import admin

from pages import models


class PageAdmin(admin.ModelAdmin):
    prepopulated_fields = {"slug": ("title",)}
    list_display = ('title', 'slug', 'noindex')

    filter_horizontal = ['imgs', ]


admin.site.register(models.Page, PageAdmin)
admin.site.register(models.CarouselImg)
