from events.models import Organization
from acct.models import Orgsync_Org
from django.contrib.auth.models import User


def normalize_orgs(target_id, dupe_ids):
    # gets rid of duplicates by converging orgs
    # ex : there are a dozen soccomm MACCs in the original db for some reason
    target = Organization.objects.get(pk=target_id)
    dupes = Organization.objects.filter(pk__in=dupe_ids)

    print "Target Merge %s" % target.name
    print "Dupes %s" % " ".join([d.name for d in dupes])

    totalcount = 0
    tdupecnt = dupes.count()

    # iterate through our dupes
    dupecount = 0
    for dupe in dupes:
        dupecount = 0
        # get their events
        events = dupe.event_set.all()
        # and iterate some more
        for event in events:
            dupecount += 1
            # remove the existing org. add the org to the events & save
            event.org.remove(dupe)
            event.org.add(target)
            event.save()

        totalcount += dupecount
        print "converted %i events to use org (%s)" % (dupecount, target.name)
        # merge the associated_users

        dusers = dupe.associated_users.all()
        target.associated_users.add(*dusers)
        target.save()
        # after this is all done,
        dupe.delete()

    print "completed conversion"
    print "converted %i orgs with a total of %i events to use org (%s)" % (dupecount, tdupecnt, target.name)


# """
# from events import normalize; normalize.update_from_orgsync_models()
# normalize.normalize_orgs()
#"""

def update_from_orgsync_models(start=0):
    all_orgs = Orgsync_Org.objects.filter(pk__gte=start)
    for org in all_orgs:
        allset = False
        while not allset:

            #print nice things
            print "Orgsync Org: [%s:%s]" % (org.id, org.name)
            lnlorgs = Organization.objects.filter(name__icontains=org.name)
            print "LNLdb Orgs Matching: [%s]" % ", ".join("[%s:%s]" % (o.id, o.name) for o in lnlorgs)
            #current orgs matching the string

            i = raw_input("Select ID or enter a '0' if the org isn't here:")
            if i == '0':
                searchmode = True
                while searchmode:
                    newsearchstr = raw_input("Search String or 0 if you'd like to skip:")
                    if newsearchstr == '0':
                        allset = True
                        searchmode = False
                    else:
                        lnlorgs = Organization.objects.filter(name__icontains=newsearchstr)
                        print "Reminding: Orgsync Org: %s" % org.name
                        print "LNLdb Orgs Matching: [%s]" % ", ".join("[%s:%s]" % (o.id, o.name) for o in lnlorgs)
                        i = raw_input("Select ID or 0 to try again, or enter an 'X' if the org isn't here:")
                        if i != '0':
                            allset = True
                            searchmode = False

                if newsearchstr == "0":
                    allset = True

            if newsearchstr == "0":
                allset = True
            if i == "0":
                allset = True
            o = lnlorgs.filter(pk=i)

            if o:
                print "Org Selected, Updating"
                o = o[0]
                uname = org.president_email.split('@')[0]
                uic, created = User.objects.get_or_create(username=uname)
                if created:
                    uic.email = org.president_email
                    uic.save()

                o.user_in_charge = uic
                o.exec_email = org.org_email
                o.save()
                print "Org Updated Successfully"
                allset = True