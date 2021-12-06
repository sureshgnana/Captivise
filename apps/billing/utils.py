from .models import Pricing


def get_pricing():
    return Pricing.objects.prefetch_related('price_bands').get()
