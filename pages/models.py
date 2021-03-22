from django.db import models
from django.conf import settings
from django.contrib.auth.models import Group

from six import python_2_unicode_compatible


# Create your models here.
@python_2_unicode_compatible
class Page(models.Model):
    """ Custom dynamic page using the static site stylesheets """
    title = models.CharField(max_length=64)
    slug = models.SlugField(max_length=64)
    description = models.TextField(blank=True, help_text="This page description may appear in search engine results "
                                                         "and along with any links to this page.")

    body = models.TextField(help_text="Accepts raw text and/or HTML input")
    body_in_jumbo = models.BooleanField(default=False)
    noindex = models.BooleanField(default=False, verbose_name="Hide from search engines")
    sitemap = models.BooleanField(default=False, verbose_name="Include in Sitemap")
    sitemap_category = models.CharField(max_length=32, blank=True, null=True)

    css = models.TextField(blank=True, verbose_name="CSS")

    imgs = models.ManyToManyField('CarouselImg', blank=True)

    def __str__(self):
        return self.title


@python_2_unicode_compatible
class CarouselImg(models.Model):
    """ Image to be displayed as part of a carousel on a custom page """
    internal_name = models.CharField(max_length=64)
    img = models.ImageField(upload_to='carousel')
    href = models.ForeignKey('Page', on_delete=models.SET_NULL, null=True, blank=True)
    caption_title = models.CharField(max_length=64, null=True, blank=True)
    caption_desc = models.CharField(max_length=128, null=True, blank=True)

    def __str__(self):
        return self.internal_name


class OnboardingScreen(models.Model):
    """ Custom page to display to users after they log in. Can be assigned to individual users or groups. """
    title = models.CharField(max_length=64)
    slug = models.SlugField(max_length=64)
    icon = models.CharField(max_length=300, blank=True, null=True, help_text='Icon or image HTML')
    content = models.TextField()
    users = models.ManyToManyField(settings.AUTH_USER_MODEL, blank=True, help_text='Select users to display this to')
    groups = models.ManyToManyField(Group, blank=True, help_text='Select groups of users to display this to.')
    inverted = models.BooleanField(default=False, verbose_name='Dark Theme')
    action_title = models.CharField(max_length=32, verbose_name='Action Button - Text', blank=True, null=True,
                                    help_text='If left blank this button will not be displayed')
    action_href = models.URLField(max_length=128, verbose_name='Action Button - href', blank=True, null=True,
                                  help_text='URL to go to when clicked. If not supplied button will not be displayed.')
    action_color = models.CharField(max_length=16, verbose_name='Action Button - Color', blank=True, null=True)
    new_window = models.BooleanField(default=False, verbose_name='Action Button - Open in New Window')
    next_btn = models.CharField(max_length=32, verbose_name='Next Button - Text', blank=True, null=True,
                                help_text='Defaults to "Next"')

    def __str__(self):
        return self.title


class OnboardingRecord(models.Model):
    """ Log of onboarding pages that have been displayed to a user """
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    screens = models.ManyToManyField(OnboardingScreen, related_name='records', blank=True)

    def __str__(self):
        return self.user.name
