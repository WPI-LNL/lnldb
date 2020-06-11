from crispy_forms.bootstrap import FormActions
from crispy_forms.layout import Submit, Layout, Fieldset, HTML, Hidden, Field, Div
from crispy_forms.helper import FormHelper
from django import forms
from django.core.exceptions import ValidationError
from django.shortcuts import reverse
from .models import Laptop


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
                         'agree to all of the relevant terms.</li><li>I agree to take full responsibility for any '
                         'loss or damage that may result from improper use of the MDM, or otherwise, and I '
                         'understand that such damage may be permanent.</li><li>I understand that I may not copy, '
                         'redistribute, reproduce, transfer, reverse-engineer, decompile, disassemble, modify, or '
                         'create derivative works of the MDM software unless I have been given explicit consent by '
                         'the LNL Webmaster.</li><li>By clicking "Agree", I accept the full MDM Terms of Use as well '
                         'as any and all additional terms that may be provided with the software.</li>'
                         '</ul><br>'),
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
    password_rotation = forms.BooleanField(required=True, label="Used the default option or am willing to forgo the "
                                                                "risk.")

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
                    HTML('<li>By default, when removing the MDM client, it will disable the password rotation feature.'
                         ' If instead you opted to keep using this feature outside of a managed configuration, please '
                         'note that even after you remove this device from the MDM, the device will continue to '
                         'communicate with the server using the same API Key. As a result, any future attempts to '
                         're-enroll this device may fail or have unintended consequences. By checking the box below, '
                         'you acknowledge that you have read and understand this disclosure.</li>'),
                    'password_rotation',
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
