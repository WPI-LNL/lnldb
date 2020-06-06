from pages.models import Page


def staticz(*args):
    return {'static': "/~photo/common"}


def navs(*args):
    page_navs = Page.objects.filter(noindex=False).order_by('title')
    return {'navs': page_navs}
