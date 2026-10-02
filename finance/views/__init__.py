""" Re-exported so ``finance/urls.py`` can refer to ``views.<name>`` uniformly. """
# flake8: noqa: F401
from finance.views.balances import (balance_sheet, checkpoint_delete, checkpoint_new,
                                    close_year, opening_balances, reopen_year, transfer_delete,
                                    transfer_new)
from finance.views.dashboard import dashboard
from finance.views.detail import entry_delete, entry_detail, transaction_detail
from finance.views.events import event_pnl, mark_bill_paid
from finance.views.forecast import (afford, forecast_page, history_line, history_page,
                                    history_year, plan_delete, plan_edit, plans)
from finance.views.ingest import (bulk_match_encumbrance, bulk_reconcile, encumbrance,
                                 match_encumbrance, queue, reconcile, settle,
                                 suggestions_json, unreconcile, upload, upload_confirm)
from finance.views.ledger import bulk_action, ledger
from finance.views.projects import (funding_detail, funding_edit, funding_list, project_edit,
                                    project_explorer)
from finance.views.reports import report, report_list
