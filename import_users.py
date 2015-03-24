import csv
import string
from django.contrib.auth.models import User
from django.contrib.auth.models import Group
from acct.models import Profile
# x = open('/home/lnldb/lnldb/csvs/users/assoc.csv','rU')
#do(x)
#y = open('/home/lnldb/lnldb/csvs/users/active.csv','rU')
#do(y)
#z = open('/home/lnldb/lnldb/csvs/users/aluminac.csv','rU')
#do(z)


def do(infile):
    #get groups
    g_alumni = Group.objects.get(name="Alumni")
    g_active = Group.objects.get(name="Active")
    g_assoc = Group.objects.get(name="Associate")
    g_away = Group.objects.get(name="Away")
    g_officer = Group.objects.get(name="Officer")

    foo = csv.reader(infile, dialect="excel", delimiter=',')
    for line in foo:
        if not line[5]:  # wpi username
            if '@wpi.edu' or '@WPI.EDU' in line[4]:
                uname = line[4].split('@')[0]
            else:
                continue
        else:
            uname = line[4].split('@')[0]
            pass

        # get user/create
        u, created = User.objects.get_or_create(username=uname)

        if created:
            p = Profile.objects.create(user=u)
            p = u.get_profile()
        else:
            print u
            p = u.get_profile()

        #assocation
        if line[0] == 'Al':
            g_alumni.user_set.add(u)
        elif line[0] == 'In':
            g_away.user_set.add(u)
        elif line[0] == 'As':
            g_assoc.user_set.add(u)
        elif line[0] == 'Ac':
            g_active.user_set.add(u)
        p.save()

        #enter name
        try:
            splitname = line[1].split(' ', 1)
            u.first_name = splitname[0]
            u.last_name = splitname[1]
        except KeyError:
            pass

        #mailbox
        if line[2]:
            u.profile.wpibox = line[2]
        #phone
        if line[3]:
            num = line[3]
            num = num.translate(string.maketrans("", ""), string.punctuation).replace(' ', '')

            u.profile.phone = num

        if line[4]:
            u.email = line[4]

        u.save()