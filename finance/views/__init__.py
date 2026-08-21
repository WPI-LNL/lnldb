""" Re-exported so ``finance/urls.py`` can refer to ``views.<name>`` uniformly. """
# flake8: noqa: F401
from finance.views.dashboard import dashboard
from finance.views.detail import entry_delete, entry_detail, transaction_detail
from finance.views.ingest import (bulk_reconcile, encumbrance, queue, reconcile, settle,
                                 suggestions_json, unreconcile, upload, upload_confirm)
from finance.views.ledger import bulk_action, ledger
from finance.views.projects import (funding_detail, funding_edit, funding_list, project_edit,
                                    project_explorer)
