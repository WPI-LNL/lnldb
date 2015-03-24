from django.db import models
from django.contrib.auth.models import User
from django.contrib.auth.models import Group
from django.db.models.signals import pre_save

# Create your models here.


class StatusChange(models.Model):
    member = models.ForeignKey(User, related_name="statuschange")
    groups = models.ManyToManyField(Group, related_name="statuschange")
    date = models.DateTimeField(auto_now_add=True)

    @property
    def group_list(self):
        return ",".join(x.name[0:3] for x in self.groups.all())

    class Meta:
        ordering = ["-date"]


def update_status(sender, instance, raw=False, **kwargs):
    if instance.id and not raw:
        old = User.objects.get(pk=instance.id)
        oldgroups = old.groups.values_list('id', flat=True)
        newgroups = instance.groups.values_list('id', flat=True)
        if newgroups != oldgroups:
            s = StatusChange.objects.create(member=instance)
            s.groups = instance.groups.all()
            s.save()
            # print update_fields
            # adfad


pre_save.connect(update_status, sender=User)