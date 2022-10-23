from django.db import models
from django.conf import settings

# Create your models here.

class Key(models.Model):
    key_eeprom_id = models.CharField(max_length=32, null=False, blank=False,
                                     verbose_name="Key EEPROM ID")
    pretty_name = models.CharField(max_length=32, null=False, blank=False,
                                   verbose_name="Display Name")
    

class KeyAuditEvent(models.Model):
    timestamp = models.DateTimeField(verbose_name="Time Logged", blank=False,
                                     null=False)
    card_id = models.CharField(verbose_name="HID Card ID", blank=True,
                               null=True, max_length=32)
    user_id = models.ForeignKey(settings.AUTH_USER_MODEL,
                                on_delete=models.PROTECT,
                                related_name="key_audit")
    event_type = models.CharField(verbose_name="Audit Type", blank=False,
                                  null=False, max_length=16)
    key_id = models.ForeignKey(Key, verbose_name="Key", blank=True, null=True,
                               on_delete=models.PROTECT,
                               related_name="audit_events")
    misc_text = models.TextField(verbose_name="Notes", blank=True, null=True)
