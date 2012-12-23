from django.forms import ModelForm
from inventory.models import Equipment

class InvForm(ModelForm):
    class Meta:
        model = Equipment