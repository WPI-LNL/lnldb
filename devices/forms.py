from crispy_forms.bootstrap import FormActions, Accordion, AccordionGroup, TabHolder, Tab
from crispy_forms.layout import Submit, Layout, Fieldset, HTML, Hidden, Field, Div, Row, Column
from crispy_forms.helper import FormHelper
from django import forms
from django.core.exceptions import ValidationError
from django.shortcuts import reverse
from .models import Laptop, MacOSApp
from data.forms import FieldAccessForm, FieldAccessLevel


class EnrollmentForm(forms.ModelForm):
    asset_tag = forms.CharField(required=True)

    def __init__(self, *args, **kwargs):
        self.helper = FormHelper()
        self.helper.form_class = 'form-horizontal col-md-6'
        self.helper.layout = Layout(
            Fieldset(
                'Complete Enrollment',
                HTML('<div class="col-md-12">'),
                HTML('<p>Please verify that the following information is correct.'),
                Field('name'),
                Field('serial', css_class='r'),
                Field('asset_tag'),
                Field('user_password'),
                Field('admin_password'),
                HTML('</div>')
            ),
            FormActions(
                Submit('save', 'Enroll')
            )
        )
        super(EnrollmentForm, self).__init__(*args, **kwargs)

    class Meta:
        model = Laptop
        fields = ('name', 'serial', 'asset_tag', 'user_password', 'admin_password')


class ClientForm(forms.Form):
    def __init__(self, *args, **kwargs):
        self.helper = FormHelper()
        self.helper.form_class = "form-horizontal col-md-6"
        self.helper.layout = Layout(
            Fieldset(
                'New Managed Device',
                Div(
                    HTML('<p style="font-weight: bold"><span style="color: red">WARNING:</span> Please read the '
                         'following statements carefully. The MDM is designed for use with LNL equipment only. Failure '
                         'to follow these instructions can lead to irreversible damage. Proceed with caution.</p>'),
                    HTML('<p>This interface supports macOS devices only. While MDM profiles can also be installed on '
                         'iOS, iPadOS, and tvOS devices, there is currently no enrollment process for those platforms. '
                         'To learn more about managing those types of devices, refer to the MDM User Guide.</p>'),
                    HTML('<p>To configure the new device to work with the MDM, you will first need to install the MDM '
                         'client. The client will be used to enroll the device and for communicating with the '
                         'management server. The installer will begin downloading automatically once you agree to the '
                         'terms below. Note that you may need administrator privileges to complete the installation.'
                         '</p>'),
                    HTML('<p>The MDM client installer comes with a few additional management features you may choose '
                         'to install alongside the client. Adding these extra features is completely optional. Before '
                         'installing additional packages, make sure you have read and fully understand the respective '
                         'README and any additional information that may be provided (i.e. Additional Terms and/or '
                         'Policies).</p>'),
                    HTML('<p>When setting up a new managed device:</p>'),
                    HTML('<ul><li>I understand that the MDM client and any other MDM configuration software is '
                         'intended solely for devices in LNL\'s inventory</li><li>I understand the risks associated '
                         'with using an MDM solution and will make every effort to read through all of the pertinent '
                         'documentation including, but not limited to: the MDM User Guide, relevant READMEs, and all '
                         'agreements and policies included with the software.</li><li>By using LNL MDM software on a '
                         'new device, I affirm that LNL owns the device, that the device is eligible for MDM '
                         'management, that I am authorized to manage the device, and that I have the authority to '
                         'agree to all of the relevant terms on behalf of everyone who will use the device.</li><li>I '
                         'agree to take full responsibility for any loss or damage that may result from improper use '
                         'of the MDM, or otherwise, and I understand that such damage may be permanent.</li><li>By '
                         'clicking "Agree", I accept the full MDM Terms of Use as well as any and all additional '
                         'terms that may be provided with the software.</li></ul><br>'),
                    FormActions(
                        HTML('<a href="{}" class="btn">Cancel</a>'.format(reverse("mdm:list"))),
                        Submit('save', 'Agree')
                    )
                )
            )
        )
        super(ClientForm, self).__init__(*args, **kwargs)


class RemovalForm(forms.Form):
    agree = forms.BooleanField(required=True, label="I have fully read the warnings above and will assume all "
                                                    "responsibility associated with performing this action.")
    client_removed = forms.BooleanField(required=True, label="MDM Client and plugins removed")
    profiles_removed = forms.BooleanField(required=True)

    def __init__(self, *args, **kwargs):
        uninstalled = False
        if 'uninstalled' in kwargs:
            uninstalled = kwargs.pop('uninstalled')
        self.helper = FormHelper()
        self.helper.form_class = "form-horizontal col-md-6"
        self.helper.layout = Layout(
            Fieldset(
                'Device Removal',
                Div(
                    HTML('<p style="font-weight: bold"><span style="color: red">WARNING:</span> Please read the '
                         'following statements carefully. Devices should only be removed from the MDM under limited '
                         'circumstances. Failure to follow these instructions can lead to irreversible damage. Proceed '
                         'with caution.</p>'),
                    HTML('<p>Before selling or giving away an enrolled device, pay careful attention to the '
                         'instructions below which will guide you through the process of removing the device from '
                         'management. Typically, devices that will remain in LNL\'s inventory should not be removed '
                         'from the MDM. However, in the event that the device has been wiped clean and will need a '
                         'fresh install of the MDM Client, you may use this interface to remove the old device record.'
                         '</p>'),
                    HTML('<p>By removing this device\'s enrollment record you understand the following:</p>'),
                    HTML('<ul><li>If the MDM Client, or any of its additional programs, have not been fully removed '
                         'from the device, the device may continue to communicate with the MDM. It may even re-enroll '
                         'itself. By checking the box below, you affirm that the MDM Client and all its programs have '
                         'been fully removed.</li>'),
                    'client_removed',
                    HTML('<li>Configuration profiles that are installed on the device should be removed prior to '
                         'removing the device from the MDM. Note that some profiles can be removed manually, while '
                         'others will require a command sent by the MDM. Before continuing, ensure that all of these '
                         'profiles have been removed. You can check for them in the System Preferences. By checking '
                         'the box below, you understand that failing to remove a profile could be permanent.</li>'),
                    'profiles_removed',
                    HTML('</ul>'),
                    'agree',
                    css_class="col-md-12"
                )
            ),
            FormActions(
                HTML('<a href="{}" class="btn">Cancel</a>'.format(reverse("mdm:list"))),
                Submit('save', 'Confirm')
            )
        )
        super(RemovalForm, self).__init__(*args, **kwargs)

        if uninstalled:
            self.fields['client_removed'] = forms.BooleanField(initial=True, disabled=True, label="MDM Client removed")


class ProfileForm(forms.Form):
    fields = {}

    # File Parameters
    display_name = forms.CharField(max_length=100, required=True, label="Profile Display Name")
    description = forms.CharField(widget=forms.Textarea, required=True, label="Profile Description",
                                  help_text="A description of the profile, shown on the detail screen for the profile. "
                                            "This should be descriptive enough to help the user understand what is "
                                            "contained within the profile.")
    filename = forms.CharField(max_length=64, required=True)
    scope = forms.ChoiceField(choices=(('System', 'System'), ('User', 'User')), required=True,
                              help_text="Determines if the profile should be installed system-wide or just for a "
                                        "specific user.")
    auto_remove = forms.ChoiceField(choices=(('default', 'Never'), ('expire', 'On date or after interval')),
                                    required=True, label="Automatically Remove Profile")
    removal_date = forms.SplitDateTimeField(required=False,
                                            help_text="The date on which the profile will be automatically removed")
    removal_period = forms.IntegerField(required=False, label="Duration Until Removal",
                                        help_text="Number of seconds until the profile is automatically removed. If "
                                                  "the \"Removal date\" key is also present, whichever field yields "
                                                  "the earliest date will be used.")
    version = forms.IntegerField()

    # Store Payload
    admin_install = forms.BooleanField(required=False, help_text="Restrict app installations to admin users.",
                                       label="Require Admin to Install Apps", initial=False)
    softwareupdate_only = forms.BooleanField(required=False,
                                             help_text="Restrict app installations to software updates only.",
                                             label="Restrict to Software Updates Only", initial=False)
    app_adoption = forms.BooleanField(required=False, help_text="Disable App Adoption by users.",
                                      label="Disable App Adoption")
    update_notifications = forms.BooleanField(required=False, label="Disable software update notifications.")
    store_version = forms.IntegerField(required=False)

    # Siri Payload
    siri_enabled = forms.BooleanField(required=False, label="Enable Siri")
    improve_siri = forms.ChoiceField(choices=((None, '--'), (0, 'Unseen'), (1, 'Enabled'), (2, 'Disabled')),
                                     required=False, label="Improve Siri & Dictation",
                                     help_text="Help improve Siri and Dictation by allowing Apple to store and review "
                                               "audio of your Siri and Dictation interactions on this device")
    siri_version = forms.IntegerField(required=False)

    # Desktop Payload
    locked = forms.BooleanField(required=False, help_text="If true, the desktop picture is locked.")
    desktop_path = forms.CharField(max_length=250, help_text="If supplied, it sets the path to the desktop picture.",
                                   required=False, label="Path")
    desktop_version = forms.IntegerField(required=False)

    # Dock Payload
    orientation = forms.ChoiceField(choices=((None, '--'), ('bottom', 'Bottom'), ('left', 'Left'), ('right', 'Right')),
                                    required=False, help_text="Orientation of the dock.")
    position = forms.BooleanField(required=False, help_text="If true, the position is locked.",
                                  label="Position Immutable")
    autohide = forms.BooleanField(required=False, help_text="If true, automatically hide and show the dock.")
    autohide_immutable = forms.BooleanField(required=False,
                                            help_text="If true, the Automatically Hide checkbox is disabled.")
    mini_app = forms.BooleanField(required=False, help_text="If true, enable the minimize-to-application feature.",
                                  label="Minimize to Application")
    magnify = forms.BooleanField(required=False, help_text="If true, magnification is active.", label="Magnification")
    magnify_immutable = forms.BooleanField(required=False, help_text="If true, the magnification checkbox is disabled.")
    magsize_immutable = forms.BooleanField(required=False, help_text="If true, the magnify slider is disabled.")
    process = forms.BooleanField(required=False, help_text="If true, show the process indicator.",
                                 label="Show Process Indicators")
    anim = forms.BooleanField(required=False, help_text="If true, animate opening applications.",
                              label="Launch Animation")
    anim_immutable = forms.BooleanField(required=False,
                                        help_text="If true, the Animate Opening Applications checkbox is disabled.",
                                        label="Launch Animation Immutable")
    mineffect = forms.ChoiceField(choices=((None, '--'), ('genie', 'Genie'), ('scale', 'Scale')), required=False,
                                  label="Minimize effect")
    mineffect_immutable = forms.BooleanField(required=False, label="Minimize Effect Immutable",
                                             help_text="If true, the Minimize Using popup is disabled")
    size_immutable = forms.BooleanField(required=False, help_text="If true, the size slider will be disabled.")
    content_immutable = forms.BooleanField(required=False, help_text="If true, the user cannot remove any item from or "
                                                                     "add any item to the dock.")
    app_name_0 = forms.CharField(max_length=200, required=False, label="Name")
    app_path_0 = forms.CharField(max_length=500, required=False, label="Path")
    extra_dock = forms.IntegerField(required=False)
    dock_version = forms.IntegerField(required=False)

    # Energy Payload
    disable_sleep = forms.BooleanField(required=False)
    ac_display_timer = forms.IntegerField(required=False, label="Display Sleep Timer",
                                          help_text="Minutes of inactivity before the display will be turned off, in "
                                                    "an integer value where 0 means never")
    ac_system_timer = forms.IntegerField(required=False, label="System Sleep Timer",
                                         help_text="Minutes of inactivity before the system will enter sleep mode, in "
                                                   "an integer value where 0 means never")
    ac_wake_lan = forms.BooleanField(required=False, label="Wake on LAN",
                                     help_text="Wake the system for network access")
    ac_wake_modem = forms.BooleanField(required=False, label="Wake on Modem Ring")
    ac_power_failure = forms.BooleanField(required=False, label="Start up Automatically After a Power Failure")
    battery_display_timer = forms.IntegerField(required=False, label="Display Sleep Timer",
                                               help_text="Minutes of inactivity before the display will be turned off, "
                                                         "in an integer value where 0 means never")
    battery_system_timer = forms.IntegerField(required=False, label="System Sleep Timer",
                                              help_text="Minutes of inactivity before the system will enter sleep "
                                                        "mode, in an integer value where 0 means never")
    battery_wake_lan = forms.BooleanField(required=False, label="Wake on LAN",
                                          help_text="Wake the system for network access")
    battery_wake_modem = forms.BooleanField(required=False, label="Wake on Modem Ring")
    battery_power_failure = forms.BooleanField(required=False, label="Start up Automatically After a Power Failure")
    energy_version = forms.IntegerField(required=False)

    # Filevault Payload
    filevault = forms.BooleanField(required=False, help_text="If true, FileVault will be disabled",
                                   label="Disable FileVault")
    filevault_version = forms.IntegerField(required=False)

    # Finder Payload
    preferred_style = forms.ChoiceField(choices=((None, '--'), ('icnv', 'Icon View'), ('Nlsv', 'List View'),
                                                 ('clmv', 'Column View'), ('glyv', 'Gallery View')), required=False,
                                        label="Preferred Finder View Style")
    window_target = forms.ChoiceField(choices=(
        (None, '--'), ('PfHm', 'User Home Folder'), ('PfCm', 'Computer'), ('PfDe', 'Desktop'), ('PfDo', 'Documents'),
        ('file:///System/Library/CoreServices/Finder.app/Contents/Resources/MyLibraries/myDocuments.cannedSearch',
         'Recents')), required=False, label="New Finder windows show...",
        help_text="New Finder windows will open to the selected location")
    warn_trash = forms.BooleanField(required=False, initial=True, label="Show warning before emptying the Trash")
    empty_trash = forms.BooleanField(required=False, label="Remove items from the Trash after 30 days")
    prohibit_goto = forms.BooleanField(required=False, label="Disable Go to Folder",
                                       help_text="Allows user to open files or folders by typing a pathname")
    prohibit_connect = forms.BooleanField(required=False, label="Disable Connect to Server",
                                          help_text="Opens a dialog box for finding servers on the network")
    show_connected = forms.BooleanField(required=False, label="Show Connected Servers",
                                        help_text="Show connected servers on the Desktop")
    ds_store = forms.BooleanField(required=False, label="Prevent .DS_Store file creation on network volumes",
                                  help_text="Prevent .DS_Store file creation when interacting with a remote file "
                                            "server using the Finder")
    finder_version = forms.IntegerField(required=False)

    # Firewall Payload
    firewall_enable = forms.BooleanField(required=False, label="Enable Firewall")
    block_all = forms.BooleanField(required=False, label="Block all incoming connections")
    stealth = forms.BooleanField(required=False, label="Enable Stealth Mode")
    extra_firewall = forms.IntegerField(required=False)
    firewall_version = forms.IntegerField(required=False)

    # iTunes Payload
    itunes_agreement = forms.BooleanField(required=False, label="Agree to iTunes Software License Agreement",
                                          help_text="Automatically accept the iTunes Software License Agreement on "
                                                    "launch")
    library_sharing = forms.BooleanField(required=False, label="Disable Library Info Sharing",
                                         help_text="Share details about your library with Apple")
    device_backups = forms.BooleanField(required=False, label="Disable Device Backups")
    apple_music = forms.BooleanField(required=False, label="Disable Apple Music")
    update_check = forms.BooleanField(required=False, label="Disable Checking for Updates")
    music_store = forms.BooleanField(required=False, label="Disable iTunes Store")
    shared_music = forms.BooleanField(required=False, label="Disable Shared Libraries")
    ipod_sync = forms.BooleanField(required=False, label="Prevent iPods, iPhones and iPads from syncing automatically")
    itunes_version = forms.IntegerField(required=False, label="iTunes version")

    # Login Window
    login_full_name = forms.BooleanField(required=False, label="Show Full Name",
                                         help_text="Set to true to show the name and password dialog. Set to false to "
                                                   "display a list of users.")
    disable_password_change = forms.BooleanField(required=False, label="Prevent user from changing password",
                                                 help_text="Disable the \"Change Password...\" button in the Users & "
                                                           "Groups preference pane.")
    retries_till_hint = forms.IntegerField(required=False, label="Show password hints after failed attempts",
                                           help_text="Number of tries until password hint is shown (0 = disable hints)")
    hide_admin = forms.BooleanField(required=False,
                                    help_text="When showing a user list, set to false to hide the administrator users.")
    host_info = forms.CharField(max_length=50,
                                help_text="If this key is included in the payload, its value will be displayed as "
                                          "additional computer information on the login window. See the Configuration "
                                          "Profile Reference documentation for more information.", required=False,
                                label="Admin Host Info")
    shutdown = forms.BooleanField(required=False, label="Disable Shutdown",
                                  help_text="If set to true, the Shut Down button item will be hidden.")
    restart = forms.BooleanField(required=False, label="Disable Restart",
                                 help_text="If set to true, the Restart item will be hidden.")
    sleep = forms.BooleanField(required=False, label="Disable Sleep",
                               help_text="If set to true, the Sleep button item will be hidden.")
    console = forms.BooleanField(required=False, label="Disable Console Access",
                                 help_text="If set to true, the Other user will disregard use of the '>console' "
                                           "special user name")
    shutdown_loggedin = forms.BooleanField(required=False, label="Disable Shutdown while logged in",
                                           help_text="If set to true, the Shut Down menu item will be disabled when "
                                                     "the user is logged in")
    restart_loggedin = forms.BooleanField(required=False, label="Disable Restart while logged in",
                                          help_text="If set to true, the Restart menu item will be disabled when the "
                                                    "user is logged in")
    power_loggedin = forms.BooleanField(required=False, label="Disable Power Off while logged in",
                                        help_text="If set to true, the Power Off menu item will be disabled when the "
                                                  "user is logged in")
    text = forms.CharField(max_length=500, label="Login Window Text", required=False)
    screen_lock = forms.BooleanField(required=False, label="Disable Immediate Screen Lock",
                                     help_text="If set to true, the immediate Screen Lock functions will be disabled")
    login_version = forms.IntegerField(required=False)

    # Passcode Policy Payload
    passcode_simple = forms.BooleanField(required=False, label="Allow Simple Passcode",
                                         help_text="A simple passcode is defined as containing repeated characters, or "
                                                   "increasing/decreasing characters (such as 123 or CBA)")
    passcode_force = forms.BooleanField(required=False, label="Force PIN",
                                        help_text="Determines whether the user is forced to set a PIN")
    passcode_attempts = forms.IntegerField(required=False, label="Maximum Failed Attempts", max_value=11, min_value=2,
                                           help_text="Allowed range [2...11]. Specifies the number of allowed failed "
                                                     "attempts to enter the passcode at the device's lock screen. Once "
                                                     "this number is exceeded, the device is locked.")
    time_reset = forms.IntegerField(required=False, label="Minutes Until Failed Login Reset", min_value=1,
                                    help_text="This can be set to the number of minutes before the login will be reset "
                                              "after the maxFailedAttempts unsuccessful attempts has been reached. "
                                              "This key requires setting maxFailedAttempts.")
    pin_inactivity = forms.IntegerField(required=False, label="Maximum Inactivity", min_value=1,
                                        help_text="Specifies the maximum number of minutes for which the device can be "
                                                  "idle (without being unlocked by the user) before it gets locked by "
                                                  "the system. Will be interpreted as screensaver settings.")
    pin_age = forms.IntegerField(required=False,
                                 help_text="Specifies the number of days for which the passcode can remain unchanged. "
                                           "After this number of days, the user is forced to change the passcode "
                                           "before the device can be unlocked.")
    complexity = forms.IntegerField(required=False, label="Minimum Complex Characters",
                                    help_text="Specifies the minimum number of complex characters that a passcode must "
                                              "contain. A \"complex\" character is a character other than a number or "
                                              "a letter, such as &%$#")
    pin_min_length = forms.IntegerField(required=False, label="Minimum Length",
                                        help_text="Specifies the minimum overall length of the passcode")
    alpha = forms.BooleanField(required=False, label="Require Alphanumeric",
                               help_text="Specifies whether the user must also enter alphabetic characters ('abcd') "
                                         "along with numbers, or if numbers only are sufficient")
    pin_history = forms.IntegerField(required=False, min_value=1, max_value=50,
                                     help_text="When the user changes the passcode, it has to be unique within the last"
                                               " N entries in the history. Minimum value is 1, maximum value is 50.")
    grace_period = forms.IntegerField(required=False, label="Maximum Grace Period",
                                      help_text="The maximum grace period, in minutes, to unlock without entering a "
                                                "passcode. Default is 0, that is no grace period, which requires "
                                                "entering a passcode immediately. This will be interpreted as "
                                                "screensaver settings.")
    force_reset = forms.BooleanField(required=False, label="Change at next login",
                                     help_text="Setting this to true will cause a password reset to occur the next "
                                               "time the user tries to authenticate. If this key is set in a device "
                                               "profile, the setting takes effect for all users, and admin "
                                               "authentications may fail until the admin user password is also reset")
    passcode_version = forms.IntegerField(required=False)

    # Removal Password
    enable_protection = forms.BooleanField(required=False, label="Enable Removal Password",
                                           help_text="Requires a password to remove the profile from the device. "
                                                     "Enabling this will use the password supplied by the LNL MDM.")
    password_version = forms.IntegerField(required=False)

    # Restrictions Payload
    ad_tracking = forms.BooleanField(required=False, label="Force Limited Ad Tracking",
                                     help_text="Enabling this opts out of receiving ads targeted to interests in Apple "
                                               "Maps and macOS devices. May still receive the same number of ads, but "
                                               "the ads may be less relevant.")
    disable_assistant = forms.BooleanField(required=False, label="Disable Siri", help_text="When true, disables Siri")
    disable_camera = forms.BooleanField(required=False, help_text="When true, the camera is completely disabled")
    cloud_bookmarks = forms.BooleanField(required=False, label="Disable iCloud Bookmarks", help_text="Disallows iCloud "
                                                                                                     "Bookmark sync")
    cloud_mail = forms.BooleanField(required=False, label="Disable iCloud Mail",
                                    help_text="Disallows Mail iCloud services")
    cloud_cal = forms.BooleanField(required=False, label="Disable iCloud Calendars",
                                   help_text="Disallows iCloud Calendar services")
    cloud_reminders = forms.BooleanField(required=False, label="Disable iCloud Reminders",
                                         help_text="Disallows iCloud Reminder services")
    cloud_address = forms.BooleanField(required=False, label="Disable iCloud Address Book",
                                       help_text="Disallows iCloud Address Book services")
    cloud_notes = forms.BooleanField(required=False, label="Disable iCloud Notes",
                                     help_text="Disallows iCloud Notes services")
    cloud_doc_sync = forms.BooleanField(required=False, label="Disable iCloud Document Sync",
                                        help_text="Disables document and key-value syncing to iCloud")
    cloud_keychain = forms.BooleanField(required=False, label="Disable iCloud Keychain",
                                        help_text="Disables iCloud keychain synchronization")
    caching = forms.BooleanField(required=False, label="Disable Content Caching")
    disable_touchid = forms.BooleanField(required=False, label="Disallow TouchID for Unlock",
                                         help_text="Prevents Touch ID from unlocking the device")
    itunes_file_share = forms.BooleanField(required=False, label="Disable iTunes File Sharing",
                                           help_text="When true, iTunes application file sharing services are disabled")
    disable_airdrop = forms.BooleanField(required=False, label="Disable AirDrop")
    disable_handoff = forms.BooleanField(required=False, label="Disable Handoff")
    spotlight_internet = forms.BooleanField(required=False, label="Disable Spotlight Internet Results",
                                            help_text="If true, Spotlight will not return Internet search results")
    disable_screenshot = forms.BooleanField(required=False, label="Disable Screenshots",
                                            help_text="Users won't be able to save a screenshot of the display and "
                                                      "will be prevented from capturing a screen recording")
    disable_autounlock = forms.BooleanField(required=False, label="Disable Auto Unlock")
    cloud_docs_desk = forms.BooleanField(required=False, label="Disable iCloud Documents and Desktop",
                                         help_text="Disallows cloud desktop and document services")
    pass_autofill = forms.BooleanField(required=False, label="Disable Password AutoFill",
                                       help_text="Users won't be able to use the AutoFill Passwords feature and will "
                                                 "not be prompted to use a saved password in Safari")
    pass_proximity = forms.BooleanField(required=False, label="Disable Password Proximity Requests",
                                        help_text="If true, a user's device will not request passwords from nearby "
                                                  "devices")
    pass_share = forms.BooleanField(required=False, label="Disable Password Sharing",
                                    help_text="If true, users can not share their passwords with the Airdrop "
                                              "Passwords feature")
    restrictions_version = forms.IntegerField(required=False)

    # Safari Payload
    homepage = forms.CharField(max_length=64, required=False, help_text="Homepage URL")
    new_window = forms.ChoiceField(choices=((None, '--'), (0, 'Homepage'), (1, 'Empty Page'),
                                            (2, 'Same page as current window'), (3, 'Bookmarks')), required=False,
                                   label="Contents of New Windows", help_text="Policy for new window contents")
    new_tab = forms.ChoiceField(choices=((None, '--'), (0, 'Show Homepage'), (1, 'Show Empty Page'),
                                         (2, 'Show same page as current window'), (3, 'Show Bookmarks')),
                                required=False, label="Contents of New Tabs", help_text="Policy for new tab contents")
    tab_policy = forms.ChoiceField(choices=((None, '--'), (0, 'Never'), (1, 'Automatically'), (2, 'Always')),
                                   required=False, label="Open pages in tabs instead of windows")
    command_click = forms.BooleanField(required=False, label="&#8984;-click opens a link in a new tab", initial=True,
                                       help_text="Open command-clicked links in a new tab rather than a new window")
    history_limit = forms.ChoiceField(choices=((None, '--'), (1, 'After one day'), (7, 'After one week'),
                                               (14, 'After two weeks'), (31, 'After one month'),
                                               (365, 'After one year'), (365000, 'Manually')), required=False,
                                      label="History Age Limit",
                                      help_text="Policy for when to automatically remove items from History")
    downloads_path = forms.CharField(max_length=64, required=False, label="Downloads Location",
                                     help_text="File system path (can start with ~) where downloaded files will be "
                                               "saved")
    downloads_clear = forms.ChoiceField(choices=((None, '--'), (0, 'Manually'), (1, 'When Safari quits'),
                                                 (2, 'Upon successful download')), required=False,
                                        label="Downloads Clearing Policy",
                                        help_text="Policy for when to remove items from the Downloads window")
    safe_downloads = forms.BooleanField(required=False, label="Open Safe Downloads Automatically",
                                        help_text="Automatically open downloaded files that are of certain well-known "
                                                  "safe types")
    multiple_pages = forms.BooleanField(required=False, label="Confirm Closing Multiple Pages",
                                        help_text="Display a confirmation alert when multiple pages are closed at once")
    default_browser = forms.BooleanField(required=False, label="Suppress Default Web Browser Prompt",
                                         help_text="When Safari is quit for the first time, if it detects it is not "
                                                   "configured as the default browser it will present a prompt to the "
                                                   "user to choose whether to keep the current default browser or "
                                                   "change it to Safari. Enable this to suppress this prompt.")
    autofill_address = forms.BooleanField(required=False, label="AutoFill web forms from contacts",
                                          help_text="Autofill web forms using info from Contacts")
    autofill_forms = forms.BooleanField(required=False, label="AutoFill Miscellaneous Forms",
                                        help_text="Autofill web forms using previously-typed text")
    plugins = forms.BooleanField(required=False, label="Enable Plug-ins", initial=True)
    java = forms.BooleanField(required=False, label="Enable Java", initial=True)
    javascript = forms.BooleanField(required=False, label="Enable JavaScript", initial=True)
    insecure_forms = forms.BooleanField(required=False, label="Ask Before Submitting Insecure Forms",
                                        help_text="Display a confirmation alert when an insecure form is submitted "
                                                  "from a secure site")
    private_browsing = forms.BooleanField(required=False, label="Private Browsing",
                                          help_text="Prevent Safari from keeping track of most user activities")
    cookies = forms.ChoiceField(choices=((None, '--'), (0, 'Always'), (1, 'Never'),
                                         (2, 'Third Parties except sites you visited'), (3, 'Third Parties')),
                                required=False, label="Block cookies and other website data")
    disallow_notifications = forms.BooleanField(required=False, label="Disallow Notifications",
                                                help_text="Prevent websites from requesting permission to send "
                                                          "notifications")
    tab_links = forms.BooleanField(required=False, label="Press Tab to highlight each item on a webpage",
                                   help_text="Highlight links and form controls as you press the Tab key")
    safari_version = forms.IntegerField(required=False)

    # Screensaver Payload
    screensaver_password = forms.BooleanField(required=False, label="Require Password",
                                              help_text="If true, the user will be prompted for a password when the "
                                                        "screensaver is unlocked or stopped. When using this, "
                                                        "Password Delay must also be provided.")
    screensaver_delay = forms.IntegerField(required=False, label="Password Delay",
                                           help_text="Number of seconds to delay before the password will be required "
                                                     "to unlock or stop the screen saver (the \"grace period\"). A "
                                                     "value of 2147483647 (eg 0x7FFFFFFF) can be used to disable this "
                                                     "requirement.")
    screensaver_path = forms.CharField(max_length=250, label="Path", required=False,
                                       help_text="A full path to the screen saver module to be used")
    screensaver_idle = forms.IntegerField(required=False, label="Login Window Idle Time",
                                          help_text="Number of seconds of inactivity before screensaver activates. "
                                                    "(0=never activate).")
    screensaver_version = forms.IntegerField(required=False)

    # Setup Payload
    skip_cloud = forms.BooleanField(required=False, label="Skip Apple ID Setup")
    skip_siri = forms.BooleanField(required=False, label="Skip Siri Setup")
    skip_privacy = forms.BooleanField(required=False, label="Skip Privacy Consent Window")
    skip_cloud_storage = forms.BooleanField(required=False, label="Skip iCloud Storage Setup")
    skip_true_tone = forms.BooleanField(required=False, label="Skip True Tone Display Window")
    skip_appearance = forms.BooleanField(required=False, label="Skip the Choose Your Look Window")
    setup_version = forms.IntegerField(required=False)

    # Software Payload
    disable_beta = forms.BooleanField(required=False, label="Disallow Pre-Release Software",
                                      help_text="Users will be unable to install prerelease software on this computer")
    auto_check = forms.BooleanField(required=False, label="Automatically check for updates")
    auto_download = forms.BooleanField(required=False, label="Download newly available updates in the background")
    os_auto = forms.BooleanField(required=False, label="Automatically install macOS updates")
    app_auto = forms.BooleanField(required=False, label="Automatically install App Store app updates")
    config_install = forms.BooleanField(required=False,
                                        label="Install XProtect, MRT, & Gatekeeper updates automatically")
    software_version = forms.IntegerField(required=False)

    # Submit Diagnostic Information Payload
    diagnostics = forms.BooleanField(required=False, label="Automatically Submit Diagnostic Information",
                                     help_text="If true, will automatically submit diagnostic information to Apple")
    diagnostics_version = forms.IntegerField(required=False)

    # Policy Payload
    policy_enable = forms.BooleanField(required=False, label="Enable Gatekeeper",
                                       help_text="Leaving this unchecked will disable Gatekeeper. Disabling Gatekeeper "
                                                 "is highly discouraged.")
    developers_policy = forms.BooleanField(required=False, label="Allow Identified Developers",
                                           help_text="If true, Gatekeeper's \"Mac App Store and identified developers\""
                                                     " option will be chosen. If false, Gatekeeper's \"Mac App Store\" "
                                                     "option will be chosen.")
    disable_context = forms.BooleanField(required=False, label="Disable System Policy Override",
                                         help_text="If true, the Finder's contextual menu item will be disabled")
    policy_version = forms.IntegerField(required=False)

    # System Preferences Payload
    enabled_panes = forms.MultipleChoiceField(choices=[], widget=forms.CheckboxSelectMultiple, label="Enabled",
                                              required=False)
    disabled_panes = forms.MultipleChoiceField(choices=[], widget=forms.CheckboxSelectMultiple, label="Disabled",
                                               required=False)
    hidden_panes = forms.MultipleChoiceField(choices=[], widget=forms.CheckboxSelectMultiple, label="Hidden",
                                             required=False)
    lockmessage_ui = forms.BooleanField(required=False, label="Prevent user from setting lock message")
    password_change = forms.BooleanField(required=False, label="Prevent user from changing password")
    preferences_version = forms.IntegerField(required=False)

    # Time Machine Payload
    auto_backup = forms.BooleanField(required=False, label="Enable automatic backups",
                                     help_text="Automatically backup at regular intervals")
    backup_volumes = forms.BooleanField(required=False, label="Backup all volumes",
                                        help_text="Only startup volume is backed up by default")
    backup_sys = forms.BooleanField(required=False, label="Backup system files and folders",
                                    help_text="System files and folders are skipped by default")
    mobile_backups = forms.BooleanField(required=False, label="Enable local snapshots",
                                        help_text="Creates local backup snapshots if the backup destination is offline")
    backup_url = forms.CharField(max_length=64, required=False, label="Backup Destination",
                                 help_text="URL of the backup destination (e.g. smb://server.example.com/backups)")
    backup_size = forms.IntegerField(required=False, label="Backup size limit",
                                     help_text="Enter a limit in MB for the size of the backup. Set to 0 for unlimited")
    time_machine_version = forms.IntegerField(required=False)

    # Initialize form
    def __init__(self, *args, **kwargs):
        extra_dock = kwargs.pop('extra_dock')
        extra_firewall = kwargs.pop('extra_firewall')
        edit_mode = kwargs.pop('edit_mode')
        self.helper = FormHelper()
        self.helper.form_class = "form-horizontal col-md-12"
        super(ProfileForm, self).__init__(*args, **kwargs)

        # Create Dock and Firewall Fieldsets dynamically
        dock = AccordionGroup('Dock', HTML('<div class="col-md-12">'), 'orientation', 'position', 'autohide',
                              'autohide_immutable', 'mini_app', 'magnify', 'magnify_immutable', 'magsize_immutable',
                              'process', 'anim', 'anim_immutable', 'mineffect', 'mineffect_immutable', 'size_immutable',
                              'content_immutable', Hidden('extra_dock', extra_dock),
                              HTML('<br><h5>Static Apps</h5><div class="col-md-12"><label>App #1</label>'),
                              'app_name_0', 'app_path_0', HTML('<hr>'))
        firewall = AccordionGroup('Firewall',
                                  HTML('<div class="col-md-12"><p>* Only valid for System level profiles</p>'),
                                  'firewall_enable', 'block_all', 'stealth', Hidden('extra_firewall', extra_firewall),
                                  HTML('<br><h5>Applications</h5><div class="col-md-12">'))
        submit_btns = FormActions(
            Submit('save', 'Generate')
        )
        if edit_mode:
            submit_btns = FormActions(
                Submit('save', 'Save Changes'),
                Submit('save', 'Save and Redeploy')
            )
        self.helper.layout = Layout(
            Row(
                Column(
                    Fieldset(
                        'Configuration Profile - Main Parameters',
                        HTML('<div class="col-md-12">'),
                        'display_name',
                        'description',
                        'filename',
                        'scope',
                        'auto_remove',
                        'removal_date',
                        'removal_period',
                        'version',
                        HTML('<p><br><br></p></div>')
                    ),
                    css_class='col-md-6'
                ),
                Column(
                    Fieldset(
                        'Payloads',
                        Accordion(
                            AccordionGroup(
                                'App Store',
                                HTML('<div class="col-md-12">'),
                                'admin_install',
                                'softwareupdate_only',
                                'app_adoption',
                                'update_notifications',
                                'store_version',
                                HTML('</div>')
                            ),
                            AccordionGroup(
                                'Siri',
                                HTML('<div class="col-md-12">'),
                                'siri_enabled',
                                'improve_siri',
                                'siri_version',
                                HTML('</div>')
                            ),
                            AccordionGroup(
                                'Desktop',
                                HTML('<div class="col-md-12">'),
                                'locked',
                                'desktop_path',
                                'desktop_version',
                                HTML('</div>')
                            ),
                            dock,
                            AccordionGroup(
                                'Energy Saver',
                                HTML('<div class="col-md-12">'),
                                'disable_sleep',
                                TabHolder(
                                    Tab(
                                        'Power Adapter',
                                        'ac_display_timer',
                                        'ac_system_timer',
                                        'ac_wake_lan',
                                        'ac_wake_modem',
                                        'ac_power_failure',
                                        css_class='col-md-12'
                                    ),
                                    Tab(
                                        'Battery',
                                        'battery_display_timer',
                                        'battery_system_timer',
                                        'battery_wake_lan',
                                        'battery_wake_modem',
                                        'battery_power_failure',
                                        css_class='col-md-12'
                                    ),
                                ),
                                'energy_version',
                                HTML('</div>')
                            ),
                            AccordionGroup(
                                'FileVault',
                                HTML('<div class="col-md-12">'),
                                'filevault',
                                'filevault_version',
                                HTML('</div>')
                            ),
                            AccordionGroup(
                                'Finder',
                                HTML('<div class="col-md-12">'),
                                'preferred_style',
                                'window_target',
                                'warn_trash',
                                'empty_trash',
                                'prohibit_goto',
                                'prohibit_connect',
                                'show_connected',
                                'ds_store',
                                'finder_version',
                                HTML('</div>')
                            ),
                            firewall,
                            AccordionGroup(
                                'iTunes',
                                HTML('<div class="col-md-12">'),
                                'itunes_agreement',
                                'library_sharing',
                                'device_backups',
                                'apple_music',
                                'update_check',
                                'music_store',
                                'shared_music',
                                'ipod_sync',
                                'itunes_version',
                                HTML('</div>')
                            ),
                            AccordionGroup(
                                'Loginwindow',
                                HTML('<div class="col-md-12">'),
                                'login_full_name',
                                'disable_password_change',
                                'retries_till_hint',
                                'hide_admin',
                                'host_info',
                                'shutdown',
                                'restart',
                                'sleep',
                                'console',
                                'shutdown_loggedin',
                                'restart_loggedin',
                                'power_loggedin',
                                'text',
                                'screen_lock',
                                'login_version',
                                HTML('</div>')
                            ),
                            AccordionGroup(
                                'Passcode Policy',
                                HTML('<div class="col-md-12">'),
                                'passcode_simple',
                                'passcode_force',
                                'passcode_attempts',
                                'time_reset',
                                'pin_inactivity',
                                'pin_age',
                                'complexity',
                                'pin_min_length',
                                'alpha',
                                'pin_history',
                                'grace_period',
                                'force_reset',
                                'passcode_version',
                                HTML('</div>')
                            ),
                            AccordionGroup(
                                'Profile Removal Password',
                                HTML('<div class="col-md-12">'),
                                'enable_protection',
                                'password_version',
                                HTML('</div>')
                            ),
                            AccordionGroup(
                                'Restrictions',
                                HTML('<div class="col-md-12">'),
                                'ad_tracking',
                                'disable_assistant',
                                'disable_camera',
                                'cloud_bookmarks',
                                'cloud_mail',
                                'cloud_cal',
                                'cloud_reminders',
                                'cloud_address',
                                'cloud_notes',
                                'cloud_doc_sync',
                                'cloud_docs_desk',
                                'cloud_keychain',
                                'caching',
                                'disable_touchid',
                                'itunes_file_sharing',
                                'disable_airdrop',
                                'disable_handoff',
                                'spotlight_internet',
                                'disable_screenshot',
                                'disable_autounlock',
                                'pass_autofill',
                                'pass_proximity',
                                'pass_share',
                                'restrictions_version',
                                HTML('</div>')
                            ),
                            AccordionGroup(
                                'Safari',
                                HTML('<div class="col-md-12">'),
                                'homepage',
                                'new_window',
                                'new_tab',
                                'tab_policy',
                                'command_click',
                                'history_limit',
                                'downloads_path',
                                'downloads_clear',
                                'safe_downloads',
                                'multiple_pages',
                                'default_browser',
                                'autofill_address',
                                'autofill_forms',
                                'plugins',
                                'java',
                                'javascript',
                                'insecure_forms',
                                'private_browsing',
                                'cookies',
                                'disallow_notifications',
                                'tab_links',
                                'safari_version',
                                HTML('</div>')
                            ),
                            AccordionGroup(
                                'Screensaver',
                                HTML('<div class="col-md-12">'),
                                'screensaver_password',
                                'screensaver_delay',
                                'screensaver_path',
                                'screensaver_idle',
                                'screensaver_version',
                                HTML('</div>')
                            ),
                            AccordionGroup(
                                'Setup Assistant',
                                HTML('<div class="col-md-12">'),
                                'skip_cloud',
                                'skip_siri',
                                'skip_privacy',
                                'skip_cloud_storage',
                                'skip_true_tone',
                                'skip_appearance',
                                'setup_version',
                                HTML('</div>')
                            ),
                            AccordionGroup(
                                'Software',
                                HTML('<div class="col-md-12"><p>* Intended for System level profiles</p>'),
                                'disable_beta',
                                'auto_check',
                                'auto_download',
                                'os_auto',
                                'app_auto',
                                'config_install',
                                'software_version',
                                HTML('</div>')
                            ),
                            AccordionGroup(
                                'Diagnostic Info',
                                HTML('<div class="col-md-12">'),
                                'diagnostics',
                                'diagnostics_version',
                                HTML('</div>')
                            ),
                            AccordionGroup(
                                'System Policy',
                                HTML('<div class="col-md-12"><p>* Only valid with System level profiles</p>'),
                                'policy_enable',
                                'developers_policy',
                                'disable_context',
                                'policy_version',
                                HTML('</div>')
                            ),
                            AccordionGroup(
                                'System Preferences',
                                Row(
                                    Column('enabled_panes', css_class='col-md-4'),
                                    Column('disabled_panes', css_class='col-md-4'),
                                    Column('hidden_panes', css_class='col-md-4'),
                                    css_class='col-md-12'
                                ),
                                HTML('<div class="col-md-12" style="margin-top: 3%"></div>'),
                                Fieldset(
                                    'Security',
                                    'lockmessage_ui',
                                    'password_change',
                                    'preferences_version',
                                    css_class='col-md-12'
                                ),
                            ),
                            AccordionGroup(
                                'Time Machine',
                                HTML('<div class="col-md-12"><p>* Only valid with System level profiles</p>'),
                                'auto_backup',
                                'backup_volumes',
                                'backup_sys',
                                'mobile_backups',
                                'backup_url',
                                'backup_size',
                                'time_machine_version',
                                HTML('</div>')
                            )
                        ),
                        css_class='col-md-6'
                    ),
                ),
                css_class='form-row'
            ),
            HTML("<p><br><br></p>"),
            submit_btns
        )
        super(ProfileForm, self).__init__(*args, **kwargs)

        self.fields['filename'].widget = forms.HiddenInput()

        for i in range(extra_dock):
            name = 'app_name_%s' % str(i + 1)
            path = 'app_path_%s' % str(i + 1)
            self.fields[name] = forms.CharField(max_length=200, required=False, label="Name")
            self.fields[path] = forms.CharField(max_length=500, required=False, label="Path")
            dock.fields.append(HTML('<label>App #%s</label>' % str(i + 2)))
            dock.fields.append(name)
            dock.fields.append(path)
            dock.fields.append(HTML('<hr>'))
        dock.fields.append(Submit('save', '+ Add App'))
        dock.fields.append(HTML('<p>&nbsp;</p></div>'))
        dock.fields.append('dock_version')
        dock.fields.append(HTML('</div>'))

        for j in range(extra_firewall):
            bundle_id = 'id_%s' % str(j + 1)
            allowed = 'permit_%s' % str(j + 1)
            self.fields[bundle_id] = forms.CharField(max_length=300, required=False, label="BundleID")
            self.fields[allowed] = forms.BooleanField(required=False, label="Connections Allowed")
            firewall.fields.append(HTML('<label>Application #%s</label>' % str(j + 1)))
            firewall.fields.append(bundle_id)
            firewall.fields.append(allowed)
            firewall.fields.append(HTML('<hr>'))
        firewall.fields.append(Submit('save', 'Add App'))
        firewall.fields.append(HTML('<p>&nbsp;</p></div>'))
        firewall.fields.append('firewall_version')
        firewall.fields.append(HTML('</div>'))

        preference_panes = [('com.apple.preference.universalaccess', 'Accessibility'),
                            ('com.apple.preferences.Bluetooth', 'Bluetooth'),
                            ('com.apple.preference.datetime', 'Date & Time'),
                            ('com.apple.preference.dock', 'Dock'),
                            ('com.apple.preferences.FamilySharingPrefPane', 'Family Sharing'),
                            ('com.apple.preferences.icloud', 'iCloud'),
                            ('com.apple.preference.keyboard', 'Keyboard'),
                            ('com.apple.preference.notifications', 'Notifications'),
                            ('com.apple.preferences.sharing', 'Sharing'),
                            ('com.apple.preferences.softwareupdate', 'Software Update'),
                            ('com.apple.preference.startupdisk', 'Startup Disk'),
                            ('com.apple.preference.trackpad', 'Trackpad'),
                            ('com.apple.Xsan', 'Xsan'),
                            ('com.apple.preferences.users', 'Users & Groups'),
                            ('com.apple.prefs.backup', 'Time Machine'),
                            ('com.apple.preference.sound', 'Sound'),
                            ('com.apple.preference.sidecar', 'Sidecar'),
                            ('com.apple.preference.screentime', 'Screentime'),
                            ('com.apple.preferences.parentalcontrols', 'Parental Controls'),
                            ('com.apple.preference.mouse', 'Mouse'),
                            ('com.apple.Localization', 'Language & Region'),
                            ('com.apple.preference.ink', 'Ink'),
                            ('com.apple.preference.energysaver', 'Energy Saver'),
                            ('com.apple.preference.desktopscreeneffect', 'Desktop & Screen Saver'),
                            ('com.apple.preference.digihub.discs', 'CDs & DVDs'),
                            ('com.apple.preferences.appstore', 'App Store'),
                            ('com.apple.preferences.AppleIDPrefPane', 'Apple ID'),
                            ('com.apple.preference.displays', 'Displays'),
                            ('com.apple.preferences.extensions', 'Extensions'),
                            ('com.apple.preference.general', 'General'),
                            ('com.apple.preferences.internetaccounts', 'Internet Accounts'),
                            ('com.apple.preference.expose', 'Mission Control'),
                            ('com.apple.preference.network', 'Network'),
                            ('com.apple.preference.printfax', 'Printers & Scanners'),
                            ('com.apple.preference.security', 'Security & Privacy'),
                            ('com.apple.preference.speech', 'Siri'),
                            ('com.apple.preference.spotlight', 'Spotlight'),
                            ('com.apple.preferences.password', 'Touch ID'),
                            ('com.apple.preferences.wallet', 'Wallet & Apple Pay'),
                            ('com.apple.preferences.configurationprofiles', 'Profiles')]

        self.fields['enabled_panes'].choices = preference_panes
        self.fields['disabled_panes'].choices = preference_panes
        self.fields['hidden_panes'].choices = preference_panes

    def clean_store_version(self):
        data = self.cleaned_data['admin_install']
        data |= self.cleaned_data['softwareupdate_only']
        data |= self.cleaned_data['app_adoption']
        data |= self.cleaned_data['update_notifications']
        store_version = self.cleaned_data['store_version']

        if data and store_version is None:
            raise ValidationError('You must provide a valid version number')
        return store_version

    def clean_siri_version(self):
        enabled = self.cleaned_data['siri_enabled']
        improve = self.cleaned_data['improve_siri']
        version = self.cleaned_data['siri_version']

        if enabled or improve not in [None, '']:
            if version is None:
                raise ValidationError('You must provide a valid version number')
        return version

    def clean_desktop_version(self):
        locked = self.cleaned_data['locked']
        path = self.cleaned_data['desktop_path']
        desktop_version = self.cleaned_data['desktop_version']

        if locked is True or path not in [None, '']:
            if desktop_version is None:
                raise ValidationError('You must provide a valid version number')
        return desktop_version

    def clean_dock_version(self):
        first_app = self.cleaned_data['app_name_0']
        orientation = self.cleaned_data['orientation']
        effect = self.cleaned_data['mineffect']
        data = self.cleaned_data['position']
        data |= self.cleaned_data['autohide']
        data |= self.cleaned_data['autohide_immutable']
        data |= self.cleaned_data['mini_app']
        data |= self.cleaned_data['magnify']
        data |= self.cleaned_data['magnify_immutable']
        data |= self.cleaned_data['magsize_immutable']
        data |= self.cleaned_data['process']
        data |= self.cleaned_data['anim']
        data |= self.cleaned_data['anim_immutable']
        data |= self.cleaned_data['mineffect_immutable']
        data |= self.cleaned_data['size_immutable']
        data |= self.cleaned_data['content_immutable']
        dock_version = self.cleaned_data['dock_version']

        if orientation not in [None, ''] or effect not in [None, ''] or data:
            if dock_version is None:
                raise ValidationError('You must provide a valid version number')
        if first_app not in [None, ''] and dock_version is None:
            raise ValidationError('You must provide a valid version number')
        return dock_version

    def clean_energy_version(self):
        sleep = self.cleaned_data['disable_sleep']
        ac_display = self.cleaned_data['ac_display_timer']
        ac_system = self.cleaned_data['ac_system_timer']
        ac_data = self.cleaned_data['ac_wake_lan']
        ac_data |= self.cleaned_data['ac_wake_modem']
        ac_data |= self.cleaned_data['ac_power_failure']
        battery_display = self.cleaned_data['battery_display_timer']
        battery_system = self.cleaned_data['battery_system_timer']
        battery_data = self.cleaned_data['battery_wake_lan']
        battery_data |= self.cleaned_data['battery_wake_modem']
        battery_data |= self.cleaned_data['battery_power_failure']
        version = self.cleaned_data['energy_version']

        if ac_display is not None or ac_system is not None or battery_display is not None or battery_system is not None:
            if sleep:
                raise ValidationError('The sleep timers have no effect with Sleep disabled')
        if ac_data or battery_data or ac_display is not None or ac_system is not None or battery_display is not None \
                or battery_system is not None or sleep:
            if version is None:
                raise ValidationError('You must provide a valid version number')
        return version

    def clean_finder_version(self):
        style = self.cleaned_data.get('preferred_style', None)
        target = self.cleaned_data.get('window_target', None)
        data = self.cleaned_data['empty_trash']
        data |= self.cleaned_data['prohibit_goto']
        data |= self.cleaned_data['prohibit_connect']
        data |= self.cleaned_data['show_connected']
        data |= self.cleaned_data['ds_store']
        version = self.cleaned_data['finder_version']

        if style not in [None, ''] or target not in [None, ''] or data:
            if version is None:
                raise ValidationError('You must provide a valid version number')
        return version

    def clean_filevault_version(self):
        disabled = self.cleaned_data['filevault']
        version = self.cleaned_data['filevault_version']

        if disabled and version is None:
            raise ValidationError('You must provide a valid version number')
        return version

    def clean_firewall_version(self):
        data = self.cleaned_data['firewall_enable']
        block_all = self.cleaned_data['block_all']
        stealth = self.cleaned_data['stealth']
        version = self.cleaned_data['firewall_version']

        if block_all or stealth:
            if not data:
                raise ValidationError('Firewall must be enabled to configure any additional options')
        data |= block_all
        data |= stealth
        if data and version is None:
            raise ValidationError('You must provide a valid version number')
        return version

    def clean_itunes_version(self):
        data = self.cleaned_data['itunes_agreement']
        data |= self.cleaned_data['library_sharing']
        data |= self.cleaned_data['device_backups']
        data |= self.cleaned_data['apple_music']
        data |= self.cleaned_data['update_check']
        data |= self.cleaned_data['music_store']
        data |= self.cleaned_data['shared_music']
        data |= self.cleaned_data['ipod_sync']
        version = self.cleaned_data['itunes_version']

        if data and version is None:
            raise ValidationError('You must provide a valid version number')
        return version

    def clean_login_version(self):
        data = self.cleaned_data['login_full_name']
        data |= self.cleaned_data['disable_password_change']
        data |= self.cleaned_data['hide_admin']
        data |= self.cleaned_data['shutdown']
        data |= self.cleaned_data['restart']
        data |= self.cleaned_data['sleep']
        data |= self.cleaned_data['console']
        data |= self.cleaned_data['shutdown_loggedin']
        data |= self.cleaned_data['restart_loggedin']
        data |= self.cleaned_data['power_loggedin']
        data |= self.cleaned_data['screen_lock']
        text = self.cleaned_data['text']
        host_info = self.cleaned_data['host_info']
        retries = self.cleaned_data['retries_till_hint']
        version = self.cleaned_data['login_version']

        if text not in [None, ''] or host_info not in [None, ''] or retries is not None:
            if version is None:
                raise ValidationError('You must provide a valid version number')
        if data and version is None:
            raise ValidationError('You must provide a valid version number')
        return version

    def clean_time_reset(self):
        attempts = self.cleaned_data['passcode_attempts']
        time = self.cleaned_data['time_reset']

        if attempts is None and time is not None:
            raise ValidationError('Must supply Maximum Failed Attempts')
        return time

    def clean_passcode_version(self):
        data = self.cleaned_data['passcode_simple']
        data |= self.cleaned_data['passcode_force']
        data |= self.cleaned_data['alpha']
        data |= self.cleaned_data['force_reset']
        attempts = self.cleaned_data['passcode_attempts']
        time = self.cleaned_data.get('time_reset', None)
        inactivity = self.cleaned_data['pin_inactivity']
        age = self.cleaned_data['pin_age']
        complexity = self.cleaned_data['complexity']
        length = self.cleaned_data['pin_min_length']
        history = self.cleaned_data['pin_history']
        grace = self.cleaned_data['grace_period']
        version = self.cleaned_data['passcode_version']

        if attempts is not None or time is not None or inactivity is not None or age is not None or \
                complexity is not None or length is not None or history is not None or grace is not None:
            if version is None:
                raise ValidationError('You must provide a valid version number')
        if data and version is None:
            raise ValidationError('You must provide a valid version number')
        return version

    def clean_password_version(self):
        password = self.cleaned_data['enable_protection']
        version = self.cleaned_data['password_version']

        if password and version is None:
            raise ValidationError('You must provide a valid version number')
        return version

    def clean_restrictions_version(self):
        data = self.cleaned_data['disable_assistant']
        data |= self.cleaned_data['ad_tracking']
        data |= self.cleaned_data['disable_camera']
        data |= self.cleaned_data['cloud_bookmarks']
        data |= self.cleaned_data['cloud_mail']
        data |= self.cleaned_data['cloud_cal']
        data |= self.cleaned_data['cloud_address']
        data |= self.cleaned_data['cloud_reminders']
        data |= self.cleaned_data['cloud_notes']
        data |= self.cleaned_data['cloud_doc_sync']
        data |= self.cleaned_data['cloud_keychain']
        data |= self.cleaned_data['cloud_docs_desk']
        data |= self.cleaned_data['caching']
        data |= self.cleaned_data['disable_touchid']
        data |= self.cleaned_data['itunes_file_share']
        data |= self.cleaned_data['disable_airdrop']
        data |= self.cleaned_data['disable_handoff']
        data |= self.cleaned_data['spotlight_internet']
        data |= self.cleaned_data['disable_screenshot']
        data |= self.cleaned_data['disable_autounlock']
        data |= self.cleaned_data['pass_autofill']
        data |= self.cleaned_data['pass_proximity']
        data |= self.cleaned_data['pass_share']
        version = self.cleaned_data['restrictions_version']

        if data and version is None:
            raise ValidationError('You must provide a valid version number')
        return version

    def clean_safari_version(self):
        data = self.cleaned_data['safe_downloads']
        data |= self.cleaned_data['multiple_pages']
        data |= self.cleaned_data['default_browser']
        data |= self.cleaned_data['autofill_address']
        data |= self.cleaned_data['autofill_forms']
        data |= self.cleaned_data['insecure_forms']
        data |= self.cleaned_data['private_browsing']
        data |= self.cleaned_data['disallow_notifications']
        data |= self.cleaned_data['tab_links']
        homepage = self.cleaned_data['homepage']
        new_window = self.cleaned_data['new_window']
        new_tab = self.cleaned_data['new_tab']
        tab_policy = self.cleaned_data['tab_policy']
        history_limit = self.cleaned_data['history_limit']
        path = self.cleaned_data['downloads_path']
        clear = self.cleaned_data['downloads_clear']
        cookies = self.cleaned_data['cookies']
        version = self.cleaned_data['safari_version']

        for value in [homepage, new_window, new_tab, tab_policy, history_limit, path, clear, cookies]:
            if value not in ['', None] and version is None:
                raise ValidationError('You must provide a valid version number')
        if data and version is None:
            raise ValidationError('You must provide a valid version number')
        return version

    def clean_screensaver_version(self):
        passwd = self.cleaned_data['screensaver_password']
        delay = self.cleaned_data['screensaver_delay']
        path = self.cleaned_data['screensaver_path']
        idle = self.cleaned_data['screensaver_idle']
        version = self.cleaned_data['screensaver_version']

        if passwd and delay is None:
            raise ValidationError('You must specify a value for Password Delay')
        if passwd or path not in [None, ''] or idle is not None:
            if version is None:
                raise ValidationError('You must provide a valid version number')

        return version

    def clean_setup_version(self):
        data = self.cleaned_data['skip_cloud']
        data |= self.cleaned_data['skip_siri']
        data |= self.cleaned_data['skip_privacy']
        data |= self.cleaned_data['skip_cloud_storage']
        data |= self.cleaned_data['skip_true_tone']
        data |= self.cleaned_data['skip_appearance']
        version = self.cleaned_data['setup_version']

        if data and version is None:
            raise ValidationError('You must provide a valid version number')
        return version

    def clean_software_version(self):
        data = self.cleaned_data['disable_beta']
        data |= self.cleaned_data['auto_check']
        data |= self.cleaned_data['auto_download']
        data |= self.cleaned_data['os_auto']
        data |= self.cleaned_data['app_auto']
        data |= self.cleaned_data['config_install']
        version = self.cleaned_data['software_version']

        if data and version is None:
            raise ValidationError('You must provide a valid version number')
        return version

    def clean_diagnostics_version(self):
        data = self.cleaned_data['diagnostics']
        version = self.cleaned_data['diagnostics_version']

        if data and version is None:
            raise ValidationError('You must provide a valid version number')
        return version

    def clean_policy_version(self):
        data = self.cleaned_data['developers_policy']
        data |= self.cleaned_data['policy_enable']
        data |= self.cleaned_data['disable_context']
        version = self.cleaned_data['policy_version']

        if data and version is None:
            raise ValidationError('You must provide a valid version number')
        return version

    def clean_preferences_version(self):
        enabled = self.cleaned_data.get('enabled_panes', [])
        disabled = self.cleaned_data.get('disabled_panes', [])
        hidden = self.cleaned_data.get('hidden_panes', [])
        data = self.cleaned_data['lockmessage_ui']
        data |= self.cleaned_data['password_change']
        version = self.cleaned_data['preferences_version']

        if len(enabled) > 0 or len(disabled) > 0 or len(hidden) > 0 or data:
            if version is None:
                raise ValidationError('You must provide a valid version number')
        for pane in enabled:
            if pane in disabled:
                raise ValidationError('Preference panes cannot be enabled and disabled at the same time')
        return version

    def clean_time_machine_version(self):
        data = self.cleaned_data['auto_backup']
        data |= self.cleaned_data['backup_volumes']
        data |= self.cleaned_data['backup_sys']
        data |= self.cleaned_data['mobile_backups']
        size = self.cleaned_data['backup_size']
        url = self.cleaned_data['backup_url']
        version = self.cleaned_data['time_machine_version']

        if size is not None or url not in [None, ''] or data:
            if version is None:
                raise ValidationError('You must provide a valid version number')
        return version


class AssignmentForm(forms.Form):
    options = forms.MultipleChoiceField(choices=[], widget=forms.CheckboxSelectMultiple, label="Select one or more",
                                        required=False)

    def __init__(self, *args, **kwargs):
        option_type = kwargs.pop('type')
        option_data = kwargs.pop('options')
        self.helper = FormHelper()
        self.helper.form_class = "form-horizontal col-md-6"
        self.helper.layout = Layout(
            Fieldset("Select {}".format(option_type), HTML('<div class="col-md-12" style="padding-bottom: 3%">'),
                     'options', HTML('</div><br><br>')),
            FormActions(Submit('save', 'Assign'))
        )
        super(AssignmentForm, self).__init__(*args, **kwargs)

        if option_type == 'devices':
            items = [(laptop, laptop.name) for laptop in option_data]
            self.fields['options'].choices = items
        elif option_type == 'apps':
            items = [(app.pk, app.name) for app in option_data]
            self.fields['options'].choices = items
        elif option_type == 'profiles':
            items = [(profile.pk, str(profile)) for profile in option_data]
            self.fields['options'].choices = items


class ProfileRemovalForm(forms.Form):
    options = forms.ChoiceField(choices=[('auto', 'I would like to have the profiles removed automatically'),
                                         ('manual', 'I have chosen to remove the profiles manually. I affirm that this '
                                                    'profile is no longer installed on any of LNL\'s devices.')],
                                widget=forms.RadioSelect, label="Before continuing, please select one of the following")

    def __init__(self, *args, **kwargs):
        mode = kwargs.pop('mode')
        self.helper = FormHelper()
        self.helper.form_class = "form-horizontal col-md-6"
        warning = '<p style="font-weight: bold"><span style="color: red">WARNING:</span> This profile has been ' \
                  'applied to one or more devices. Before removing this profile from the MDM, you must ensure that ' \
                  'all occurrences of this profile have been removed.</p>'
        directions = '<p>There are two ways to remove this profile from your managed devices:</p><ul><li><strong>' \
                     '[Recommended]</strong> The first option is to have the MDM remove the profiles automatically. ' \
                     'The profile will be removed from each device the next time the device checks in. If you are ' \
                     'currently using a managed device, you can sign out and sign back in to force a checkin.</li>' \
                     '<li>The second option is to remove it from each device manually. Follow the directions in the ' \
                     'MDM User Guide for more information. If the profile is password protected, ' \
                     '<a href="' + reverse("mdm:password") + '">click here</a>.</li></ul>'
        if mode == 'disassociate':
            warning = '<p style="font-weight: bold"><span style="color: red">WARNING:</span> This profile may ' \
                      'still be installed on the device. Unlinking this profile without removing it from the device ' \
                      'first could cause the profile to remain on the device indefinitely. Read the following ' \
                      'carefully before continuing.</p>'
            directions = '<p>There are two ways to remove this profile from the device:</p><ul><li>The first option ' \
                         'is to have the MDM remove the profile automatically the next time the device checks in. If ' \
                         'you are currently using the device and would like these changes deployed immediately, ' \
                         'you\'ll need to sign out then sign back in.</li><li>The second option is to remove it ' \
                         'manually. Follow the directions in the MDM User Guide for more information. If the profile ' \
                         'is password protected, <a href="' + reverse("mdm:password") + '">click here</a>.</li></ul>'
        self.helper.layout = Layout(
            Fieldset(
                'Remove Profile',
                Div(
                    HTML(warning),
                    HTML(directions),
                    HTML('<div class="col-md-12">'),
                    'options',
                    HTML('</div><br><br>'),
                    FormActions(
                        Submit('save', 'Continue')
                    )
                )
            )
        )
        super(ProfileRemovalForm, self).__init__(*args, **kwargs)

        if mode == 'disassociate':
            self.fields['options'].choices = [('auto', 'I would like the profile to removed at the next check-in'),
                                              ('manual', 'The profile has already been removed manually')]


class NewAppForm(FieldAccessForm):
    def __init__(self, *args, **kwargs):
        title = kwargs.pop('title')
        self.helper = FormHelper()
        self.helper.form_class = "form-horizontal col-md-6"
        self.helper.layout = Layout(
            Fieldset(title, 'name', 'version', 'developer', 'description', 'developer_website'),
            FormActions(Submit('save', "Submit"))
        )
        super(NewAppForm, self).__init__(*args, **kwargs)

        self.fields['name'].label = "Application Name"
        self.fields['developer_website'].label = "Website"
        self.fields['developer_website'].help_text = "Please enter a fully formed URL (i.e. https://lnl.wpi.edu)"

    class Meta:
        model = MacOSApp
        fields = ['name', 'developer', 'version', 'description', 'developer_website']

    class FieldAccess:
        def __init__(self):
            pass

        can_request = FieldAccessLevel(
            lambda user, instance: user.has_perm('devices.add_apps', instance),
            enable=('name', 'developer', 'version', 'developer_website'),
            exclude=('description',)
        )

        can_edit = FieldAccessLevel(
            lambda user, instance: user.has_perm('devices.manage_apps', instance),
            enable=('name', 'developer', 'version', 'description', 'developer_website')
        )


class UpdateAppForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        self.helper = FormHelper()
        self.helper.form_class = "form-horizontal col-md-6"
        self.helper.layout = Layout(
            Fieldset(
                'Application Info',
                Div(
                    'name',
                    'identifier',
                    'developer',
                    'version',
                    'description',
                    'developer_website',
                    'requires_license',
                    css_class="col-md-12"
                )
            ),
            FormActions(
                Submit("save", "Delete", css_class="btn-danger"),
                Submit("save", "Merge"),
                Submit("save", "Save Changes")
            )
        )
        super(UpdateAppForm, self).__init__(*args, **kwargs)

        self.fields['identifier'].help_text = "If the application is available in homebrew, it can be found " \
                                              "<a href='" + reverse("mdm:app-list") + "' target='_blank'>here</a>. " \
                                              "Enter the respective identifier above (if applicable)."
        self.fields['identifier'].label = "Homebrew Identifier"
        self.fields['developer_website'].label = "Website"
        self.fields['developer_website'].help_text = "Please enter a fully formed URL (i.e. https://lnl.wpi.edu)"

    class Meta:
        model = MacOSApp
        fields = ['name', 'identifier', 'developer', 'version', 'description', 'developer_website', 'requires_license']


class AppMergeForm(forms.Form):
    options = forms.ChoiceField(label="Select the application to merge this into", choices=[])

    def __init__(self, *args, **kwargs):
        pk = kwargs.pop('pk')
        app_name = MacOSApp.objects.get(pk=pk).name
        self.helper = FormHelper()
        self.helper.form_class = "form-horizontal col-md-6"
        self.helper.layout = Layout(
            Fieldset('Merge ' + app_name + ' into...', 'options'),
            FormActions(Submit('save', 'Merge'))
        )
        super(AppMergeForm, self).__init__(*args, **kwargs)

        items = [(app.pk, app.name) for app in MacOSApp.objects.exclude(pk=pk, merged_into__isnull=False).all()]
        self.fields['options'].choices = items


class UninstallAppForm(forms.Form):
    def __init__(self, *args, **kwargs):
        mode = kwargs.pop('mode')
        self.helper = FormHelper()
        self.helper.form_class = "form-horizontal col-md-6"
        warning = '<p style="font-weight: bold"><span style="color: red">WARNING:</span> Our records indicate that ' \
                  'this app might still be installed on one or more devices. Note that if this application is still ' \
                  'installed, it will reappear here the next time that device checks in. Managed applications can be ' \
                  'uninstalled using the Managed Software Center or Homebrew (if applicable).</li></ul>'
        if mode == 'disassociate':
            warning = '<p>This app may still be installed on the device. Note that if it is, it could reappear here ' \
                      'the next time the device checks in. Would you like to continue anyways?</p>'
        self.helper.layout = Layout(
            Fieldset(
                'Remove Application',
                Div(
                    HTML(warning),
                    HTML('<br><br>'),
                    FormActions(
                        Submit('save', 'Continue')
                    )
                )
            )
        )
        super(UninstallAppForm, self).__init__(*args, **kwargs)
