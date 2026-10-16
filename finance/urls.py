"""
URL map for the subledger.

The five numbered blocks are the pages the app started with, in the order a
Treasurer normally walks them: look at the dashboard, scan the ledger, clear the
queue, drill into a line, then check a project tag. The blocks after them came
as the app grew: what each event made, fund balances and the year end, funding
requests, reports, the forecast with the history it learns from, and billing
events, which moved here from the events app. Anything
reached only from inside a page (bulk actions, JSON endpoints) is grouped under
the page that links to it. The pages, and the permission each needs, are listed
in ``docs/reference/finance.rst`` under *The pages*.
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

    # What each event made or lost
    re_path(r'^events/$', views.event_pnl, name="events"),

    # What each fund holds, and the year-end close
    re_path(r'^balances/$', views.balance_sheet, name="balances"),
    re_path(r'^balances/workday/new/$', views.checkpoint_new, name="checkpoint-new"),
    re_path(r'^balances/workday/(?P<pk>\d+)/delete/$', views.checkpoint_delete,
            name="checkpoint-delete"),
    re_path(r'^balances/transfer/new/$', views.transfer_new, name="transfer-new"),
    re_path(r'^balances/transfer/(?P<pk>\d+)/delete/$', views.transfer_delete,
            name="transfer-delete"),
    re_path(r'^balances/opening/$', views.opening_balances, name="opening-balances"),
    re_path(r'^balances/close/(?P<fiscal_year>\d{4})/$', views.close_year, name="close-year"),
    re_path(r'^balances/close/(?P<fiscal_year>\d{4})/reopen/$', views.reopen_year,
            name="reopen-year"),

    # Funding requests
    re_path(r'^funding/$', views.funding_list, name="fr-list"),
    re_path(r'^funding/new/$', views.funding_edit, name="fr-new"),
    re_path(r'^funding/(?P<pk>\d+)/$', views.funding_detail, name="fr-detail"),
    re_path(r'^funding/(?P<pk>\d+)/edit/$', views.funding_edit, name="fr-edit"),

    # Reports to print and download
    re_path(r'^reports/$', views.report_list, name="reports"),
    re_path(r'^reports/(?P<slug>[a-z-]+)/$', views.report, name="report"),

    # Where the money is heading, and the past it is worked out from
    re_path(r'^forecast/$', views.forecast_page, name="forecast"),
    re_path(r'^forecast/afford/$', views.afford, name="afford"),
    re_path(r'^forecast/plans/$', views.plans, name="plans"),
    re_path(r'^forecast/plans/new/$', views.plan_edit, name="plan-new"),
    re_path(r'^forecast/plans/(?P<pk>\d+)/$', views.plan_edit, name="plan-edit"),
    re_path(r'^forecast/plans/(?P<pk>\d+)/delete/$', views.plan_delete, name="plan-delete"),
    re_path(r'^forecast/history/$', views.history_page, name="history"),
    re_path(r'^forecast/history/(?P<fiscal_year>\d{4})/$', views.history_year,
            name="history-year"),
    re_path(r'^forecast/history/line/(?P<pk>\d+)/$', views.history_line, name="history-line"),

    # Billing an event: the Billing page, bills, multi-bills, the worktag and
    # ISD each is charged to, and events that need no bill. The client's own
    # worktag form stays in the events app, where the links in every bill email
    # already sent point.
    re_path(r'^billing/$', views.billing_page, name="billing"),
    re_path(r'^billing/event/(?P<event>\d+)/new/$', views.BillingCreate.as_view(), name="bill-new"),
    re_path(r'^billing/event/(?P<event>\d+)/(?P<pk>\d+)/edit/$', views.BillingUpdate.as_view(),
            name="bill-edit"),
    re_path(r'^billing/event/(?P<event>\d+)/(?P<pk>\d+)/delete/$', views.BillingDelete.as_view(),
            name="bill-delete"),
    re_path(r'^billing/event/(?P<event>\d+)/(?P<billing>\d+)/email/$',
            views.BillingEmailCreate.as_view(), name="bill-email"),
    re_path(r'^billing/event/(?P<event>\d+)/(?P<pk>\d+)/paid/$', views.bill_mark_paid, name="bill-paid"),
    re_path(r'^billing/event/(?P<event>\d+)/(?P<pk>\d+)/unpaid/$', views.bill_mark_unpaid, name="bill-unpaid"),
    re_path(r'^billing/event/(?P<event>\d+)/(?P<pk>\d+)/worktag/$', views.bill_worktag, name="bill-worktag"),
    re_path(r'^billing/event/(?P<event>\d+)/(?P<pk>\d+)/isd/$', views.bill_isd, name="bill-isd"),
    re_path(r'^billing/event/(?P<event>\d+)/no-bill-needed/$', views.no_bill_needed, name="no-bill-needed"),
    re_path(r'^billing/event/(?P<event>\d+)/no-bill-needed/undo/$', views.no_bill_needed_undo,
            name="no-bill-needed-undo"),
    re_path(r'^billing/multibills/$', views.multibill_list, name="multibill-list"),
    re_path(r'^billing/multibills/new/$', views.multibill_edit, name="multibill-new"),
    re_path(r'^billing/multibills/(?P<pk>\d+)/$', views.multibill_detail, name="multibill-detail"),
    re_path(r'^billing/multibills/(?P<pk>\d+)/edit/$', views.multibill_edit, name="multibill-edit"),
    re_path(r'^billing/multibills/(?P<pk>\d+)/delete/$', views.MultiBillingDelete.as_view(),
            name="multibill-delete"),
    re_path(r'^billing/multibills/(?P<pk>\d+)/charges/new/$', views.multibill_charge,
            name="multibill-charge-new"),
    re_path(r'^billing/multibills/(?P<pk>\d+)/charges/(?P<charge_pk>\d+)/$', views.multibill_charge,
            name="multibill-charge-edit"),
    re_path(r'^billing/multibills/(?P<pk>\d+)/charges/(?P<charge_pk>\d+)/delete/$',
            views.multibill_charge_delete, name="multibill-charge-delete"),
    re_path(r'^billing/multibills/(?P<pk>\d+)/update-total/$', views.multibill_update_total,
            name="multibill-update-total"),
    re_path(r'^billing/multibills/(?P<pk>\d+)/paid/$', views.multibill_mark_paid, name="multibill-paid"),
    re_path(r'^billing/multibills/(?P<pk>\d+)/unpaid/$', views.multibill_mark_unpaid,
            name="multibill-unpaid"),
    re_path(r'^billing/multibills/(?P<pk>\d+)/worktag/$', views.multibill_worktag, name="multibill-worktag"),
    re_path(r'^billing/multibills/(?P<pk>\d+)/isd/$', views.multibill_isd, name="multibill-isd"),
    re_path(r'^billing/multibills/(?P<multibilling>\d+)/email/$',
            views.MultiBillingEmailCreate.as_view(), name="multibill-email"),
    re_path(r'^billing/multibills/(?P<multibilling>\d+)/pdf/$', views.generate_multibill_pdf,
            name="multibill-pdf"),
]
