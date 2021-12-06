"""captivise URL Configuration

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/1.10/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  url(r'^$', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  url(r'^$', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.conf.urls import url, include
    2. Add a URL to urlpatterns:  url(r'^blog/', include('blog.urls'))
"""
from django.conf.urls import url, include
from django.contrib import admin
from django.conf import settings
from django.conf.urls.static import static

urlpatterns = [
    url(r'^manage/', admin.site.urls),

    url(r'^ecom6/', include(('ecom6.urls', 'ecom6'), namespace='ecom6')),
    url(r'^', include('reports.urls')),
    url(r'^', include('accounts.urls')),
    url(r'^', include('website.urls')),
    url(r'^', include('quotes.urls')),
    url(r'^', include('website.urls')),
    url(r'^', include('report_scripts.urls')),
]+static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)+static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)

app_name = 'captivise'

admin.site.site_header = "Captivise Admin"
admin.site.site_title = "Captivise Admin"
admin.site.index_title = "Captivise Admin"
