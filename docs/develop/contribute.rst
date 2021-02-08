===========================
Contributing to the Project
===========================

The source code for the LNL Database project is open source and can be found on GitHub. Any current or former LNL
member is more than welcome to contribute to this project. When doing so, we ask that you familiarize yourself with
some of the best practices outlined below and let us know if you have any questions. Feel free to email lnl-w@wpi.edu
if you ever need more assistance and happy coding!


Getting Started
===============

If you haven't already, you'll want to fork the LNLDB project and clone or download your fork onto your device. Be sure
to follow the directions provided in the README file to get set up. You'll also need to switch to a new branch before
making any changes.

.. seealso::
    `LNLDB Repository on GitHub <https://github.com/WPI-LNL/lnldb>`_


Testing
=======

Before submitting new features for review, we strongly encourage writing tests for your code. All tests should pass
and cover a majority of the lines written. Pull requests that do not contain adequate test coverage are less likely to
be accepted.

We recommend writing tests for larger models and all of your views. In most cases, this is enough to provide adequate
coverage. Examples for how to write some of these test cases are provided below.

.. tip::
    When writing test cases, be sure to test multiple inputs; especially edge cases. Test both valid inputs and invalid inputs.

Models
------

.. code-block:: python

    from django.test import TestCase
    from django.utils import timezone
    from events.tests.generators import UserFactory
    from . import models

    class ProjectionistModelTests(TestCase):
        def setUp(self):
            self.user = UserFactory.create(password="123")
            self.projectionist = models.Projectionist(user=self.user)
            self.projectionist.save()

        def test_expired(self):
            today = timezone.datetime.today().date()
            yesterday = today + timezone.timedelta(days=-1)
            tomorrow = today + timezone.timedelta(days=1)

            self.projectionist.license_expiry = today
            self.projectionist.save()
            self.assertTrue(self.projectionist.expired)

            self.projectionist.license_expiry = yesterday
            self.projectionist.save()
            self.assertTrue(self.projectionist.expired)

            self.projectionist.license_expiry = tomorrow
            self.projectionist.save()
            self.assertFalse(self.projectionist.expired)

When writing unit tests for models, you typically only need to test the properties that you have defined for the
model (if any). In this case we are testing the ``expired`` property on a Projectionist object. We start by subclassing
``TestCase`` and override the default ``setUp()`` function to create objects that we will use frequently in our tests. In
this case, many of these tests will use an instance of ``Projectionist``, so we create a new Projectionist object.

Model Factories
^^^^^^^^^^^^^^^
Now you might notice that we also created a dummy user here using ``UserFactory``. UserFactory is one of several model
factory classes which allow you to create objects from certain models quickly and easily. These model factories will
fill in dummy data for each required field unless otherwise specified when you create the object. A list of available
model factories is included below:

- UserFactory
- BuildingFactory
- LocationFactory
- CategoryFactory
- ServiceFactory
- EventFactory
- Event2019Factory
- CCInstanceFactory
- CCReportFactory
- OrgFactory
- FundFactory


Views
-----

Test cases for views are a bit different when compared to model test cases. They can become fairly complicated, but
fortunately there are a few shortcuts that can help make things a bit easier. Here's an example of two different test
cases used to check a couple of our more typical views:

.. code-block:: python

    from data.tests.util import ViewTestCase
    from django.core.files.uploadedfile import SimpleUploadedFile
    from django.contrib.auth.models import Permission
    from django.urls.base import reverse
    from django.utils import timezone
    from . import models
    from meetings.models import mtg_attachment_file_name

    class MeetingsViewTest(ViewTestCase):
        def setUp(self):
            super(MeetingsViewTest, self).setUp()  # Always include a call to super to take full advantage of the ViewTestCase class
            self.meeting_type1 = models.MeetingType.objects.create(name='Exec')
            self.meeting = models.Meeting.objects.create(datetime=timezone.now(), meeting_type=self.meeting_type1)
            self.meeting2 = models.Meeting.objects.create(datetime=timezone.now(), meeting_type=self.meeting_type1)
            path = models.mtg_attachment_file_name(self, "TotallyAFile.png")
            f = SimpleUploadedFile(path, b"some content")
            self.attachment = models.MtgAttachment.objects.create(name="Attachment1", file=f, author=self.user, meeting=self.meeting)

        def test_viewattendace(self):
            # By default, should not have permission to view attendance
            self.assertOk(self.client.get(reverse("meetings:detail", args=[self.meeting.pk])), 403)

            permission = Permission.objects.get(codename="view_mtg_attendance")
            self.user.user_permissions.add(permission)

            self.assertOk(self.client.get(reverse("meetings:detail", args=[self.meeting.pk])))

        def test_modify_att(self):
            # By default, should not have permission to modify attachments
            self.assertOk(self.client.get(reverse("meetings:att-edit", args=[self.meeting.pk, self.attachment.pk])), 403)

            permission = Permission.objects.get(codename="edit_mtg")
            self.user.user_permissions.add(permission)

            # Will also need view_mtg permissions for redirect
            permission = Permission.objects.get(codename="view_mtg_attendance")
            self.user.user_permissions.add(permission)

            self.assertOk(self.client.get(reverse("meetings:att-edit", args=[self.meeting.pk, self.attachment.pk])))

            # If attachment event id does not match event id throw permission denied
            self.assertOk(self.client.get(reverse("meetings:att-edit", args=[self.meeting2.pk, self.attachment.pk])), 403)

            path = models.mtg_attachment_file_name(self, "TotallyAFile.png")
            f = SimpleUploadedFile(path, b"some content")
            valid_data = {
                "name": "Test File",
                "file": f,
                "private": True,
                "submit": "Submit"
            }

            self.assertRedirects(
                self.client.post(reverse("meetings:att-edit", args=[self.meeting.pk, self.attachment.pk]), valid_data),
                reverse("meetings:detail", args=[self.meeting.pk]) + "#minutes"
            )

There's a lot to unpack here, so let's work our way through it from top to bottom. If you look at the import statements
you'll notice that we import ``ViewTestCase``. This is a custom test case class which we have developed to provide
shortcuts for testing views. Next, there's something called ``SimpleUploadedFile``. This is used whenever
you need to test a form with a file upload field. You'll also notice we've imported the ``Permission`` model so that we
can check that only users with the proper permissions can access a given view. Finally, when it comes to dealing with
dates and times, we import ``timezone`` rather than ``datetime``. This helps us avoid running into naive datetimes.

Next take a look at the ``setUp()`` function. We are once again overriding this function to set up some commonly used
objects for our tests, however note that the first line makes a call to super. This doesn't necessarily need to be the
first line, however it does need to be included in the setup if you intend to test permissions (which you should). The
``setUp()`` function defined by ViewTestCase creates a new user (self.user) and logs them in for you.

The first test case is for a very basic view. For this view, we are only interested in ensuring that the
view can load successfully. That being said, this view requires certain permissions to access, so first we will want to
check that a user with no permissions will be denied access. After that, we add the permission(s) a user would need to
``self.user`` and try again. To check if the page loads as expected, we use the ``assertOk`` function provided by the
``ViewTestCase`` class to check for a HTTP status code of 200 (or some other code if specified).

The second test case is a bit more complex. We start out the same way we did with the first view, except in this case,
you'll notice that we have actually added two permissions for the user. This is because when the user successfully
submits the form that is presented on this page, they will be redirected to a new page (which should have its own test)
and that page requires a different permission. The next chunk handles checking that the page actually redirects when
valid data is posted.

Forms and Formsets
^^^^^^^^^^^^^^^^^^
Most views will follow a similar format to the views tested above, so you'll just need to set up and test various GET
and POST requests. When submitting form data, another thing to take note of is whether the form fields will have a
prefix or if the form will include formsets. If so, valid form data may look something more like this:

.. code-block:: python

    valid_data = {
        "main-TOTAL_FORMS": 1,
        "main-INITIAL_FORMS": 0,
        "main-MIN_NUM_FORMS": 0,
        "main-MAX_NUM_FORMS": 1000,
        "main-0-crew_chief": str(self.user.pk),
        "main-0-service": str(service.pk),
        "main-0-category": "",
        "main-0-setup_location": str(location.pk),
        "main-0-setup_start_0": timezone.now().date(),
        "main-0-setup_start_1": timezone.now().time(),
        "event_name": "Some Event",
        "description": "We want to have an event to do event things",
        "save": "Submit"
    }

.. seealso::
    For more details on formsets, check out the `Django Documentation <https://docs.djangoproject.com/en/3.1/topics/forms/formsets/>`_

It may take a bit of practice to get used to at first, but writing tests for your code will save you time in the long
run and significantly limit the number of bugs you introduce. If you're new to test driven development, now is a great
time to learn more about it! And if you are struggling with writing any of your tests, take a peek at the several tests
that have already been written for the existing code.


Documentation
=============

Any time you make changes to the code or add a new feature, you should take some time to update the documentation
accordingly. If you're adding new models or views, you can do this simply by including block comments like this:

.. code-block:: python

    class NewClass(models.Model):
        """A new class I just created as an example"""
        some_field = models.CharField(max_length=100)
        ...

These comments will be added to the documentation automatically the next time it's compiled. You should also make sure
that any related help guides are also updated. Everything you need to edit the documentation can be found in the
``docs`` module.

To compile the docs, navigate to the docs directory via the command line and run:

.. code-block:: bash

    make html

And that's all there is to it! This project's documentation is an incredibly valuable resource for both our users and
contributors like you. So help us out by doing your part to keep our documentation fresh and up-to-date.


Submitting your Code
====================

Once you've managed to write some code, verified that all the tests pass, and updated the documentation (if applicable),
it's time to open a pull request. Once you've opened up your pull request, our Webmaster will begin reviewing your
changes. If everything is in order, it will be merged and deployed with the next release.

Every contribution matters and we want to thank you all for your support. If at any time you get stuck or have questions
about anything that isn't covered by the documentation, we invite you to join the #webdev channel on Slack or email the
Webmaster at lnl-w@wpi.edu.
