from django import forms


class DismissBannerForm(forms.Form):
    banner_name = forms.CharField()
