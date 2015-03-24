from pages.models import Page


def staticz(*args):
    return {'static': "/~photo/common"}


def navs(*args):
    page_navs = Page.objects.filter(main_nav=True).order_by('nav_pos')
    return {'navs': page_navs}