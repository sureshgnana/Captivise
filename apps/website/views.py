from django.http import HttpResponse, HttpResponseBadRequest
from django.views.generic import FormView, TemplateView

from .forms import DismissBannerForm
from .utils import cms_page_content
#30/11/2020
#from accounts.views import PaidAccountRequiredMixin
#from django.contrib.auth.mixins import LoginRequiredMixin
#from .models import CmsContent


class ActiveMenuItemMixin(object):

    def get_active_menu(self):
        return {}

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        context.update({
            'active_menu': self.get_active_menu(),
        })

        return context


class TermsAndConditionsView(TemplateView):
    template_name = 'website/terms_and_conditions.html'
    def get_context_data(self, **kwargs): # new
        context = super().get_context_data(**kwargs)
                
        context['page_content'] = cms_page_content('terms_and_conditions', 10)
        return context


class HttpResponseNoContent(HttpResponse):
    status_code = 204


class DismissBannerView(FormView):
    form_class = DismissBannerForm
    http_method_names = ('post', 'options', )

    def form_valid(self, form):
        hidden_banners = set(self.request.session.get('hidden_banners', []))
        hidden_banners.add(form.cleaned_data['banner_name'])
        self.request.session['hidden_banners'] = list(hidden_banners)

        return HttpResponseNoContent()

    def form_invalid(self, form):
        return HttpResponseBadRequest()


#30/11/2020
"""class CmsContentView(
    ActiveMenuItemMixin,
    LoginRequiredMixin,
    PaidAccountRequiredMixin,
    TemplateView):
    model = CmsContent

    def get_active_menu(self):
        return {
            'information': True,
        }

    template_name = 'website/show_cms_content.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        if not self.request.user.has_adwords_account:
            return context

        context['has_adwords_account'] = True

        cms_id = int(self.kwargs['cms_id'])
        cms_content = CmsContent.objects.get(pk=cms_id)
        context.update({
            'cms_content': cms_content
        })

        return context
"""
