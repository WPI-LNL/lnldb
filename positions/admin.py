from django.contrib import admin

from .models import Position

# Register your models here.

class PositionAdmin(admin.ModelAdmin):
   fields = (
           'name',
           'description'
           )

admin.site.register(Position, PositionAdmin)
