from django.conf import settings
import decimal

from django.contrib import admin

import google_auth_httplib2
from googleapiclient import discovery
from googleapiclient import errors
from googleapiclient import http
from googleapiclient import model
from shopping.content import common
from shopping.content import auth
import google.auth
from google.oauth2 import service_account

class GoogleMerchantConnect:

    def __init__(self, user):
        self._user = user

    def get_products(self):   
        MAX_PAGE_SIZE = 100
        
        merchant_id = self._user.merchant_id
        merchant_refresh_token = self._user.merchant_refresh_token


        credentials = google.oauth2.credentials.Credentials(
            None,
            client_id=settings.ADWORDS_CLIENT_ID,
            client_secret=settings.ADWORDS_SECRET_KEY,
            refresh_token=merchant_refresh_token,
            token_uri='https://oauth2.googleapis.com/token',
            scopes=['https://www.googleapis.com/auth/content'])
          
        credentials.refresh(google.auth.transport.requests.Request())
        auth_http = google_auth_httplib2.AuthorizedHttp(
            credentials, http=http.set_user_agent(
                http.build_http(), 'Content API for Shopping Samples'))

        service = discovery.build(
            'content', 'v2.1', http=auth_http)

        request = service.products().list(
            merchantId=merchant_id, maxResults=MAX_PAGE_SIZE)
        products_list = []
        while request is not None:
            result = request.execute()
            products = result.get('resources')
            if not products:
                break
            for product in products:
                product_info = {'id':product['offerId'], 'title':product['title'], 'description':product['description'], 'price':product['price']['value']}
                products_list.append(product_info)
            request = service.products().list_next(request, result)        

        return products_list
    
    def get_products_text(self):
        products = self.get_products()
        if len(products) > 0:
            product_texts = []
            for product in products:
                product_text = ' '.join([product['title'], product['description']])
                product_texts.append(product_text)
            
            if len(product_texts) > 0:
                return str(product_texts)
        else:
            return False
    
    def get_products_id_price(self):
        products = self.get_products()
        if len(products) > 0:
            product_id_price = {}
            for product in products:
                product_id_price[product['id']] = product['price']            
            if len(product_id_price) > 0:
                return product_id_price
        else:
            return False
