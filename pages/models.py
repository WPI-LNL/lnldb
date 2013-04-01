from django.db import models

# Create your models here.

class Page(models.Model):
    title = models.CharField(max_length=64)
    slug = models.SlugField(max_length=64)

    body = models.TextField()
    body_in_hero = models.BooleanField()

    main_nav = models.BooleanField()
    nav_pos = models.IntegerField()
    
    carousel_css = models.CharField(max_length=32,default="custom")
    
    imgs = models.ManyToManyField('CarouselImg',null=True,blank=True)
    
    def __unicode__(self):
        return self.title
    
    ordering = ['nav_pos']

class CarouselImg(models.Model):
    internal_name = models.CharField(max_length=64)
    img = models.ImageField(upload_to='carousel')
    href = models.ForeignKey('Page',null=True,blank=True)
    href_words = models.CharField(max_length=64,null=True,blank=True)
    href_desc = models.CharField(max_length=128,null=True,blank=True)
    
    def __unicode__(self):
        return self.internal_name