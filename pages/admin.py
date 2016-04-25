from pages.models import *
from django.contrib import admin


class PageAdmin(admin.ModelAdmin):
    prepopulated_fields = {"slug": ("title",)}
    list_display = ('title', 'slug', 'main_nav', 'nav_pos')

    filter_horizontal = ['imgs', ]


admin.site.register(Page, PageAdmin)
admin.site.register(CarouselImg)
