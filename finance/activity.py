"""
What LNL's work was worth, and who it was for, read from the events app.

The ledger knows what was paid. This module answers a different question --
what LNL *did* -- from the events lnldb holds: every approved event that has
run, priced at its own price list whether or not anybody was charged for it.
From FY27 student organizations are not billed at all, so their shows bring in
nothing, but the work and the wear on the gear are the same as a department's
show. Comparing what each kind of client used means pricing every show.

**Service value** is what the events app would charge for LNL's own services
and extras, after its discounts and fees: ``Event2019.lnl_services_subtotal``.
It leaves out two things the client may also be charged for, because neither is
LNL's work or LNL's gear: hired-in gear (passed through at cost, plus a fee)
and one-off charges.

Pricing one show through the model costs a query for every service on it, and
a report prices hundreds. :class:`PriceBook` loads every price once and
:func:`load_work` works the same figures out in memory, line by line, with the
discounts and fees shared out across the lines they apply to so that each
service, each category and each show add up to the cent. The arithmetic
mirrors the events app's; ``finance.tests.test_activity`` holds the two
together.
"""
import datetime
import decimal
from collections import OrderedDict, namedtuple

from django.utils import timezone

from finance.models import ZERO, ClientType, client_of, client_type_for, money

#: Who a show was for, as the reports group them. A client on the student
#: organization Workday fund (810, set in the Finance Configuration) is a
#: student organization; any other fund is a department or an outside client
#: billed at full rates; no fund on the event or its client cannot be placed.
#: See :func:`finance.models.client_type_for`.
CLIENT_GROUPS = OrderedDict((
    (ClientType.STUDENT_ORG, 'Student organizations'),
    (ClientType.DEPARTMENT, 'Departments and external'),
    (ClientType.UNKNOWN, 'Not classified'),
))


# ---------------------------------------------------------------------------
# WPI terms
#
# WPI's year is four seven-week terms, A and B in the fall and C and D in the
# spring, and E over the summer. The exact dates move by a few days each year,
# so each term here starts on a fixed day that sits in the break before it: an
# event is only put in the wrong term if it falls in the days a break moved by.
# New student orientation, in mid-August, counts as A term.
# ---------------------------------------------------------------------------

#: ``(term letter, month, day)`` each term starts on, in calendar order.
TERM_STARTS = (('C', 1, 1), ('D', 3, 10), ('E', 5, 20), ('A', 8, 15), ('B', 10, 15))

Term = namedtuple('Term', 'code first last')


def term_for(day):
    """ The :class:`Term` a date falls in, e.g. ``A25`` for Sep 3, 2025. """
    starts = [(letter, datetime.date(day.year, month, date))
              for letter, month, date in TERM_STARTS]
    index = max(i for i, (_, start) in enumerate(starts) if start <= day)
    letter, first = starts[index]
    if index + 1 < len(starts):
        last = starts[index + 1][1] - datetime.timedelta(days=1)
    else:
        last = datetime.date(day.year, 12, 31)
    return Term('%s%02d' % (letter, day.year % 100), first, last)


def terms_between(first, last):
    """ Every term that starts on or before ``last`` and ends on or after ``first``. """
    terms, day = [], first
    while day <= last:
        term = term_for(day)
        terms.append(term)
        day = term.last + datetime.timedelta(days=1)
    return terms


# ---------------------------------------------------------------------------
# Pricing
# ---------------------------------------------------------------------------

CENT = decimal.Decimal('0.01')

#: The categories the events app's original discount covers: 15% off these
#: services, and every extra, on a show that has both lighting and sound.
OLD_DISCOUNT_CATEGORIES = ('Lighting', 'Sound', 'Rigging', 'Power')
OLD_DISCOUNT_RATE = decimal.Decimal('.15')


class PriceBook(object):
    """ Every price-list price, discount and fee rate, loaded once. """

    def __init__(self):
        from events.models import DiscountPrice, ExtraPrice, FeePrice, ServicePrice

        self.services = {(row.service_id, row.pricelist_id): row.cost
                         for row in ServicePrice.objects.all()}
        self.extras = {(row.extra_id, row.pricelist_id): row.cost
                       for row in ExtraPrice.objects.all()}
        self.discounts = {(row.discount_id, row.pricelist_id): row.percent
                          for row in DiscountPrice.objects.all()}
        self.fees = {(row.fee_id, row.pricelist_id): row.percent
                     for row in FeePrice.objects.all()}


class Line(object):
    """
    One priced thing on a show: a service, or an extra and how many of it.

    ``amount`` is its price; ``net`` is its price after its share of the
    show's discounts and fees, so the lines of a show add up to its value.
    """

    SERVICE, EXTRA = 'service', 'extra'

    def __init__(self, kind, item, category, quantity, amount):
        self.kind = kind
        self.item = item
        self.category = category
        self.quantity = quantity
        self.amount = amount
        self.net = amount

    @property
    def key(self):
        """ What the line is, across shows: ``('service', pk)`` or ``('extra', pk)``. """
        return (self.kind, self.item.pk)

    @property
    def category_name(self):
        return self.category.name if self.category is not None else 'Other'


def _allocate(amount, weights):
    """
    ``amount`` split across ``weights`` in proportion, to the cent, adding up
    to ``amount`` exactly: each part is rounded down and the cents left over
    go to the parts that lost the most to rounding.
    """
    total = sum(weights, ZERO)
    if not total:
        return [ZERO for _ in weights]
    cents = int((amount / CENT).to_integral_value())
    raw = [decimal.Decimal(cents) * weight / total for weight in weights]
    parts = [int(share) for share in raw]
    left = cents - sum(parts)
    for index in sorted(range(len(raw)), key=lambda i: parts[i] - raw[i])[:left]:
        parts[index] += 1
    return [decimal.Decimal(part) * CENT for part in parts]


def _share_out(lines, amount, sign):
    """ Take ``amount`` off (``sign`` -1) or add it to (+1) ``lines``, by price. """
    for line, part in zip(lines, _allocate(amount, [line.amount for line in lines])):
        line.net += sign * part


def _percent_of(total, percent):
    """ A discount or fee, as the events app works it out: rounded down to the cent. """
    value = total * decimal.Decimal(percent) / decimal.Decimal('100')
    return value.quantize(CENT, rounding=decimal.ROUND_DOWN)


def _lines_2019(event, book):
    """ A 2019 event's services and extras, priced and with discounts and fees shared out. """
    pricelist = event.pricelist_id
    lines = []
    for instance in event.serviceinstance_set.all():
        service = instance.service
        cost = book.services.get((service.pk, pricelist)) if pricelist else None
        lines.append(Line(Line.SERVICE, service, service.category, 1,
                          service.base_cost if cost is None else cost))
    for instance in event.extrainstance_set.all():
        extra = instance.extra
        cost = book.extras.get((extra.pk, pricelist)) if pricelist else None
        cost = extra.cost if cost is None else cost
        lines.append(Line(Line.EXTRA, extra, extra.category, instance.quant,
                          instance.quant * cost))

    if not event.uses_new_discounts:
        # Event2019.discount_applied and discount_value.
        names = {line.category_name for line in lines if line.kind == Line.SERVICE}
        if 'Lighting' in names and 'Sound' in names:
            covered = [line for line in lines
                       if line.kind == Line.EXTRA or line.category_name in OLD_DISCOUNT_CATEGORIES]
            total = sum((line.amount for line in covered), ZERO)
            discount = (total * OLD_DISCOUNT_RATE).quantize(CENT, rounding=decimal.ROUND_DOWN)
            _share_out(covered, discount, -1)
        return lines

    # Event2019.get_discount_values and get_fee_values: each one only with a
    # price list that gives it a rate, over the categories it names.
    for adjustments, rates, sign in ((event.applied_discounts.all(), book.discounts, -1),
                                     (event.applied_fees.all(), book.fees, 1)):
        for adjustment in adjustments:
            percent = rates.get((adjustment.pk, pricelist)) if pricelist else None
            if percent is None:
                continue
            categories = {category.pk for category in adjustment.categories.all()}
            covered = [line for line in lines if line.category is not None and
                       line.category.pk in categories]
            total = sum((line.amount for line in covered), ZERO)
            if total:
                _share_out(covered, _percent_of(total, percent), sign)
    return lines


def _lines_legacy(event):
    """
    A 2012 event's services and extras, as ``Event.cost_total`` prices them:
    list prices, extras only in the four categories it counts, and 15% off the
    lighting and sound services when the show has both.
    """
    lines = [Line(Line.SERVICE, service, service.category, 1, service.base_cost)
             for service in (event.lighting, event.sound, event.projection)
             if service is not None]
    lines += [Line(Line.SERVICE, service, service.category, 1, service.base_cost)
              for service in event.otherservices.all()]
    lines += [Line(Line.EXTRA, instance.extra, instance.extra.category, instance.quant,
                   instance.quant * instance.extra.cost)
              for instance in event.extrainstance_set.all()
              if instance.extra.category.name in ('Lighting', 'Sound', 'Projection', 'Misc')]
    if event.lighting is not None and event.sound is not None:
        pair = [line for line in lines[:2]]
        discount = money((event.lighting.base_cost + event.sound.base_cost) * OLD_DISCOUNT_RATE)
        _share_out(pair, discount, -1)
    return lines


# ---------------------------------------------------------------------------
# Every show in a stretch of time
# ---------------------------------------------------------------------------

class Work(object):
    """ One show: who it was for, what LNL brought to it, and what that was worth. """

    def __init__(self, event, lines, billed):
        self.event = event
        self.lines = lines
        self.billed = billed
        self.day = timezone.localtime(event.datetime_start).date()
        self.client = client_of(event)
        self.client_type = client_type_for(event)
        rentals = list(event.rentals.all())
        self.rental_items = sum((rental.quantity for rental in rentals), 0)
        self.rental_cost = sum((money(rental.totalcost) for rental in rentals), ZERO)

    @property
    def value(self):
        """ The show's service value: every line after discounts and fees. """
        return sum((line.net for line in self.lines), ZERO)

    def value_in(self, category_name):
        """ The part of its value in one service category. """
        return sum((line.net for line in self.lines if line.category_name == category_name),
                   ZERO)

    def uses(self, category_name):
        """ Whether LNL brought anything in that category. """
        return any(line.category_name == category_name for line in self.lines)


def load_work(first=None, last=None, today=None):
    """
    Every approved show that ran between ``first`` and ``last`` -- and no later
    than today, since a show still to come is a booking, not work done --
    priced. Either end may be ``None`` for no limit. Cancelled and test events
    are left out.
    """
    from events.models import Event, Event2019

    from finance.calculators import event_billed

    today = today or timezone.localdate()
    last = min(last, today) if last is not None else today
    book = PriceBook()

    def shows(model, *related, **selected):
        queryset = model.objects.filter(approved=True, cancelled=False, test_event=False,
                                        datetime_start__date__lte=last)
        if first is not None:
            queryset = queryset.filter(datetime_start__date__gte=first)
        return (queryset.select_related('billing_org', *selected.get('select', ()))
                .prefetch_related('org', 'rentals', 'billings', 'multibillings__events',
                                  'extrainstance_set__extra__category', *related))

    cache, out = {}, []
    for event in shows(Event2019, 'serviceinstance_set__service__category',
                       'applied_discounts__categories', 'applied_fees__categories'):
        out.append(Work(event, _lines_2019(event, book), event_billed(event, cache)[0]))
    for event in shows(Event, 'otherservices__category',
                       select=('lighting__category', 'sound__category', 'projection__category')):
        out.append(Work(event, _lines_legacy(event), event_billed(event, cache)[0]))
    out.sort(key=lambda work: (work.event.datetime_start, work.event.pk))
    return out


def category_names():
    """ The events app's service categories, in its own order. """
    from events.models import Category

    return list(Category.objects.order_by('pk').values_list('name', flat=True))


def earliest_event_date():
    """ The day the first approved show ran, or ``None`` with none on file. """
    from events.models import BaseEvent

    first = (BaseEvent.objects.filter(approved=True, cancelled=False, test_event=False)
             .order_by('datetime_start').values_list('datetime_start', flat=True).first())
    return timezone.localtime(first).date() if first is not None else None
