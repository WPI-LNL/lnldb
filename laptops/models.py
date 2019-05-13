from django.conf import settings
from django.db import models
from django.utils.encoding import python_2_unicode_compatible

@python_2_unicode_compatible
class Laptop(models.Model):
    name = models.CharField(max_length=20)
    description = models.TextField(blank=True)
    api_key_hash = models.CharField(max_length=64, db_index=True, verbose_name='API key hash', help_text='SHA-256 hash of the API key that the laptop uses when it changes its passwords')
    user_password = models.CharField(max_length=25)
    admin_password = models.CharField(max_length=25)
    retired = models.BooleanField(default=False)

    class Meta:
        permissions = (
            ('view_laptop', 'View details of a laptop'),
            ('view_laptop_history', 'View password retrieval history for a laptop'),
            ('retrieve_user_password', 'Retrieve the user password for a laptop'),
            ('retrieve_admin_password', 'Retrieve the admin password for a laptop'),
        )

    def __str__(self):
        return self.name

class LaptopPasswordRetrieval(models.Model):
    timestamp = models.DateTimeField(auto_now_add=True)
    laptop = models.ForeignKey(Laptop, on_delete=models.CASCADE, related_name='password_retrievals')
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    admin = models.BooleanField()

class LaptopPasswordRotation(models.Model):
    timestamp = models.DateTimeField(auto_now_add=True)
    laptop = models.ForeignKey(Laptop, on_delete=models.CASCADE, related_name='password_rotations')
