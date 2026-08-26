"""
URL map for the subledger.

The five numbered comments below match the five pages the app is built around,
and the order here is the order a Treasurer normally walks them: look at the
dashboard, scan the ledger, clear the queue, drill into a line, then check a
project tag. Anything reached only from inside one of those pages (bulk
actions, JSON endpoints) is grouped under the page that links to it.
"""
from django.urls import re_path

from finance import views

app_name = 'finance'

urlpatterns = [
    # Page 1 -- executive dashboard
    re_path(r'^$', views.dashboard, name="dashboard"),

    # Page 2 -- spreadsheet ledger
    re_path(r'^ledger/$', views.ledger, name="ledger"),
    re_path(r'^ledger/bulk/$', views.bulk_action, name="bulk-action"),

    # Page 3 -- ingestion queue & reconciliation
    re_path(r'^queue/$', views.queue, name="queue"),
    re_path(r'^queue/upload/$', views.upload, name="upload"),
    re_path(r'^queue/upload/confirm/$', views.upload_confirm, name="upload-confirm"),
    re_path(r'^queue/bulk/$', views.bulk_reconcile, name="bulk-reconcile"),
    re_path(r'^queue/bulk/encumbrance/$', views.bulk_match_encumbrance,
            name="bulk-match-encumbrance"),
    re_path(r'^queue/(?P<pk>\d+)/reconcile/$', views.reconcile, name="reconcile"),
    re_path(r'^queue/(?P<pk>\d+)/undo/$', views.unreconcile, name="unreconcile"),
    re_path(r'^queue/(?P<pk>\d+)/settle/$', views.settle, name="settle"),
    re_path(r'^queue/(?P<pk>\d+)/match-encumbrance/$', views.match_encumbrance,
            name="match-encumbrance"),
    re_path(r'^queue/(?P<pk>\d+)/suggestions/$', views.suggestions_json, name="suggestions"),
    re_path(r'^encumbrance/new/$', views.encumbrance, name="encumbrance-new"),
    re_path(r'^encumbrance/(?P<pk>\d+)/$', views.encumbrance, name="encumbrance-edit"),

    # Page 4 -- line item detail & splitting
    re_path(r'^transaction/(?P<pk>\d+)/$', views.transaction_detail, name="txn-detail"),
    re_path(r'^entry/(?P<pk>\d+)/$', views.entry_detail, name="entry-detail"),
    re_path(r'^entry/(?P<pk>\d+)/delete/$', views.entry_delete, name="entry-delete"),

    # Page 5 -- project tag explorer
    re_path(r'^projects/$', views.project_explorer, name="projects"),
    re_path(r'^projects/(?P<pk>\d+)/$', views.project_explorer, name="projects-detail"),
    re_path(r'^projects/new/$', views.project_edit, name="project-new"),
    re_path(r'^projects/(?P<pk>\d+)/edit/$', views.project_edit, name="project-edit"),

    # Funding requests
    re_path(r'^funding/$', views.funding_list, name="fr-list"),
    re_path(r'^funding/new/$', views.funding_edit, name="fr-new"),
    re_path(r'^funding/(?P<pk>\d+)/$', views.funding_detail, name="fr-detail"),
    re_path(r'^funding/(?P<pk>\d+)/edit/$', views.funding_edit, name="fr-edit"),
]
