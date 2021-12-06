from django.conf.urls import url
from django.contrib.auth import logout
from django.contrib.auth.views import (
PasswordResetView,
PasswordResetConfirmView,
PasswordResetDoneView,
PasswordResetCompleteView,
PasswordChangeView,
PasswordChangeDoneView,
LogoutView,
)


from .forms import PasswordResetForm, SetPasswordForm
from .views import (
    AccountView,
    LoginView,
    AddAdwordsAccountView,
    AddAdwordsAccountCallbackView,
    RemoveAdwordsAccountView,
    AddAdwordsAccountClientCustomerView,
    RegisterView,
    PaymentListView,
    DownloadInvoiceView,
    AddMerchantAccountView,
    AddMerchantAccountCallbackView,
    AddMerchantAccountClientCustomerView,
    RemoveMerchantAccountView,
)
from . import views

urlpatterns = [
    url(r'^login/$', LoginView.as_view(), name='accounts_login'),
    url(
        r'^logout/$',
        LogoutView.as_view(),
        name='accounts_logout',
    ),
    url(r'^register/$', RegisterView.as_view(), name='accounts_register'),
    url(
        r'^password/reset/$',
        PasswordResetView.as_view(template_name='accounts/password_reset.html'),
        {
            'template_name': 'accounts/password_reset.html',
            'email_template_name': 'accounts/email/password_reset.html',
            'post_reset_redirect': 'accounts_password_reset_done',
            'password_reset_form': PasswordResetForm,
        },
        name='accounts_password_reset',
    ),
    url(
        r'^password/reset/done/$',
        PasswordResetDoneView.as_view(template_name='accounts/password_reset_done.html'),
        {
            'template_name': 'accounts/password_reset_done.html',
        },
        name='password_reset_done',
    ),
    url(
        r'^password/reset/confirm/(?P<uidb64>[0-9A-Za-z_\-]+)/'
        r'(?P<token>[0-9A-Za-z]{1,13}-[0-9A-Za-z]{1,20})/$',
        PasswordResetConfirmView.as_view(template_name='accounts/password_reset_confirm.html'),
        {
            'template_name': 'accounts/password_reset_confirm.html',
            'post_reset_redirect': 'accounts_password_reset_complete',
            'set_password_form': SetPasswordForm,
        },
        name='password_reset_confirm',
    ),
    url(
        r'^password/reset/complete/$',
        PasswordResetCompleteView.as_view(template_name='accounts/password_reset_complete.html'),
        {
            'template_name': 'accounts/password_reset_complete.html',
        },
        name='password_reset_complete',
    ),
    url(r'^account/$', AccountView.as_view(), name='accounts_account'),
    url(
        r'^account/oauth/redirect/$',
        AddAdwordsAccountView.as_view(),
        name='accounts_oauth_redirect',
    ),
    url(
        r'^account/oauth/callback/$',
        AddAdwordsAccountCallbackView.as_view(),
        name='accounts_oauth_callback',
    ),
    url(
        r'^account/oauth/customers/$',
        AddAdwordsAccountClientCustomerView.as_view(),
        name='accounts_oauth_customers',
    ),
    url(
        r'^account/oauth/remove/$',
        RemoveAdwordsAccountView.as_view(),
        name='accounts_oauth_remove',
    ),
    url(
        r'^payments/$',
        PaymentListView.as_view(),
        name='accounts_payment_list',
    ),
    url(
        r'^download_invoice/(?P<payment_id>\d+)/$',
        DownloadInvoiceView.as_view(),
        name='accounts_download_invoice',
    ),
    url(
        r'^account/merchant/oauth/redirect/$',
        AddMerchantAccountView.as_view(),
        name='accounts_merchant_oauth_redirect',
    ),
    url(
        r'^account/merchant/oauth/callback/$',
        AddMerchantAccountCallbackView.as_view(),
        name='accounts_merchant_oauth_callback',
    ),
    url(
        r'^account/merchant/oauth/customers/$',
        AddMerchantAccountClientCustomerView.as_view(),
        name='accounts_merchant_oauth_customers',
    ),
    url(
        r'^account/merchant/oauth/remove/$',
        RemoveMerchantAccountView.as_view(),
        name='accounts_merchant_oauth_remove',
    ),
]
