from pages.models import Page
def staticz(request):
    return {'static':"/~photo/common"}
    
def navs(request):
    navs = Page.objects.filter(main_nav=True).order_by('nav_pos')
    return {'navs':navs}