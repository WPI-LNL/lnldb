from django.db.models import Q, IntegerField, CharField, TextField
from django.contrib.auth.models import AbstractUser
from events.models import Organization
# from django_custom_user_migration.models import AbstractUser


class User(AbstractUser):

    def save(self, *args, **kwargs):
        if not self.pk and not self.email:
            self.email = "%s@wpi.edu" % self.username
        super(User, self).save(*args, **kwargs)

    wpibox = IntegerField(null=True, blank=True, verbose_name="WPI Box Number")
    phone = CharField(max_length=24, null=True, blank=True, verbose_name="Phone Number")
    addr = TextField(null=True, blank=True, verbose_name="Address / Office Location")
    mdc = CharField(max_length=32, null=True, blank=True, verbose_name="MDC")

    @property
    def is_lnl(self):
        if self.groups.filter(Q(name="Alumni") | Q(name="Active") | Q(name="Officer") | Q(name="Associate") | Q(
                name="Away") | Q(name="Inactive")).exists():
            return True
        else:
            return False

    @property
    def is_complete(self):
        # We can make it more strict later on, but these are the essentials. And
        return self.first_name and self.last_name

    @property
    def group_str(self):
        groups = map(lambda l: l.name, self.user.groups.all())
        out_str = ""
        if "Alumni" in groups:
            out_str += 'Alum '
        if "Officer" in groups:
            out_str += 'Officer'
        elif "Active" in groups:
            out_str += 'Active'
        elif "Associate" in groups:
            out_str += 'Associate'
        elif "Away" in groups:
            out_str += 'Away'
        elif "Inactive" in groups:
            out_str += 'Inactive'
        else:
            out_str += "Unclassified"
        return out_str

    @property
    def owns(self):
        return ', '.join(map(str, self.user.orgowner.all()))

    @property
    def orgs(self):
        return ', '.join(map(str, self.user.orgusers.all()))

    @property
    def all_orgs(self):
        return Organization.objects.complex_filter(
            Q(user_in_charge=self.user) | Q(associated_users=self.user)).distinct()

    @property
    def mdc_name(self):
        max_chars = 12
        clean_first, clean_last = "", ""

        # assume that Motorola can handle practically nothing. Yes, ugly, but I don't wanna regex 1000's of times
        for char in self.user.first_name.upper().strip():
            if ord(char) == ord(' ') or ord(char) == ord('-') \
                    or ord('0') <= ord(char) <= ord('9') or ord('A') <= ord(char) <= ord('Z'):
                clean_first += char
        for char in self.user.last_name.upper().strip():
            if ord(char) == ord(' ') or ord(char) == ord('-') \
                    or ord('0') <= ord(char) <= ord('9') or ord('A') <= ord(char) <= ord('Z'):
                clean_last += char

        outstr = clean_last[:max_chars - 2] + ","  # leave room for at least an initial
        outstr += clean_first[:max_chars - len(outstr)]  # fill whatever's left with the first name
        return outstr

    class Meta:
        permissions = (
            ('change_group', 'Change the group membership of a user'),
            ('edit_mdc', 'Change the MDC of a user'),
            ('view_user', 'View users'),
            ('view_member', 'View LNL members'),
        )