"""
Admin registrations for the finance app.

The admin is the Treasurer's back door, not a second ledger. Day-to-day work
happens on the five finance pages; what lives here is the stuff those pages
deliberately do not expose -- the editable vocabularies, the suggestion rules,
the importer's column aliases, and read-only access to the raw bank rows for
when something needs to be looked at rather than changed.
"""
from django import forms
from django.contrib import admin
from django.utils.html import format_html
from mptt.admin import MPTTModelAdmin
from reversion.admin import VersionAdmin

from finance.importers import COLUMN_ALIASES
from finance.models import (ColumnAlias, FinanceSettings, FRLineItem, FundingRequest, FundSource,
                            ParsedTransaction, PartitionCode, ProjectTag, RevenueSource,
                            ServiceColor, SpendCategory, SuggestionRule, WorkdayTransaction)


# ---------------------------------------------------------------------------
# Editable vocabularies
#
# These are the tables a Treasurer is expected to maintain. They were hard-coded
# choice lists until it became clear they change without the code changing.
# ---------------------------------------------------------------------------

class VocabularyAdmin(admin.ModelAdmin):
    """
    Shared behaviour for the small editable lists (categories, funds, sources).

    Subclasses set ``usage_related_name`` to whichever reverse accessor points
    back at the rows using them, which is all the "Records using it" column and
    the delete guard need to work.
    """
    list_display = ('name', 'slug', 'sort_order', 'is_active', 'in_use')
    list_editable = ('sort_order', 'is_active')
    list_filter = ('is_active',)
    search_fields = ('name', 'slug')
    prepopulated_fields = {'slug': ('name',)}
    usage_related_name = 'entries'

    @admin.display(description="Records using it")
    def in_use(self, obj):
        """ How many ledger rows currently point at this term. """
        return getattr(obj, self.usage_related_name).count()

    def has_delete_permission(self, request, obj=None):
        """ Refuse to delete a term that real money is still filed under. """
        # A category still attached to real money must be retired with the
        # "active" flag rather than deleted; the FK is PROTECT, so a delete
        # would fail anyway -- better to not offer it.
        if obj is not None and getattr(obj, self.usage_related_name).exists():
            return False
        return super(VocabularyAdmin, self).has_delete_permission(request, obj)


class SuggestionRuleInline(admin.TabularInline):
    """ Edit a category's auto-suggest rules on the category's own page. """
    model = SuggestionRule
    extra = 0
    fields = ('match_field', 'match_mode', 'pattern', 'confidence', 'priority',
              'is_active', 'notes')


@admin.register(SpendCategory)
class SpendCategoryAdmin(VocabularyAdmin):
    """ LNL's own spending buckets, each with the colour it charts in. """
    list_display = ('name', 'swatch', 'slug', 'sort_order', 'is_active', 'in_use', 'rule_count')
    fields = ('name', 'slug', 'color', 'description', 'sort_order', 'is_active')
    inlines = (SuggestionRuleInline,)

    @admin.display(description="Colour")
    def swatch(self, obj):
        """ Preview the category colour next to its hex value. """
        return format_html(
            '<span style="display:inline-block;width:14px;height:14px;border-radius:3px;'
            'border:1px solid rgba(0,0,0,.2);background:{}"></span> <code>{}</code>',
            obj.color, obj.color)

    @admin.display(description="Auto-suggest rules")
    def rule_count(self, obj):
        """ How many suggestion rules point at this category. """
        return obj.suggestion_rules.count()


@admin.register(FundSource)
class FundSourceAdmin(VocabularyAdmin):
    """
    Where the money came from, and the Workday fund codes that imply it.

    ``requires_funding_request`` is the one flag with teeth: it is what makes
    the allocation form insist on an SGA request number.
    """
    list_display = ('name', 'slug', 'workday_fund_codes', 'requires_funding_request',
                    'sort_order', 'is_active', 'in_use')
    fields = ('name', 'slug', 'description', 'workday_fund_codes',
              'requires_funding_request', 'sort_order', 'is_active')


@admin.register(RevenueSource)
class RevenueSourceAdmin(VocabularyAdmin):
    """ Where incoming money came from -- clients, grants, cost recovery. """
    fields = ('name', 'slug', 'description', 'sort_order', 'is_active')


@admin.register(SuggestionRule)
class SuggestionRuleAdmin(admin.ModelAdmin):
    """
    The pattern table behind the queue's reconciliation suggestions.

    Rules are data rather than code precisely so a Treasurer can teach the
    queue about a new vendor or account without a deploy. Editing ``priority``
    from the list is the usual way to settle a rule that fires too eagerly.
    """
    list_display = ('pattern', 'match_field', 'match_mode', 'fills_in', 'spend_category',
                    'priority', 'is_active')
    list_editable = ('priority', 'is_active')
    list_filter = ('match_field', 'match_mode', 'confidence', 'is_active', 'spend_category')
    search_fields = ('pattern', 'notes')
    list_select_related = ('spend_category',)

    @admin.display(description="Fills the form in", boolean=True)
    def fills_in(self, obj):
        """ Whether a match is treated as evidence or merely offered as a chip. """
        return obj.is_lookup


@admin.register(PartitionCode)
class PartitionCodeAdmin(admin.ModelAdmin):
    """ The worktags that pin a transaction to Event Production or Projection. """
    list_display = ('code', 'partition', 'worktag')
    list_filter = ('is_projection',)
    search_fields = ('code', 'notes')

    @admin.display(description="Locks money to", boolean=False)
    def partition(self, obj):
        """ Spell out which side of the partition this code locks money to. """
        return 'Projection' if obj.is_projection else 'Event Production'


# ---------------------------------------------------------------------------
# Ledger
# ---------------------------------------------------------------------------

@admin.register(WorkdayTransaction)
class WorkdayTransactionAdmin(admin.ModelAdmin):
    """
    Read-only by design. These rows are the bank's record; the model itself
    refuses updates and deletes, so the admin reflects that rather than
    offering buttons that will raise.
    """
    list_display = ('operational_transaction', 'accounting_date', 'net_amount', 'payee',
                    'ledger_account', 'defaults_to_projection')
    list_filter = ('accounting_date',)
    search_fields = ('operational_transaction', 'supplier', 'employee', 'memo')
    date_hierarchy = 'accounting_date'
    readonly_fields = [f.name for f in WorkdayTransaction._meta.fields]

    def has_add_permission(self, request):
        """ Never: rows arrive only via the CSV importer. """
        return False

    def has_change_permission(self, request, obj=None):
        """ Never: the bank's record is not ours to edit. """
        return False

    def has_delete_permission(self, request, obj=None):
        """ Never: the model itself raises on delete. """
        return False

    @admin.display(boolean=True, description="Projection by default")
    def defaults_to_projection(self, obj):
        """ Whether this row's worktags put it on the Projection side. """
        return obj.defaults_to_projection


class FRLineItemInline(admin.TabularInline):
    """ The individual awarded amounts that make up a funding request. """
    model = FRLineItem
    extra = 1


@admin.register(FundingRequest)
class FundingRequestAdmin(VersionAdmin):
    """ SGA funding requests, versioned so award changes stay traceable. """
    list_display = ('name', 'reference', 'fiscal_year', 'total_awarded', 'total_spent',
                    'total_remaining', 'closed')
    list_filter = ('fiscal_year', 'closed', 'is_projection')
    search_fields = ('name', 'reference')
    inlines = (FRLineItemInline,)


@admin.register(ProjectTag)
class ProjectTagAdmin(MPTTModelAdmin, VersionAdmin):
    """
    The project tag forest.

    ``MPTTModelAdmin`` comes first so the changelist renders the tree indented;
    ``VersionAdmin`` behind it keeps the history of every reparent.
    """
    list_display = ('name', 'code', 'parent', 'is_projection', 'archived')
    list_filter = ('is_projection', 'archived')
    search_fields = ('name', 'code')
    prepopulated_fields = {'code': ('name',)}


@admin.register(ParsedTransaction)
class ParsedTransactionAdmin(VersionAdmin):
    """
    Raw access to ledger entries, for repairs the finance pages will not do.

    ``raw_id_fields`` rather than dropdowns on the three FKs: each points at a
    table with tens of thousands of rows, and rendering a ``<select>`` over
    them would time the page out.
    """
    list_display = ('__str__', 'effective_date', 'amount', 'status', 'is_projection',
                    'lnl_spend_category', 'project_tag')
    list_filter = ('status', 'is_projection', 'fund_source', 'lnl_spend_category')
    search_fields = ('description', 'audit_explanation',
                     'parent_transaction__operational_transaction')
    raw_id_fields = ('parent_transaction', 'linked_event', 'refund_of')
    list_select_related = ('lnl_spend_category', 'project_tag')
    date_hierarchy = 'effective_date'


# ---------------------------------------------------------------------------
# Settings that used to live in code
# ---------------------------------------------------------------------------

@admin.register(FinanceSettings)
class FinanceSettingsAdmin(admin.ModelAdmin):
    """ One row, so the changelist goes straight to it and neither adds nor deletes. """

    def has_add_permission(self, request):
        """ Only while the singleton row does not exist yet. """
        return not FinanceSettings.objects.exists()

    def has_delete_permission(self, request, obj=None):
        """ Never: half the app reads these values on every request. """
        return False

    def changelist_view(self, request, extra_context=None):
        """ Skip the one-row list and open the settings form directly. """
        from django.shortcuts import redirect
        from django.urls import reverse
        settings_row = FinanceSettings.load()
        return redirect(reverse('admin:finance_financesettings_change',
                                args=[settings_row.pk]))


@admin.register(ServiceColor)
class ServiceColorAdmin(admin.ModelAdmin):
    """
    Chart colours for the events app's service categories.

    A category with no row here falls back to the shared ramp, so this table
    only needs the services worth pinning to a recognisable colour.
    """
    list_display = ('category', 'swatch', 'color')
    list_select_related = ('category',)

    @admin.display(description="Colour")
    def swatch(self, obj):
        """ Preview the colour this service will chart in. """
        return format_html(
            '<span style="display:inline-block;width:34px;height:14px;border-radius:3px;'
            'border:1px solid rgba(0,0,0,.2);background:{};"></span>', obj.color)


@admin.register(ColumnAlias)
class ColumnAliasAdmin(admin.ModelAdmin):
    """
    Maps a Workday column heading onto the field the importer reads it into.

    This is the escape hatch for the day Workday renames a column: add the new
    heading here and the next upload parses without a deploy.
    """
    list_display = ('alias', 'canonical', 'notes')
    search_fields = ('alias', 'canonical')

    def formfield_for_dbfield(self, db_field, request, **kwargs):
        """
        Offer the importer's own field names for the canonical side.

        Typing it by hand means a single character can point an alias at a
        column nothing reads, and the symptom is a silent one -- the import
        succeeds and the value lands in worktags instead of the field.

        The field is constructed here rather than by adding ``choices`` to
        ``kwargs``. ``CharField.formfield()`` hands its own arguments to the
        form field it builds, and a plain ``forms.CharField`` accepts no
        ``choices`` while a choice field accepts no ``max_length`` -- so going
        through it raised ``TypeError`` either way, and this page was a 500.
        On the one form whose entire job is being reachable the day Workday
        renames a column, which is a day nobody schedules.
        """
        if db_field.name == 'canonical':
            # Built and returned outright rather than handed to
            # ``CharField.formfield()``, which injects ``max_length`` -- an
            # argument no choice field accepts.
            return forms.ChoiceField(
                choices=[(name, name.replace('_', ' ').title())
                         for name in sorted(COLUMN_ALIASES)],
                required=not db_field.blank,
                label=db_field.verbose_name.capitalize(),
                help_text=db_field.help_text,
                widget=admin.widgets.AdminRadioSelect(attrs={'class': 'inline'}))
        return super(ColumnAliasAdmin, self).formfield_for_dbfield(db_field, request, **kwargs)
