from django.conf.urls import url

from .views import ResponseView


urlpatterns = [
    url(r'ecom6-redirect-url/', ResponseView.as_view(), name='ecom6-redirect-url'),
]
