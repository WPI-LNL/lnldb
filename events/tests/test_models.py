from django.test import TestCase
from decimal import Decimal

from .generators import Event2019Factory, ServiceFactory, ServiceInstanceFactory
from .. import models

class Event2019PropertyTests(TestCase):
    def setup(self):
        self.event = Event2019Factory.create(event_name="2019 Test Event")
        self.category = models.Category.objects.create(name="test category")
        self.lighting = models.Category.objects.create(name="Lighting")
        self.sound = models.Category.objects.create(name="Sound")
        self.projection = models.Category.objects.create(name="Projection")
        self.service = ServiceFactory(category=self.category, shortname="ts", base_cost=10.01)
        self.service2 = ServiceFactory(category=self.category, shortname="t2", base_cost=20.02)
        self.film_service = ServiceFactory(longname="film projection", category=self.projection, base_cost=23.32)
        self.extra = models.Extra.objects.create(name="Mirror Ball", cost=4500.99, desc="A very nice mirror ball.", category=self.lighting)
        self.extra2 = models.Extra.objects.create(name="caring", cost=1.99, desc="", category=self.category)

        self.pricelist = models.Pricelist.objects.create(name="test pricelist")
        models.ServicePrice.objects.create(service=self.service, pricelist=self.pricelist, cost=100.11)
    
    def test_has_projection(self):
        self.setup()
        
        self.assertFalse(self.event.has_projection)

        film_instance = ServiceInstanceFactory(service=self.film_service, event=self.event)
        self.assertTrue(self.event.has_projection)
    
    def test_event_services(self):
        self.setup()
        self.assertEqual(list(self.event.eventservices), [])
        ServiceInstanceFactory(service=self.service, event=self.event)
        self.assertEqual(list(self.event.eventservices), [self.service])
    
    def test_short_services(self):
        self.setup()
        self.assertEqual(self.event.short_services, "")
        ServiceInstanceFactory(service=self.service, event=self.event)
        ServiceInstanceFactory(service=self.service2, event=self.event)
        self.assertEqual(self.event.short_services, "ts, t2")
    
    def test_event_count(self):
        self.setup()
        self.assertEqual(self.event.eventcount, 0)
        
        # even though they are associated with categories, extras don't count towards this
        models.ExtraInstance.objects.create(event=self.event, extra=self.extra, quant=2)
        self.assertEqual(self.event.eventcount, 0)

        ServiceInstanceFactory(service=self.service, event=self.event)
        self.assertEqual(self.event.eventcount, 1)
        ServiceInstanceFactory(service=self.film_service, event=self.event)
        self.assertEqual(self.event.eventcount, 2)
        
    def test_services_total(self):
        self.setup()
        self.assertEqual(self.event.services_total, 0)
        ServiceInstanceFactory(service=self.service, event=self.event)
        self.assertEqual(self.event.services_total, Decimal('10.01'))
        ServiceInstanceFactory(service=self.service2, event=self.event)
        self.assertEqual(self.event.services_total, Decimal('30.03'))
        
        self.event.pricelist = self.pricelist
        self.event.save()
        self.assertEqual(self.event.services_total, Decimal('120.13'))
        models.ServicePrice.objects.create(service=self.service2, pricelist=self.pricelist, cost=200.22)
        self.assertEqual(self.event.services_total, Decimal('300.33'))

        # extras shouldn't effect services total
        models.ExtraInstance.objects.create(event=self.event, extra=self.extra, quant=2)
        self.assertEqual(self.event.services_total, Decimal('300.33'))
    
    def test_extras_total(self):
        self.setup()
        self.assertEqual(self.event.extras_total, 0)
        models.ExtraInstance.objects.create(event=self.event, extra=self.extra, quant=2)
        self.assertEqual(self.event.extras_total, Decimal('9001.98'))
        models.ExtraInstance.objects.create(event=self.event, extra=self.extra2, quant=1)
        self.assertEqual(self.event.extras_total, Decimal('9003.97'))

        # services shouldn't effect extras total
        ServiceInstanceFactory(service=self.service, event=self.event)
        self.assertEqual(self.event.extras_total, Decimal('9003.97'))
    
    def test_cost_total_pre_discount(self):
        self.setup()
        self.assertEqual(self.event.cost_total_pre_discount, 0)
        ServiceInstanceFactory(service=self.service, event=self.event)
        self.assertEqual(self.event.cost_total_pre_discount, Decimal('10.01'))
        models.ExtraInstance.objects.create(event=self.event, extra=self.extra2, quant=1)
        self.assertEqual(self.event.cost_total_pre_discount, Decimal('12.00'))
        models.EventArbitrary.objects.create(event=self.event, key_name="extra fee", key_value="52.93")
        self.assertEqual(self.event.cost_total_pre_discount, Decimal('64.93'))

        self.event.pricelist = self.pricelist
        self.event.save()
        self.assertEqual(self.event.cost_total_pre_discount, Decimal('155.03'))
    
    def test_discount_applied(self):
        self.setup()
        self.assertFalse(self.event.discount_applied)
        
        sound_service = ServiceFactory(category=self.sound)
        ServiceInstanceFactory(service=sound_service, event=self.event)
        self.assertFalse(self.event.discount_applied)

        # extras don't count towards the combo discount
        models.ExtraInstance.objects.create(event=self.event, extra=self.extra, quant=2)
        self.assertFalse(self.event.discount_applied)
        
        lighting_service = ServiceFactory(category=self.lighting)
        ServiceInstanceFactory(service=lighting_service, event=self.event)
        self.assertTrue(self.event.discount_applied)
    
    def test_discount_value_and_cost_total(self):
        self.setup()
        self.assertEqual(self.event.discount_value, 0)
        self.assertEqual(self.event.cost_total, 0)
        
        # without both lighting and sound, no discount yet
        lighting_service = ServiceFactory(category=self.lighting, base_cost=51.35)
        ServiceInstanceFactory(service=lighting_service, event=self.event)
        self.assertFalse(self.event.discount_applied)
        self.assertEqual(self.event.discount_value, 0)
        self.assertEqual(self.event.cost_total, Decimal('51.35'))

        ServiceInstanceFactory(service=self.film_service, event=self.event)
        self.assertFalse(self.event.discount_applied)
        self.assertEqual(self.event.discount_value, 0)
        self.assertEqual(self.event.cost_total, Decimal('74.67'))

        # discount gets applied correctly, projection service doesn't get discounted
        sound_service = ServiceFactory(category=self.sound, base_cost=70)
        ServiceInstanceFactory(service=sound_service, event=self.event)
        self.assertTrue(self.event.discount_applied)
        self.assertEqual(self.event.discount_value, Decimal('18.20'))
        self.assertEqual(self.event.cost_total, Decimal('126.47'))

        # all extras get discounted, even in other categories
        models.ExtraInstance.objects.create(event=self.event, extra=self.extra2, quant=1)
        self.assertEqual(self.event.discount_value, Decimal('18.50'))
        self.assertEqual(self.event.cost_total, Decimal('128.16'))
        
        # rigging services get discounted
        rigging = models.Category.objects.create(name="Rigging")
        rigging_service = ServiceFactory(category=rigging, base_cost=19.20)
        ServiceInstanceFactory(service=rigging_service, event=self.event)
        self.assertEqual(self.event.discount_value, Decimal('21.38'))
        self.assertEqual(self.event.cost_total, Decimal('144.48'))

        # power services get discounted
        power = models.Category.objects.create(name="Power")
        power_service = ServiceFactory(category=power, base_cost=35.92)
        ServiceInstanceFactory(service=power_service, event=self.event)
        self.assertEqual(self.event.discount_value, Decimal('26.76'))
        self.assertEqual(self.event.cost_total, Decimal('175.02'))

    def test_new_combo_discount(self):
        self.setup()

        rigging = models.Category.objects.create(name="Rigging")
        power = models.Category.objects.create(name="Power")

        combo_discount = models.Discount.objects.create(name="Combo Discount")
        combo_discount.categories.add(self.lighting)
        combo_discount.categories.add(self.sound)
        combo_discount.categories.add(rigging)
        combo_discount.categories.add(power)
        
        self.event.uses_new_discounts = True
        self.event.applied_discounts.add(combo_discount)
        self.event.pricelist = self.pricelist
        self.event.save()

        self.assertEqual(self.event.discount_value, 0)
        self.assertEqual(self.event.cost_total, 0)
        self.assertFalse(self.event.discount_applied)
        
        # without both lighting and sound, no discount yet
        lighting_service = ServiceFactory(category=self.lighting, base_cost=51.35)
        ServiceInstanceFactory(service=lighting_service, event=self.event)
        self.assertEqual(self.event.discount_value, 0)
        self.assertEqual(self.event.cost_total, Decimal('51.35'))

        ServiceInstanceFactory(service=self.film_service, event=self.event)
        self.assertEqual(self.event.discount_value, 0)
        self.assertEqual(self.event.cost_total, Decimal('74.67'))
        
        # discount should be applied now
        sound_service = ServiceFactory(category=self.sound, base_cost=70)
        ServiceInstanceFactory(service=sound_service, event=self.event)

        # if the discount isn't in the pricelist, it defaults to 0
        self.assertEqual(self.event.discount_value, Decimal('0'))
        self.assertEqual(self.event.cost_total, Decimal('144.67'))
        
        # add the combo discount to the pricelist
        models.DiscountPrice.objects.create(pricelist=self.pricelist, discount=combo_discount, percent=15)

        # discount gets applied correctly, projection service doesn't get discounted
        self.assertEqual(sum(self.event.discount_values.values()), Decimal('18.20'))
        self.assertEqual(self.event.cost_total, Decimal('126.47'))

        # extras don't get discounted
        models.ExtraInstance.objects.create(event=self.event, extra=self.extra2, quant=1)
        self.assertEqual(sum(self.event.discount_values.values()), Decimal('18.20'))
        self.assertEqual(self.event.cost_total, Decimal('128.46'))
        
        # rigging services get discounted
        rigging_service = ServiceFactory(category=rigging, base_cost=19.20)
        ServiceInstanceFactory(service=rigging_service, event=self.event)
        self.assertEqual(sum(self.event.discount_values.values()), Decimal('21.08'))
        self.assertEqual(self.event.cost_total, Decimal('144.78'))

        # power services get discounted
        power_service = ServiceFactory(category=power, base_cost=35.92)
        ServiceInstanceFactory(service=power_service, event=self.event)
        self.assertEqual(sum(self.event.discount_values.values()), Decimal('26.47'))
        self.assertEqual(self.event.cost_total, Decimal('175.31'))
        
        # projection services don't get discounted
        projection_service = ServiceFactory(category=self.projection, base_cost=10)
        ServiceInstanceFactory(service=projection_service, event=self.event)
        self.assertEqual(sum(self.event.discount_values.values()), Decimal('26.47'))
        self.assertEqual(self.event.cost_total, Decimal('185.31'))
    
    def test_fees(self):
        self.setup()

        test_fee = models.Fee.objects.create(name="Test Fee")
        test_fee.categories.add(self.lighting)

        test_discount = models.Discount.objects.create(name="Test Discount")
        test_discount.categories.add(self.lighting)
        
        self.event.uses_new_discounts = True
        self.event.pricelist = self.pricelist
        self.event.save()
        
        # fee isn't applied to the event yet, so nothing should happen
        lighting_service = ServiceFactory(category=self.lighting, base_cost=92.12)
        ServiceInstanceFactory(service=lighting_service, event=self.event)
        self.assertEqual(sum(self.event.fee_values.values()), Decimal('0'))
        self.assertEqual(self.event.cost_total, Decimal('92.12'))
        
        # fee doesn't have a pricelist entry yet, so should still be 0
        self.event.applied_fees.add(test_fee)
        self.assertEqual(sum(self.event.fee_values.values()), Decimal('0'))
        self.assertEqual(self.event.cost_total, Decimal('92.12'))
        
        # fee should be applied now
        models.FeePrice.objects.create(pricelist=self.pricelist, fee=test_fee, percent=25)
        self.assertEqual(sum(self.event.fee_values.values()), Decimal('23.03'))
        self.assertEqual(self.event.cost_total, Decimal('115.15'))
        
        # fees and discounts are both calculated relative to the base cost, and then added together
        self.event.applied_discounts.add(test_discount)
        models.DiscountPrice.objects.create(pricelist=self.pricelist, discount=test_discount, percent=10)
        self.assertEqual(self.event.cost_total, Decimal('105.94'))
       