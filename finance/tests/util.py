"""
Helpers for the finance tests.

Spend categories, fund sources and revenue sources are rows now rather than
enum members, so tests look them up by slug. The rows themselves are created by
the seed data migration, which runs when the test database is built.
"""
import datetime

from django.utils import timezone

from finance.models import (Encumbrance, FundSource, RevenueSource, SpendCategory,
                            reset_partition_cache)


def category(slug='consumables'):
    """ A seeded :class:`SpendCategory` by slug. """
    return SpendCategory.objects.get(slug=slug)


def fund(slug='legacy'):
    return FundSource.objects.get(slug=slug)


def revenue_source(slug='donations'):
    return RevenueSource.objects.get(slug=slug)


def encumbrance(description, logged_on):
    """
    An :class:`Encumbrance` logged on ``logged_on``, which its open lines are
    dated. ``created_on`` is set on create whatever is passed, so it is moved
    afterwards.
    """
    header = Encumbrance.objects.create(description=description)
    Encumbrance.objects.filter(pk=header.pk).update(
        created_on=timezone.make_aware(datetime.datetime.combine(logged_on, datetime.time(12))))
    header.refresh_from_db()
    return header


def clear_caches():
    """
    Drop the in-memory partition codes.

    A rollback at the end of a test does not fire the signals that normally
    invalidate that cache, so a test creating its own codes would otherwise
    leak them into the next one.
    """
    reset_partition_cache()
