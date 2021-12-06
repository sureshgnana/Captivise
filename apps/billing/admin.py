from django import forms
from django.contrib import admin
from django.core.exceptions import ValidationError
from django.forms.models import BaseInlineFormSet
from django.shortcuts import reverse
from django.utils.safestring import mark_safe

from reports.forms import MicroAmountInput

from .models import Payment, PriceBand, Pricing
import decimal


class PriceBandForm(forms.ModelForm):
    class Meta:
        model = Pricing
        widgets = {
            'maximum': MicroAmountInput(),
        }
        fields = '__all__'


class PriceBandInlineFormset(BaseInlineFormSet):

    def clean(self):
        super().clean()

        has_open_upper_band = False
        maximums = []

        for form in self.forms:
            if not form.cleaned_data['DELETE']:
                # Check there's an upper price band with no maximum.
                if not form.cleaned_data['maximum']:
                    has_open_upper_band = True

                # Check for duplicate maximums as if they're created at
                # the same time Django will not perform the validation.
                if form.cleaned_data['maximum'] in maximums:
                    raise ValidationError(
                        'The price band with maximum £{} appears more than once: it should not be '
                        'repeated.'.format(form.cleaned_data['maximum']))
                maximums.append(form.cleaned_data['maximum'])

        if not has_open_upper_band:
            raise ValidationError('Please add the upper price band with no maximum.')


class PriceBandInlineAdmin(admin.TabularInline):
    model = PriceBand
    extra = 0
    formset = PriceBandInlineFormset
    form = PriceBandForm


@admin.register(Pricing)
class PricingAdmin(admin.ModelAdmin):
    inlines = (
        PriceBandInlineAdmin,
    )
    actions = None

    def has_add_permission(self, request):
        # Only allow one pricing object.
        if Pricing.objects.exists():
            return False
        return super().has_add_permission(request)

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = ('user', 'payment_amount', 'transaction_id', 'status', 'created_at',)
    exclude = ('response', )
    readonly_fields = [
        field.name for field in Payment._meta.fields if field.name != 'response'
    ] + ['response_link']

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def response_link(self, obj):
        return mark_safe('<a href="{url}">{name}</a>'.format(
            url=reverse('admin:ecom6_response_change', args=(obj.response.pk, )),
            name=obj.response,
        ))
    response_link.short_description = 'response'

    def payment_amount(self, obj):
        return decimal.Decimal(obj.amount/ 100.0).quantize(decimal.Decimal('0.01'))
