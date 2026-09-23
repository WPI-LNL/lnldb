"""
The finance test package.

Importing this module installs one compatibility shim, described below, before
any test runs. Everything else lives in the ``test_*`` modules, grouped here by
what they cover rather than alphabetically.

**The data model**

``test_models``
    Fiscal years, the money helper, entry types, the immutability guarantee,
    line identity, and every accounting rule enforced in ``Model.clean()``.
``test_model_details``
    The narrower model surface the pages lean on: rollups, picker labels,
    refundable balances, partition inheritance, and the derived properties that
    prefer a queryset annotation and fall back to their own query.
``test_config``
    The admin-editable vocabularies and settings -- retiring a term, the
    PROTECT guards, the singleton settings row, and cache invalidation.

**Getting data in**

``test_importers``
    Reading Workday's CSV and ``.xlsx`` exports, and deciding what is a
    duplicate.
``test_importer_parsing``
    The parsing layer on its own: encodings and the BOM, delimiter sniffing,
    the header hunt, amount and date dialects, column aliases, and the staging
    helpers behind the two-step import.
``test_ingest``
    The queue itself -- upload, confirm, reconcile, bulk reconcile, undo,
    settle, matching an encumbrance to the line that settles it, and the
    suggestion JSON endpoint.

**Deciding what a line means**

``test_suggestions``
    What the export tells us outright versus what we merely infer, and the
    rule ordering that keeps those apart.
``test_calculators``
    The dashboard's numbers.

**Forms and pages**

``test_forms``
    Field-level rules, the direction split, and what each form offers.
``test_form_rules``
    The rules that only show up in combination: cross-year funding requests,
    the fund/FR-line pairing, split formset arithmetic, and the fields each
    form deletes rather than validates.
``test_views``
    The pages, their permissions, and the flows that span several requests.
``test_ledger``
    The spreadsheet page specifically: sorting, filtering, column visibility
    and the bulk action bar.
``test_detail``
    One bank line and one entry -- splitting, deletion, and the audit trail
    reconstructed from django-reversion snapshots.

**Everything else**

``test_rollups``
    The batch figures behind the listing pages -- that each equals the
    per-row property it stands in for, and that its query count stays flat as
    rows are added -- together with the group fixture that decides whether a
    fresh install can open the app at all.

``test_admin``
    That every registered admin page loads, and that the guards on the
    read-only and singleton models hold.
``test_lookups``
    The autocomplete channels, including their permission gate and escaping.
``test_templatetags``
    The filters and tags, and in particular that each one survives being
    handed ``None`` or a non-numeric value.

``util``
    Shared fixtures and builders. Not a test module.
"""
import os
import sys


def _install_mptt_windows_shim():
    """
    Repair django-mptt's testing-generator guard on non-POSIX paths.

    ``mptt.models._check_no_testing_generators`` runs on every MPTT model
    instantiation during ``manage.py test``, and builds a label for its error
    message with ``call_file.split("/")[-2]``. A Windows path contains no
    ``/``, so the split yields a one-element list and the guard raises
    ``IndexError`` from the line that was only ever meant to name a directory.

    The effect is that every ``ProjectTag`` created in a test blows up before
    the test body runs -- twenty-nine of them here -- which is not a failing
    assertion but a whole area of this app going unexercised and unmeasured.
    ``MPTT_ALLOW_TESTING_GENERATORS`` does not help: the IndexError happens on
    the line above the one that reads the setting.

    The replacement keeps the guard exactly as intended -- refuse a model built
    by model_bakery or model_mommy unless the setting allows it, with the same
    message -- and only builds the path label in a way that works on any
    platform. It is deliberately installed from the test package rather than
    from application code: it exists solely because tests are running, and
    nothing in production ever calls it.

    Remove this when django-mptt fixes the split upstream; the guard survives
    on its own either way, because this only ever replaces a broken one.
    """
    if sys.argv[1:2] != ['test']:
        # The upstream guard only installs itself under `manage.py test`, so
        # outside that there is nothing to repair.
        return
    try:
        from django.conf import settings
        from mptt.models import MPTTModel
    except ImportError:                                     # pragma: no cover
        return

    # Untouched unless mptt actually installed the broken guard, which it only
    # does when model_bakery or model_mommy is importable.
    current = getattr(MPTTModel, '_check_no_testing_generators', None)
    if current is None or getattr(current, '_lnl_shim', False):
        return

    def _check_no_testing_generators(self):
        import inspect

        frames = inspect.getouterframes(inspect.currentframe(), 0)
        # Upstream indexes frame 5 unconditionally; a shorter stack is a
        # legitimate call, not a reason to raise from the guard itself.
        if len(frames) <= 5:
            return
        call_file = frames[5][1]
        if 'model_mommy' not in call_file and 'model_bakery' not in call_file:
            return
        if getattr(settings, 'MPTT_ALLOW_TESTING_GENERATORS', False):
            return
        # os.path rather than a hard-coded separator: the only actual bug.
        call_directory = os.path.basename(os.path.dirname(call_file))
        raise Exception(
            "The %s populates django-mptt fields with random values which leads to "
            "unpredictable behavior. If you really want to generate this model that "
            "way, please set MPTT_ALLOW_TESTING_GENERATORS=True in your settings."
            % call_directory)

    _check_no_testing_generators._lnl_shim = True
    MPTTModel._check_no_testing_generators = _check_no_testing_generators


_install_mptt_windows_shim()
