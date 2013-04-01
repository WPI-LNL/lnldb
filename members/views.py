# Create your views here.
from django.core.urlresolvers import reverse
from django.http import HttpResponse, HttpResponseRedirect
from django.shortcuts import render_to_response, get_object_or_404
from django.template import Context,RequestContext

from django.contrib.auth.models import User

def officers(request):
    context = RequestContext(request)
    users = User.objects.filter(groups__name='Officer').order_by('username')
    
    context['users'] = users
    context['h2'] = "Officer List"
    
    return render_to_response('users.html', context)

def active(request):
    context = RequestContext(request)
    users = User.objects.filter(groups__name='Active').order_by('username')
    
    context['users'] = users
    context['h2'] = "Active Members"
    
    return render_to_response('users.html', context)

def associate(request):
    context = RequestContext(request)
    users = User.objects.filter(groups__name='Associate').order_by('username')
    
    context['users'] = users
    context['h2'] = "Associate Members"
    
    return render_to_response('users.html', context)

def alum(request):
    context = RequestContext(request)
    users = User.objects.filter(groups__name='Alumni').order_by('username')
    
    context['users'] = users
    context['h2'] = "Alumni Members"
    
    return render_to_response('users.html', context)


def away(request):
    context = RequestContext(request)
    users = User.objects.filter(groups__name='Away').order_by('username')
    
    context['users'] = users
    context['h2'] = "Inactive Members"
    
    return render_to_response('users.html', context)


def detail(request,id):
    context = RequestContext(request)
    user = get_object_or_404(User,pk=id)
    
    context['u'] = user
    return render_to_response('userdetail.html', context)