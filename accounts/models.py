# noinspection PyProtectedMember
from django.contrib.auth.models import AbstractUser, _user_has_perm
from django.db.models import (BooleanField, CharField, IntegerField,
                              PositiveIntegerField, Q, TextField)
from django.utils.six import python_2_unicode_compatible

from events.models import Organization


# from django_custom_user_migration.models import AbstractUser

@python_2_unicode_compatible
class User(AbstractUser):
    def save(self, *args, **kwargs):
        # gives an email from the username when first created (ie. via CAS)
        if not self.pk and not self.email:
            self.email = "%s@wpi.edu" % self.username
        super(User, self).save(*args, **kwargs)

    wpibox = IntegerField(null=True, blank=True, verbose_name="WPI Box Number")
    phone = CharField(max_length=24, null=True, blank=True, verbose_name="Phone Number")
    addr = TextField(null=True, blank=True, verbose_name="Address / Office Location")
    mdc = CharField(max_length=32, null=True, blank=True, verbose_name="MDC")
    nickname = CharField(max_length=32, null=True, blank=True, verbose_name="Nickname")
    student_id = PositiveIntegerField(null=True, blank=True, verbose_name="Student ID")
    class_year = PositiveIntegerField(null=True, blank=True)
    locked = BooleanField(default=False)

    def __str__(self):
        nick = '"%s" ' % self.nickname if self.nickname else ""
        if self.first_name or self.last_name:
            return self.first_name + " " + nick + self.last_name
        return "[%s]" % self.username

    def has_perm(self, perm, obj=None):
        """
        Returns True if the user has the specified permission. This method
        queries all available auth backends, but returns immediately if any
        backend returns True. Thus, a user who has permission from a single
        auth backend is assumed to have permission in general. If an object is
        provided, permissions for this specific object are checked.

        This differs from the default in that superusers, while still having
        every permission, will be allowed after the logic has executed. This
        helps with typos in permission strings.
        """
        has_perm = _user_has_perm(self, perm, obj)
        # Active superusers have all permissions.
        if self.is_active and self.is_superuser:
            return True
        else:
            return has_perm

    @property
    def is_lnl(self):
        return self.groups.filter(Q(name="Alumni") | Q(name="Active") | Q(name="Officer") | Q(name="Associate") | Q(
                name="Away") | Q(name="Inactive")).exists()

    @property
    def is_complete(self):
        # if this returns false, the user will be constantly reminded to update their profile
        return self.first_name and self.last_name and self.email

    @property
    def group_str(self):
        groups = map(lambda l: l.name, self.groups.all())
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
        return ', '.join(map(str, self.orgowner.all()))

    @property
    def orgs(self):
        return ', '.join(map(str, self.orgusers.all()))

    @property
    def all_orgs(self):
        return Organization.objects.complex_filter(
            Q(user_in_charge=self) | Q(associated_users=self)
        ).distinct()

    @property
    def mdc_name(self):
        max_chars = 12
        clean_first, clean_last = "", ""

        # assume that Motorola can handle practically nothing. Yes, ugly, but I don't wanna regex 1000's of times
        for char in self.first_name.upper().strip():
            if ord(char) == ord(' ') or ord(char) == ord('-') \
                    or ord('0') <= ord(char) <= ord('9') or ord('A') <= ord(char) <= ord('Z'):
                clean_first += char
        for char in self.last_name.upper().strip():
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
