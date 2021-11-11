from django.shortcuts import render
from django.views import generic
from django.urls import reverse

from .models import Position

# Create your views here.

class CreatePosition(generic.CreateView):
    model = Position
    fields = ('name', 'description', 'position_start', 'position_end',
    'reports_to', 'closes', 'application_form')
    template_name="form_crispy_cbv.html"
    permission_required="positions.add_position"
    
    def get_success_url(self):
        return reverse("accounts:me")

class ListPositions(generic.ListView):
    model = Position
    fields = ('name', 'position_start', 'position_end', 'closes')
    template_name = 'position_list.html'
    permission_required = "positions.apply"

class ViewPosition(generic.DetailView):
    model = Position
    template_name = "position_detail.html"
    permission_required = "positions.apply"
