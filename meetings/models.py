from django.db import models
from django.contrib.auth.models import User

# Create your models here.


class Meeting(models.Model):
    datetime = models.DateTimeField()
    attendance = models.ManyToManyField(User)
