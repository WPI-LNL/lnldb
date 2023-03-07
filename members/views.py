from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required, permission_required
from django.http import HttpResponseRedirect
from django.shortcuts import get_object_or_404, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_GET, require_POST

from .forms import TrainingForm, TraineeNotesForm
from .models import TrainingType, Training, Trainee


@login_required
@permission_required('members.view_training', raise_exception=True)
@require_GET
def training_list(request):
    """ List all members with valid training """
    context = {}
    training_types = TrainingType.objects.all()
    context['training_types'] = training_types
    users = get_user_model().objects.filter(trainings__isnull=False).distinct()
    training_data = []
    for user in users:
        data = []
        for training_type in training_types:
            training_of_reference = None
            for training in user.trainings.filter(training__training_type=training_type).order_by('training__date'):
                if training_of_reference is None:
                    training_of_reference = training
                else:
                    if training.is_valid():
                        if not training_of_reference.is_valid() or \
                                training.training.expiration_date is None or \
                                (training_of_reference.training.expiration_date is not None and \
                                training.training.expiration_date >= training_of_reference.training.expiration_date):
                            training_of_reference = training
                    else:
                        if not training_of_reference.is_valid():
                            training_of_reference = training
            data.append(training_of_reference)
        training_data.append((user, data))
    context['training_data'] = training_data

    return render(request, 'traininglist.html', context)


@login_required
@permission_required('members.add_training', raise_exception=True)
def enter_training(request):
    """ Update training records """
    if request.method == 'POST':
        form = TrainingForm(request.POST)
        if form.is_valid():
            training = Training.objects.create(
                training_type=form.cleaned_data['training_type'],
                date=form.cleaned_data['date'],
                trainer=form.cleaned_data['trainer'],
                expiration_date=form.cleaned_data['expiration_date'],
                notes=form.cleaned_data['notes'],
                recorded_by=request.user
            )
            for uid in form.cleaned_data['trainees']:
                Trainee.objects.create(training=training, person=get_user_model().objects.get(pk=uid))
            return HttpResponseRedirect(reverse('members:training:list'))
    else:
        form = TrainingForm()
    return render(request, 'form_crispy.html', {'form': form, 'msg': "Record a Training"})


@login_required
@permission_required('members.edit_trainee_notes', raise_exception=True)
def trainee_notes(request, pk):
    """ Update trainee records for a particular individual (must not be expired) """
    trainee = get_object_or_404(Trainee, pk=pk)
    if trainee.training.is_expired():
        messages.add_message(request, messages.ERROR, 'Cannot add notes to an expired training.')
        return HttpResponseRedirect(reverse('accounts:detail', args=(trainee.person.pk,)))

    if request.method == 'POST':
        form = TraineeNotesForm(request.POST, instance=trainee)
        if form.is_valid():
            form.save()
            return HttpResponseRedirect(reverse('accounts:detail', args=(trainee.person.pk,)))
    else:
        form = TraineeNotesForm(instance=trainee)
    return render(request, 'form_crispy.html', {'form': form, 'msg':"Edit Training Notes"})


@login_required
@permission_required('members.revoke_training', raise_exception=True)
@require_POST
def revoke_training(request, pk):
    """ Revoke training for a particular user """
    trainee = get_object_or_404(Trainee, pk=pk)
    if trainee.revoked:
        messages.add_message(request, messages.ERROR, 'Cannot revoke a training that is already revoked.')
        return HttpResponseRedirect(reverse('accounts:detail', args=(trainee.person.pk,)))
    if not trainee.is_valid():
        messages.add_message(request, messages.ERROR, 'Cannot revoke a training that is not currently valid.')
        return HttpResponseRedirect(reverse('accounts:detail', args=(trainee.person.pk,)))
    trainee.revoked = True
    trainee.revoked_by = request.user
    trainee.revoked_on = timezone.now()
    trainee.save()
    return HttpResponseRedirect(reverse('accounts:detail', args=(trainee.person.pk,)))
