# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.shortcuts import render
from .models import Endpoint


# Create your views here.
def docs(request):
    context = {
        'endpoints': Endpoint.objects.all(),
    }
    return render(request, 'api_docs.html', context)
