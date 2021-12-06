from django.apps import apps
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured, ValidationError
from django.http import Http404
from django.utils.decorators import method_decorator
from django.utils.functional import cached_property
from django.views.decorators.csrf import csrf_exempt
from django.views.generic import FormView
from django.views.generic.edit import ModelFormMixin

from .forms import ResponseForm, get_payment_form
from .utils import PaymentModelLookupMixin


class PaymentDetailBaseView(PaymentModelLookupMixin, ModelFormMixin, FormView):

    def get_form_class(self):
        return get_payment_form(self.model)

    def get_form_kwargs(self, *args, **kwargs):
        kwargs = super().get_form_kwargs(*args, **kwargs)

        kwargs['scheme'] = self.request.scheme
        kwargs['host'] = self.request.get_host()

        return kwargs

    @property
    def object(self):
        return self.get_object()

    def get_object(self):
        """
        Looks up `payment_pk` in the session, and returns the
        AbstractBasePayment subclass referred to by it, if it exists.

        This can be sensibly overridden to instantiate and return a
        subclass of AbstractBasePayment.
        """
        payment_pk = self.request.session.get('payment_pk', None)
        if payment_pk is None:
            raise Http404(
                '`payment_pk` has not been set in the session.  Either'
                ' do so, or override `{0}.get_object()` to create a'
                ' payment model instance.'.format(self.__class__.__name__)
            )

        try:
            return self.model._default_manager.get(pk=payment_pk)
        except self.model.DoesNotExist:
            raise Http404(
                'The `payment_pk` in the session refers to a model that'
                ' doesn\'t exist.'
            )


@method_decorator(csrf_exempt, name='dispatch')
class ResponseView(FormView):
    form_class = ResponseForm
    http_method_names = ('post', )

    def form_invalid(self, form):
        # This should not be reached unless Ecom6 changes something
        # unexpectedly.  Raise an exception to log it and bring to
        # attention.
        raise ValidationError((form.errors, form.non_field_errors()))

    def form_valid(self, form):
        instance = form.save()

        return instance.payment.get_redirect()
