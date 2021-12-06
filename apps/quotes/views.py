from django.http import Http404, HttpResponseRedirect
from django.urls import reverse, reverse_lazy
from django.utils.functional import cached_property
from django.views.generic import CreateView, DetailView, FormView, TemplateView

from ecom6.views import PaymentDetailBaseView
from django.shortcuts import render
from accounts.views import UnpaidAccountRequiredMixin
from adwords.adapter import Adapter
from django.conf import settings
from .forms import TermsAndConditionsForm, QuoteEstimateForm
from .models import (
    CompatibilityCheckECommerceTracking,
    CompatibilityCheckOnPagePhoneCallTracking,
    CompatibilityCheckWebsiteTracking,
    Quote,
    StripeResponse
)
from accounts.models import User
import stripe
import json
import getpass
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from website.utils import cms_page_content
from django.contrib.auth.mixins import LoginRequiredMixin
from accounts.views import PaidAccountRequiredMixin
from website.views import ActiveMenuItemMixin
from django.core.exceptions import SuspiciousOperation
from website.models import CmsContent
from constance import config

class AdwordsPreambleView(UnpaidAccountRequiredMixin, FormView):
    template_name = 'quotes/adwords_preamble.html'
    form_class = TermsAndConditionsForm
    success_url = reverse_lazy('accounts_oauth_redirect')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        cms_pages = CmsContent.objects.filter(slug__in=[
                    'welcome_page_block1',
                    'welcome_page_block2',
                    'welcome_page_block3',
                    'welcome_page_block4',
                    'welcome_page_block5',
                    'welcome_page_block6'])
        page_content = {}
        n = 1
        for cms_page in cms_pages:
            page_content['block_'+str(n)] = cms_page
            n +=1

        context['page_content'] = page_content
        return context


class QuoteEstimateView(UnpaidAccountRequiredMixin, CreateView):
    template_name = 'quotes/quote_estimate_form.html'
    form_class = QuoteEstimateForm

    class Meta:
        model = Quote

    def get_success_url(self):
        return reverse('quoting_view_quote')

    def form_valid(self, form):
        self.object = form.save(commit=False)
        self.object.set_user_details(self.request.user)
        self.request.session['quote_pk'] = self.object.pk
        return HttpResponseRedirect(self.get_success_url())


class CompatibilityResultsView(UnpaidAccountRequiredMixin, TemplateView):
    template_name = 'quotes/compatibility_results.html'

    def test_func(self):
        return super().test_func() and self.request.user.has_adwords_account

    def get(self, request, *args, **kwargs):
        adapter = Adapter(self.request.user)        
        monthly_spend = adapter.get_monthly_spend()
        
        quote = Quote(monthly_adwords_spend=monthly_spend)        
        quote.set_user_details(request.user, commit=False)
        quote.calculate_quote(commit=False)
        quote.set_type_automatic(commit=False)
        quote.save()
        
        request.session['quote_pk'] = quote.pk
        
        return super().get(request, *args, **kwargs)

    def get_checks(self):
        adwords_adapter = Adapter(self.request.user)
        return [
            check_class(adwords_adapter)
            for check_class in (
                CompatibilityCheckWebsiteTracking,
                CompatibilityCheckECommerceTracking,
                CompatibilityCheckOnPagePhoneCallTracking,
            )
        ]

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['compatibility_checks'] = self.get_checks()
        return context


class QuoteView(UnpaidAccountRequiredMixin, DetailView):
    template_name = 'quotes/quote.html'
    context_object_name = 'quote'
    model = Quote

    def get(self, request, *args, **kwargs):
        try:
            return super().get(request, *args, **kwargs)
        except Http404:
            # If no quote exists, redirect to the start of the process.
            return HttpResponseRedirect(reverse('quoting_adwords_preamble'))

    def post(self, request, *args, **kwargs):
        try:
            self.object = self.get_object()
        except Http404:
            # If no quote exists, redirect to the start of the process.
            return HttpResponseRedirect(reverse('quoting_adwords_preamble'))

        self.object.set_accepted()

        return HttpResponseRedirect(reverse('quoting_proceed_to_payment_gateway'))

    def get_object(self, queryset=None):
        # Get quote PK from the session.
        if queryset is None:
            queryset = self.get_queryset()

        if not self.request.session.get('quote_pk', None):
            raise Http404('No quote found in session')

        try:
            obj = queryset.get(pk=self.request.session['quote_pk'])
        except queryset.model.DoesNotExist:
            raise Http404('No {} found matching the query'.format(
                queryset.model._meta.verbose_name))
        return obj


class ProceedToPaymentGatewayView(TemplateView):
    template_name = 'quotes/proceed_to_payment_gateway.html'
    

    def get_context_data(self, **kwargs): # new
        context = super().get_context_data(**kwargs)
        if config.STRIPE_PAYMENT_SANDBOX is True:
            context['key'] = settings.STRIPE_SANDBOX_PUBLISHABLE_KEY
        else:
            context['key'] = settings.STRIPE_PUBLISHABLE_KEY

        context['user_email'] = self.request.user.get_email()        
        context['page_content'] = cms_page_content('account_payment_page')
        return context
  
def payment_success(request): # new
    if request.method == 'POST':
            stripe.api_key = 'sk_test_PSFnk5W3bFwy6Fz3K16X5gXN00s1FZfq80'
            token = request.POST['stripeToken']
            request.user.is_freerolled = 1
            request.user.save()
            # Charge the Customer instead of the card
            payment_intent = stripe.PaymentIntent.create(
               description='Captivise charge',
               shipping={
                'name': 'Jenny Rosen',
                'address': {
                  'line1': '510 Townsend St',
                  'postal_code': '98140',
                  'city': 'San Francisco',
                  'state': 'CA',
                  'country': 'US',
               },
              },
          amount=5,
          currency='usd',
          payment_method_types=['card'],
          )
            StripeResponse.objects.create(
               response_code= 200,
               timestamp= payment_intent.created,
               user_email=request.POST['stripeEmail'],
               response_data=json.dumps(payment_intent))
            
    return render(request, 'quotes/charge.html')


class PaymentFailedView(TemplateView):
    template_name = 'quotes/payment_failed.html'

    def dispatch(self, *args, **kwargs):
        # Disallow access to the page if there is no failed payment
        # to take care of.
        if self.request.user.has_payment_details:
            # 404 is appropriate in this case, as we're trying to act
            # upon a resource which doesn't exist; a failed payment.
            raise Http404

        # Restore the original initial continuous payment if it
        # existed, in case a user accidentally overwrites their
        # currently good card with a bad one.
        self.old_payment_reinstated = False
        previous_initial_CA_payments = self.request.user.previous_initial_continuous_authority_payments  # noqa
        if previous_initial_CA_payments.count():
            self.old_payment_reinstated = True
            previous_initial_CA_payment = previous_initial_CA_payments.last()
            previous_initial_CA_payments.remove(previous_initial_CA_payment)
            self.request.user.initial_continuous_authority_payment = previous_initial_CA_payment

            self.request.user.save()

        return super().dispatch(*args, **kwargs)

    def get_context_data(self, *args, **kwargs):
        context = super().get_context_data(*args, **kwargs)

        context.update({'old_payment_reinstated': self.old_payment_reinstated})

        return context

class StripeGetPublicKeyView(TemplateView):

    def get(self, request, *args, **kwargs):
        if config.STRIPE_PAYMENT_SANDBOX is True:
            data = {'publicKey': settings.STRIPE_SANDBOX_PUBLISHABLE_KEY}
        else:
            data = {'publicKey': settings.STRIPE_PUBLISHABLE_KEY}

        return JsonResponse(data)

@csrf_exempt
def StripeCreateSetupIntentView(request):
    
    stripe.api_version = settings.STRIPE_API_VERSION
    if config.STRIPE_PAYMENT_SANDBOX is True:
        stripe.api_key = settings.STRIPE_SANDBOX_SECRET_KEY
        stripe.public_key = settings.STRIPE_SANDBOX_PUBLISHABLE_KEY
    else:
        stripe.api_key = settings.STRIPE_SECRET_KEY
        stripe.public_key = settings.STRIPE_PUBLISHABLE_KEY
    
    #update customer id in user table
    try:
        user_info = StripeResponse.objects.get(user_id=request.user.id)
        customer_id = user_info.customer_id
    except:
        customer = stripe.Customer.create(
            email=request.user.get_email(),
            name=request.user.get_full_name()
        )
        customer_id = customer['id']
        StripeResponse.objects.create(
            user_id=request.user.id,
            customer_id=customer['id'])

    try:
        stripe_customer = stripe.Customer.retrieve(customer_id)
    except:  
        customer = stripe.Customer.create(
            email=request.user.get_email(),
            name=request.user.get_full_name()
        )
        customer_id = customer['id']
        user_info.customer_id = customer_id
        user_info.save()

    
    setup_intent = stripe.SetupIntent.create(
        customer=customer_id
    )
    return JsonResponse(setup_intent)

@csrf_exempt
def StripeUpdateSetupIntentView(request):
    
    stripe.api_version = settings.STRIPE_API_VERSION
    if config.STRIPE_PAYMENT_SANDBOX is True:
        stripe.api_key = settings.STRIPE_SANDBOX_SECRET_KEY
        stripe.public_key = settings.STRIPE_SANDBOX_PUBLISHABLE_KEY        
    else:
        stripe.public_key = settings.STRIPE_PUBLISHABLE_KEY
        stripe.api_key = settings.STRIPE_SECRET_KEY
    
    #return JsonResponse({'status':request.GET.get('setup_intents_id', False)})

    user_info = StripeResponse.objects.get(user_id=request.user.id)
    setup_id=request.POST.get('setup_intents_id', False)
    #user_info.setup_intents_id='seti_1Gp5SvHUiFyn8WdQdQwmYosF'
    c_secret=request.POST.get('client_secret', False)
    #user_info.client_secret='seti_1Gp5SvHUiFyn8WdQdQwmYosF_secret_HNrBxwtbOt1VSea4oum7QE7YsRLdjqu'
    p_method=request.POST.get('payment_method', False)
    #user_info.payment_method='pm_1Gp5YkHUiFyn8WdQR9f0h9dW'
    

    payment_info = stripe.PaymentMethod.retrieve(p_method,)
    #payment_info = stripe.PaymentMethod.retrieve('pm_1Gp5YkHUiFyn8WdQR9f0h9dW',)
    user_info.setup_intents_id=setup_id
    user_info.client_secret=c_secret
    user_info.payment_method=p_method
    user_info.card_number_mask=payment_info.card.last4
    user_info.card_expiry_year=payment_info.card.exp_year
    user_info.card_expiry_month=payment_info.card.exp_month
    user_info.card_type=payment_info.card.brand
    user_info.response_code=1
    user_info.save()

    request.user.show_card_expiry_warning = False
    request.user.stripe_pay_id = user_info.id
    request.user.save()

    return JsonResponse({'status':True})