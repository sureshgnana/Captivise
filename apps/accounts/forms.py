from django import forms
from django.contrib.auth import password_validation, get_user_model
from django.contrib.auth.forms import (
    AuthenticationForm,
    PasswordResetForm as DjangoPasswordResetForm,
    UserCreationForm as DjangoUserCreationForm,
)

from adwords.adapter import Adapter
from adwords.exceptions import NonManagerAccountSelected, UserNotLinkedError
from django.forms.widgets import PasswordInput, TextInput, Select

import google_auth_httplib2
from googleapiclient import discovery
from googleapiclient import errors
from googleapiclient import http
from googleapiclient import model
from shopping.content import _constants
from shopping.content import auth

import six.moves.urllib.parse

from django.conf import settings

import requests
from requests.structures import CaseInsensitiveDict
import logging

UserModel = get_user_model()


class LoginForm(AuthenticationForm):
    error_messages = {
        'invalid_login': 'Incorrect Login Details',
        'inactive': 'This account is inactive.',
    }
    username = forms.CharField(widget=TextInput(attrs={'class': 'form-control',}))
    password = forms.CharField(widget=PasswordInput(attrs={'class': 'form-control'}))


class PasswordResetForm(DjangoPasswordResetForm):
    email = forms.EmailField(label='Your Email Address', max_length=254, widget=PasswordInput(attrs={'class': 'form-control',}))


class SetPasswordForm(forms.Form):
    new_password = forms.CharField(
        label='New password',
        widget=forms.PasswordInput,
        strip=False,
        help_text=password_validation.password_validators_help_text_html(),
    )    

    def __init__(self, user, *args, **kwargs):
        self.user = user
        super(SetPasswordForm, self).__init__(*args, **kwargs)

    def save(self, commit=True):
        password = self.cleaned_data['new_password']
        self.user.set_password(password)
        if commit:
            self.user.save()
        return self.user


class UserCreationForm(DjangoUserCreationForm):

    first_name = forms.CharField(widget=TextInput(attrs={'class': 'form-control',}))
    last_name = forms.CharField(widget=TextInput(attrs={'class': 'form-control',}))
    email = forms.EmailField(widget=TextInput(attrs={'class': 'form-control',}))
    phone_number = forms.CharField(widget=TextInput(attrs={'class': 'form-control',}))
    company_name = forms.CharField(widget=TextInput(attrs={'class': 'form-control',}))
    password1 = forms.CharField(
        widget=PasswordInput(attrs={'class': 'form-control'}),
        label='Password',
    )
    password2 = forms.CharField(
        widget=PasswordInput(attrs={'class': 'form-control'}),
        label='Password confirmation',
    )

    class Meta:
        model = UserModel
        fields = ('first_name', 'last_name', 'email', 'phone_number', 'company_name')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.fields['first_name'].required = True
        self.fields['last_name'].required = True
        


class EditUserForm(forms.ModelForm):
    new_password = forms.CharField(
        label='Password',
        widget=forms.PasswordInput(attrs={'class': 'form-control'}),
        strip=False,
        help_text=password_validation.password_validators_help_text_html(),
    )
    email = forms.EmailField(widget=TextInput(attrs={'class': 'form-control',}))

    class Meta:
        model = UserModel
        fields = ('email', )

    def clean_new_password(self):
        password = self.cleaned_data.get('new_password')
        password_validation.validate_password(password, self.instance)
        return password

    def save(self, **kwargs):
        password = self.cleaned_data['new_password']
        if password:
            self.instance.set_password(password)
        return super().save(**kwargs)


class AdwordsClientCustomerForm(forms.Form):
    client_customer = forms.ChoiceField(choices=(), widget=Select(attrs={'class': 'form-control',}))

    def __init__(self, refresh_token=None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['client_customer'].label = ""
        self.setup_customer_choices(refresh_token)

    def setup_customer_choices(self, refresh_token):
        try:
            try:
                # Try to get manager account
                customers = Adapter.get_customers(refresh_token)
                choices = [
                    (customer.customerId, customer.name)
                    for customer in customers
                    if not customer.canManageClients

                ]
            except:
                # In the event of failure, get normal
                customer = Adapter.get_customer(refresh_token)
                choices = [
                    (customer.customerId, customer.descriptiveName)
                ]
        except:
            raise NonManagerAccountSelected


        # Ignore manager accounts, as reports can't be run against them.
        # https://developers.google.com/adwords/api/docs/common-errors#ReportDefinitionError.CUSTOMER_SERVING_TYPE_REPORT_MISMATCH  # noqa
        
        self.fields['client_customer'].choices = choices


class MerchantForm(forms.Form):
    merchant_id = forms.ChoiceField(choices=(), widget=Select(attrs={'class': 'form-control',}))
    merchant_name = forms.CharField(widget=forms.HiddenInput())

    def __init__(self, merchant_access_token=None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['merchant_id'].label = ""
        self.setup_customer_choices(merchant_access_token)

    def setup_customer_choices(self, merchant_access_token):
        choices = []
        try:
            # Try to get manager account
           
            url = "https://shoppingcontent.googleapis.com/content/v2/accounts/authinfo?key="+settings.ADWORDS_SECRET_KEY
            resp = self.get_rest_api(url, merchant_access_token)
            if resp:                
                result = resp.json()
                choices = []
                if 'accountIdentifiers' in result:
                    for merchant in result['accountIdentifiers']:
                        merchant_id = merchant['merchantId']
                        merchant_name = merchant_id
                        url = "https://shoppingcontent.googleapis.com/content/v2/{merchant_id}/accounts/{merchant_id}?key={secret_key}".format(merchant_id=merchant_id, secret_key=settings.ADWORDS_SECRET_KEY)
                        mresp = self.get_rest_api(url, merchant_access_token)
                        if mresp:
                            mresult = mresp.json()
                            merchant_name = mresult['name']
                        choices.append((merchant_id, merchant_name))

        except:
            choices = []



        # Ignore manager accounts, as reports can't be run against them.
        # https://developers.google.com/adwords/api/docs/common-errors#ReportDefinitionError.CUSTOMER_SERVING_TYPE_REPORT_MISMATCH  # noqa
        
        self.fields['merchant_id'].choices = choices
    
    def get_rest_api(self, url, access_token):        
        headers = CaseInsensitiveDict()
        headers["Authorization"] = "Bearer "+access_token
        headers["Accept"] = "application/json"
        resp = requests.get(url, headers=headers)
        return resp


