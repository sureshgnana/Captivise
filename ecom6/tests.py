from django.test import TestCase

from .utils import generate_signature


class SignatureTestCase(TestCase):
    def test_generate_signature_output_matches_docs(self):
        signature = generate_signature(
            'DontTellAnyone',
            # Ecom6's docs have a different `merchantID`, but
            # neglected to change the signature expected.  Using
            # the `merchantID` provided in the CardStream docs
            # works just fine.
            merchantID='100001',
            action='SALE',
            type='1',
            currencyCode='826',
            countryCode='826',
            amount='2691',
            transactionUnique='55f025addd3c2',
            orderRef='Signature Test',
            cardNumber='4929 4212 3460 0821',
            cardExpiryDate='1213',
        )

        self.assertEqual(
            signature,
            (
                'da0acd2c404945365d0e7ae74ad32d57c561e9b942f6bdb7e3dda4'
                '9a08fcddf74fe6af6b23b8481b8dc8895c12fc21c72c69d60f137f'
                'df574720363e33d94097'
            ),
        )
