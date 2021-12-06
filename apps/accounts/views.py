from django.conf import settings
from django.contrib.auth import login, update_session_auth_hash
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.http import HttpResponseRedirect, FileResponse
from django.urls import reverse_lazy, reverse
from django.views.generic import CreateView, FormView, UpdateView, View, TemplateView

from googleads import oauth2
from oauth2client import client

from adwords.exceptions import NonManagerAccountSelected
from website.utils import get_adwords_client
from website.views import ActiveMenuItemMixin

from .forms import EditUserForm, LoginForm, AdwordsClientCustomerForm, UserCreationForm, MerchantForm

from quotes.models import StripeResponse

from billing.models import Payment

from adwords.adapter import Adapter
import decimal

from django.db.models import Sum
from .tables import (
    PaymentTable,
)
import io
from django.http import FileResponse
from reportlab.pdfgen import canvas
import os
from reports.models import (
    Campaign
)
from constance import config
import logging

class PaidAccountRequiredMixin(UserPassesTestMixin):

    def test_func(self):
        return self.request.user.is_authenticated and self.request.user.has_payment_details

    def handle_no_permission(self):
        if self.request.user.is_authenticated:
            return HttpResponseRedirect(reverse('quoting_adwords_preamble'))
        else:
            return HttpResponseRedirect(reverse('accounts_login'))


class UnpaidAccountRequiredMixin(UserPassesTestMixin):

    def test_func(self):
        return self.request.user.is_authenticated and not self.request.user.has_payment_details

    def handle_no_permission(self):
        if self.request.user.is_authenticated:
            return HttpResponseRedirect(reverse('reports_dashboard'))
        else:
            return HttpResponseRedirect(reverse('accounts_login'))


class LoginView(FormView):
    template_name = 'accounts/login.html'
    form_class = LoginForm

    def form_valid(self, form):
        login(self.request, form.get_user())
        return super().form_valid(form)

    def get_success_url(self):
        next_url = self.request.GET.get('next', '')
        # Only accept internal links.
        if next_url.startswith('/') and not next_url.startswith('//'):
            return next_url

        return reverse_lazy('reports_dashboard')


class RegisterView(CreateView):
    template_name = 'accounts/register.html'
    form_class = UserCreationForm

    def form_valid(self, form):
        response = super().form_valid(form)
        login(self.request, self.object)
        return response

    def get_success_url(self):
        return reverse_lazy('quoting_adwords_preamble')


class AccountView(ActiveMenuItemMixin, LoginRequiredMixin, PaidAccountRequiredMixin, UpdateView):
    template_name = 'accounts/accounts.html'
    form_class = EditUserForm

    def get_active_menu(self):
        return {
            'accounts': True,
        }

    def get_adwords_account_details(self, user):
        adwords_client = get_adwords_client(user.refresh_token, user.client_customer_id)

        customers = adwords_client.GetService('CustomerService').getCustomers()

        for customer in customers:
            if customer.customerId == int(user.client_customer_id):
                return customer

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        context.update({
            'has_adwords_account': self.request.user.has_adwords_account,
            'has_payment_details': self.request.user.has_payment_details,
        })
        logging.getLogger("error_logger").error('test')
        
        if self.request.user.has_adwords_account:
            shop_campaign = Campaign.objects.filter(
                owner=self.request.user,
                advertising_channel_type='Shopping',
                client_customer_id=self.request.user.client_customer_id
                ) \
                .first()

            if shop_campaign:
                context.update({
                'has_shopping_campaign': True,
                'merchant_id': self.request.user.merchant_id,
                'merchant_name': self.request.user.merchant_name,
                })

            # TODO Should this be cached somehow?
            context.update({
                'adwords_account': self.get_adwords_account_details(self.request.user),
                'config': config,
            })

        if self.request.user.has_payment_details:
            context.update(self.request.user.get_payment_details_context())

        return context

    def get_object(self, queryset=None):
        return self.request.user

    def form_valid(self, form):
        self.object = form.save()
        update_session_auth_hash(self.request, self.object)
        return self.form_invalid(form)


class RemoveAdwordsAccountView(LoginRequiredMixin, PaidAccountRequiredMixin, View):

    def post(self, request, *args, **kwargs):
        request.user.reset_adwords_fields()

        return HttpResponseRedirect(reverse('accounts_account'))


class BaseAdwordsAccountView(View):

    def get_adwords_client(self, request):
        client_id = settings.ADWORDS_CLIENT_ID
        client_secret = settings.ADWORDS_SECRET_KEY
        redirect_uri = request.build_absolute_uri(reverse('accounts_oauth_callback'))

        return client.OAuth2WebServerFlow(
            client_id=client_id,
            client_secret=client_secret,
            scope=oauth2.GetAPIScope('adwords'),
            user_agent='Test',
            prompt='consent',
            redirect_uri=redirect_uri,
        )


class AddAdwordsAccountView(BaseAdwordsAccountView):

    def get(self, request, *args, **kwargs):
        flow = self.get_adwords_client(request)

        auth_uri = flow.step1_get_authorize_url()

        return HttpResponseRedirect(auth_uri)


class AddAdwordsAccountCallbackView(BaseAdwordsAccountView):

    def get(self, request, *args, **kwargs):
        flow = self.get_adwords_client(request)

        auth_code = request.GET.get('code', None)

        if auth_code is None:
            return HttpResponseRedirect(reverse('accounts_account'))

        credentials = flow.step2_exchange(auth_code)

        refresh_token = credentials.refresh_token

        request.session['refresh_token'] = refresh_token

        return HttpResponseRedirect(reverse('accounts_oauth_customers'))


class AddAdwordsAccountClientCustomerView(LoginRequiredMixin, FormView):
    template_name = 'accounts/account_add_client_customers.html'
    form_class = AdwordsClientCustomerForm

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()

        kwargs.update({
            'refresh_token': self.request.session['refresh_token'],
        })

        return kwargs

    def get_form(self, form_class=None):
        if form_class is None:
            form_class = self.get_form_class()

        try:
            form = form_class(**self.get_form_kwargs())
        except NonManagerAccountSelected:
            return None

        return form

    def get_success_url(self):        
        if self.request.user.has_payment_details:            
            return reverse('accounts_account')
        else:            
            return reverse('quoting_compatibility_results')

    def form_valid(self, form):        
        self.request.user.set_adwords_fields(
            refresh_token=self.request.session['refresh_token'],
            client_customer_id=form.cleaned_data['client_customer'],
        )
        return super().form_valid(form)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        if context['form'] is None:
            context['non_manager_account_selected'] = True
        return context


class PaymentListView(
    ActiveMenuItemMixin,
    LoginRequiredMixin,
    PaidAccountRequiredMixin,
    TemplateView):
    template_name = 'accounts/payment_list.html'
    
    def get_active_menu(self):
        filter_by = self.request.GET.get('filter', 'all')
        return {
            'accounts_payment_list': True,
        }

    def get_context_data(self, *args, **kwargs):
        context = super().get_context_data(*args, **kwargs)

        if not self.request.user.has_adwords_account:
            return context

        context['has_adwords_account'] = True

        order_by = self.request.GET.get('sort', '-created_at')
        try:
            page = int(self.request.GET.get('page', 1))
        except ValueError:
            # raise a 400
            raise SuspiciousOperation('Bad request:  GET parameter `page` is not an integer')

        total_amount = 0
        total = Payment.objects.filter(user=self.request.user).aggregate(Sum('amount'))
        if 'amount__sum' in total and total['amount__sum'] is not None:
            total_amount = decimal.Decimal(total['amount__sum']/100.0).quantize(decimal.Decimal('0.01'))

        result = Payment.objects.filter(user=self.request.user)
        table = PaymentTable(result, order_by=order_by)
        table.paginate(page=page, per_page=20)
        context.update({
            'payment_list': table,
            'total_amount': total_amount             
        })

        return context

class DownloadInvoiceView(TemplateView):

    def get(self, request, *args, **kwargs):
        payment_id = int(self.kwargs['payment_id'])
        try: 
            result = Payment.objects.get(pk=payment_id, user=self.request.user)
            
            amount = decimal.Decimal(result.amount/100.0).quantize(decimal.Decimal('0.01'))
            logo_path = os.path.join(settings.MEDIA_ROOT, 'img', "logo-pdf.png")
                

            # Create a file-like buffer to receive PDF data.
            buffer = io.BytesIO()

            # Create the PDF object, using the buffer as its "file."
            c = canvas.Canvas(buffer,pagesize=(200,250),bottomup=0)
            c.setLineWidth(.5)

            # Logo Section
            c.translate(10,40)
            c.scale(1,-1)
            c.drawImage(logo_path,10,10,width=50,height=10)

            c.scale(1,-1)
            # Again Setting the origin back to (0,0) of top-left
            c.translate(-10,-40)
            # Setting the font for Name title of company
            c.setFont("Helvetica-Bold",5)
            # Inserting the name of the company
            #c.drawCentredString(125,20,"Captivise")
            # For under lining the title
            #c.line(70,22,180,22)
            # Changing the font size for Specifying Address
            c.setFont("Helvetica-Bold",5)

            # Line Seprating the page header from the body
            c.line(2,35,195,35)
            # Document Information
            # Changing the font for Document title
            c.setFont("Times-Bold",7)
            c.drawString(20,50,"Captivise")
            # This Block Consist of Costumer Details
            #c.roundRect(15,63,170,40,10,stroke=1,fill=0)
            c.setFont("Helvetica",5)
            c.drawString(20,60,"")
            c.drawString(20,70,"")
            c.drawString(20,80,"")
            c.drawString(20,90,"Lancaster UK")
            c.drawString(20,100,"info@captivise.com")
            c.drawString(20,110,"www.captivise.com")
            
            c.setFont("Helvetica",5)
            c.drawRightString(180,60,"Invoice Receipt")
            c.setFont("Helvetica-Bold",5)
            c.drawRightString(180,70, " ".join(("Invoice# ",str(result.id))))
            c.setFont("Helvetica",5)
            c.drawRightString(180,80,"Invoice Date")
            c.setFont("Helvetica-Bold",5)
            c.drawRightString(180,90, result.created_at.strftime("%d/%m/%Y"))
            # This Block Consist of Item Description
            c.setFont("Helvetica-Bold",5)
            c.drawString(20,130,"Billed To")
            c.setFont("Helvetica",5)
            if result.customer_name:
                c.drawString(20,140, result.customer_name)
            if result.customer_email:
                c.drawString(20,150, result.customer_email)
            
            c.setFont("Helvetica-Bold",5)
            c.drawString(20,170,"Description")
            c.drawRightString(180,170,"Amount")
            c.line(15,180,185,180)
            c.setFont("Helvetica",5)
            c.drawString(20,190,"Captivise Payment")
            c.drawRightString(180,190, " ".join((str(amount) ,"", config.CURRENCY_CODE)))
            c.setFont("Helvetica-Bold",5)
            c.drawString(100,210,"Subtotal")
            c.setFont("Helvetica",5)
            c.drawRightString(180,210, " ".join((str(amount), "", config.CURRENCY_CODE)))
            c.drawString(100,220,"VAT (0.0%) (+)")
            c.drawRightString(180,220," ".join(('0.00', "", config.CURRENCY_CODE)))
            c.setFont("Helvetica-Bold",5)
            c.line(70,225,180,225)
            c.drawString(100,235,"Total")
            c.drawRightString(180,235," ".join((str(amount), " ", config.CURRENCY_CODE)))
            # Declaration and Signature
            c.line(15,240,185,240)

            
            # Close the PDF object cleanly, and we're done.
            c.showPage()
            c.save()

            # FileResponse sets the Content-Disposition header so that browsers
            # present the option to save the file.
            buffer.seek(0)
            return FileResponse(buffer, as_attachment=True, filename='invoice.pdf')
        except Exception:

            return HttpResponseRedirect(reverse('accounts_payment_list'))


class RemoveMerchantAccountView(LoginRequiredMixin, PaidAccountRequiredMixin, View):

    def post(self, request, *args, **kwargs):
        request.user.reset_merchant_fields()

        return HttpResponseRedirect(reverse('accounts_account'))


class BaseMerchantAccountView(View):

    def get_adwords_client(self, request):
        client_id = settings.ADWORDS_CLIENT_ID
        client_secret = settings.ADWORDS_SECRET_KEY
        redirect_uri = request.build_absolute_uri(reverse('accounts_merchant_oauth_callback'))

        return client.OAuth2WebServerFlow(
            client_id=client_id,
            client_secret=client_secret,
            scope='https://www.googleapis.com/auth/content',
            user_agent='Test',
            prompt='consent',
            access_type='offline',
            redirect_uri=redirect_uri,
        )


class AddMerchantAccountView(BaseMerchantAccountView):

    def get(self, request, *args, **kwargs):
        flow = self.get_adwords_client(request)

        auth_uri = flow.step1_get_authorize_url()

        return HttpResponseRedirect(auth_uri)


class AddMerchantAccountCallbackView(BaseMerchantAccountView):

    def get(self, request, *args, **kwargs):
        flow = self.get_adwords_client(request)

        auth_code = request.GET.get('code', None)

        credentials = flow.step2_exchange(auth_code)

        refresh_token = credentials.refresh_token
        access_token = credentials.access_token

        request.session['merchant_access_token'] = access_token
        request.session['merchant_refresh_token'] = refresh_token

        return HttpResponseRedirect(reverse('accounts_merchant_oauth_customers'))


class AddMerchantAccountClientCustomerView(LoginRequiredMixin, FormView):
    template_name = 'accounts/account_add_merchant.html'
    form_class = MerchantForm

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()

        kwargs.update({
            'merchant_access_token': self.request.session['merchant_access_token'],
        })

        return kwargs

    def get_form(self, form_class=None):
        if form_class is None:
            form_class = self.get_form_class()

        try:
            form = form_class(**self.get_form_kwargs())
        except NonManagerAccountSelected:
            return None

        return form

    def get_success_url(self):        
        if self.request.user.has_payment_details:            
            return reverse('accounts_account')
        else:            
            return reverse('quoting_compatibility_results')

    def form_valid(self, form):        
        self.request.user.set_merchant_fields(
            merchant_refresh_token=self.request.session['merchant_refresh_token'],
            merchant_access_token=self.request.session['merchant_access_token'],
            merchant_id=form.cleaned_data['merchant_id'],
            merchant_name=form.cleaned_data['merchant_name'],
        )
        return super().form_valid(form)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        if context['form'] is None:
            context['non_manager_account_selected'] = True
        return context
