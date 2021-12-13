from django.shortcuts import render
from django.views import generic
from django.urls import reverse
import datetime

from .models import Position
from .forms import UpdateCreatePosition

from django.contrib.auth.mixins import PermissionRequiredMixin, LoginRequiredMixin

# Create your views here.

class CreatePosition(PermissionRequiredMixin, LoginRequiredMixin, generic.CreateView):
    model = Position
    form_class = UpdateCreatePosition
    template_name="form_crispy_cbv.html"
    permission_required="positions.add_position"
    
    def get_success_url(self):
        return reverse("accounts:me")

class UpdatePosition(PermissionRequiredMixin, LoginRequiredMixin, generic.UpdateView):
    model = Position
    template_name="form_crispy_cbv.html"
    permission_required="positions.change_position"
    form_class = UpdateCreatePosition

    def get_success_url(self):
        return reverse("positions:detail", args=[self.object.id])

class ListPositions(PermissionRequiredMixin, LoginRequiredMixin, generic.ListView):
    model = Position
    queryset = Position.objects.filter(closes__gte=datetime.datetime.now())
    fields = ('name', 'position_start', 'position_end', 'closes')
    template_name = 'position_list.html'
    permission_required = "positions.apply"

class ViewPosition(PermissionRequiredMixin, LoginRequiredMixin, generic.DetailView):
    model = Position
    template_name = "position_detail.html"
    permission_required = "positions.apply"
