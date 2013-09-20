import mechanize
import gzip
import time,sys,random,os
from BeautifulSoup import BeautifulSoup as BS

import getpass,simplejson
from django.core import serializers

from acct.models import Orgsync_User,Orgsync_Org,Orgsync_OrgCat

OrgProfileURL = "https://orgsync.com/%s/chapter/profile"

def ungzipResponse(r,b):
    headers = r.info()
    if headers['Content-Encoding']=='gzip':
        import gzip
        gz = gzip.GzipFile(fileobj=r, mode='rb')
        html = gz.read()
        gz.close()
        headers["Content-type"] = "text/html; charset=utf-8"
        r.set_data( html )
        b.set_response(r)

def login():
    browser = mechanize.Browser()
    browser.set_handle_robots(False)
    #browser.open("https://orgsync.com/sso/cas/worcester-polytechnic-institute")
    browser.open("https://orgsync.com/sso_redirect/worcester-polytechnic-institute")
    print browser.title()
    browser.select_form(nr=0)
    uname = raw_input("username")
    passwd = getpass.getpass("pass")
    browser["username"] = uname
    browser["password"] = passwd
    homepage = browser.submit()
    browser.addheaders = [('User-agent','Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/535.11 (KHTML, like Gecko) Chrome/17.0.963.56 Safari/535.11'),
                 ('Accept', 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8'),
                 ('Accept-Encoding', 'gzip,deflate,sdch'),                  
                 ('Accept-Language', 'en-US,en;q=0.8'),                     
                 ('Accept-Charset', 'ISO-8859-1,utf-8;q=0.7,*;q=0.3'),
                 ('Referer', 'https://orgsync.com/38382/groups'),
                 ('x-csrf-token', '03ec95XtNy1ILWXAf5mcT4KV3R2tulZ6TflL9u0va0Y='), 
                 ('x-requested-with', 'XMLHttpRequest')]
    return browser;

def collect_users():
    browser = login()
    browser.addheaders = [('User-agent', 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/535.11 (KHTML, like Gecko) Chrome/17.0.963.56 Safari/535.11'), ('Accept', 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8'), ('Accept-Encoding', 'gzip,deflate,sdch'), ('Accept-Language', 'en-US,en;q=0.8'), ('Accept-Charset', 'ISO-8859-1,utf-8;q=0.7,*;q=0.3'), ('Referer', 'https://orgsync.com/38382/groups'), ('x-csrf-token', '03ec95XtNy1ILWXAf5mcT4KV3R2tulZ6TflL9u0va0Y='), ('x-requested-with', 'XMLHttpRequest')]
    browser.open("https://orgsync.com/38382/accounts?per_page=100&num_pages=3&order=first_name+ASC&page=1")
    resp = browser.response().read()
    json = simplejson.loads(resp)
    
    totalpages = json['totalEntries']/100 + 2
    for i in range(totalpages):
        print "parsing page %i" % i
        browser.open("https://orgsync.com/38382/accounts?per_page=100&num_pages=3&order=first_name+ASC&page=%i" % i)
        resp = browser.response().read()
        json = simplejson.loads(resp)
        entries = json['entries']
        for e in entries:
            id = {}
            id['last_name'] = e['last_name']
            id['first_name'] = e['first_name']
            id['title'] = e['title']
            if 'email_address' in e.keys():
                id['email_address'] = e['email_address']
            id['orgsync_id'] = e['id']
            id['account_id'] = e['account_id']
            if 'portfolio' in e.keys():
                id['portfolio'] = e['portfolio']
                

            u,created = Orgsync_User.objects.get_or_create(
                    **id
                )
            
        time.sleep(random.random()*8)
        
def create_orgs():
    g = open(os.getcwd() + "/acct/2013-09-17-orgs.json")
    h = g.read().replace('\n','').replace("&quot;",'"')
    i = simplejson.loads(h)
    for e in i['data']:
        c,ccreated = Orgsync_OrgCat.objects.get_or_create(orgsync_id=e['category']['id'], name=e['category']['name'])
        o,ocreated = Orgsync_Org.objects.get_or_create(
                orgsync_id = e['id'],
                name = e['name'],
                keywords = e['keywords'],
            )
        o.category = c
        o.save()
        
def populate_org_data():
    b = login()
    orgs = Orgsync_Org.objects.exclude(category__orgsync_id__in=[34268])
    for o in orgs:
        print "getting data for %s" % o.name
        r = b.open(OrgProfileURL % o.orgsync_id)
        ungzipResponse(r,b)
        html = r.read()
        orgsoup = BS(html)
        
        try:
            prezemail = orgsoup.find("div",text="President Email").findNext('div').text
            o.president_email = prezemail
        except:
            print "no prez email, going along to find the club one"
        try:
            orgemail = orgsoup.find("div",text="Club Email").findNext('div').text
            o.org_email = orgemail
        except:
            print "no org email, shucks"
        
        o.save()
        print "got data for %s" % o.name
