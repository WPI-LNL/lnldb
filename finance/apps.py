"""
App configuration for the financial subledger.

The only real work here is wiring up cache invalidation; see
:meth:`FinanceConfig.ready` for why the settings tables are cached at all.
"""
from django.apps import AppConfig
from django.db.models.signals import post_delete, post_save


class FinanceConfig(AppConfig):
    """ Registers the finance app and its cache-invalidation signals. """
    name = 'finance'
    verbose_name = "Financial Subledger"
    default_auto_field = 'django.db.models.AutoField'

    def ready(self):
        """
        Drop the in-memory copies of the settings tables whenever one changes.

        A few tables are read on paths hot enough to cache -- the partition
        lock runs on every save, the fiscal year on every row of every page --
        so they are held in module state. Without these signals an admin edit
        would appear to do nothing until the next restart, which is a far worse
        failure than the query it saves.
        """
        from finance import models as finance_models

        cached_models = {
            'PartitionCode': 'codes',
            'FinanceSettings': 'config',
            'ServiceColor': 'service_colors',
            'ColumnAlias': 'column_aliases',
            'SpendCategory': 'event_passthrough',
            'FundSource': 'fund_codes',
        }

        for model_name, cache_key in cached_models.items():
            model = getattr(finance_models, model_name)

            def _invalidate(sender, key=cache_key, **kwargs):
                finance_models.reset_finance_cache(key)

            post_save.connect(_invalidate, sender=model,
                              dispatch_uid='finance.cache_save.%s' % model_name)
            post_delete.connect(_invalidate, sender=model,
                                dispatch_uid='finance.cache_delete.%s' % model_name)
