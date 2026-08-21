"""
Helpers for the finance tests.

Spend categories, fund sources and revenue sources are rows now rather than
enum members, so tests look them up by slug. The rows themselves are created by
the seed data migration, which runs when the test database is built.
"""
from finance.models import FundSource, RevenueSource, SpendCategory, reset_partition_cache


def category(slug='consumables'):
    """ A seeded :class:`SpendCategory` by slug. """
    return SpendCategory.objects.get(slug=slug)


def fund(slug='sga_budget'):
    return FundSource.objects.get(slug=slug)


def revenue_source(slug='alumni'):
    return RevenueSource.objects.get(slug=slug)


def clear_caches():
    """
    Drop the in-memory partition codes.

    A rollback at the end of a test does not fire the signals that normally
    invalidate that cache, so a test creating its own codes would otherwise
    leak them into the next one.
    """
    reset_partition_cache()
