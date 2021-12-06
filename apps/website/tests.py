from datetime import date

from django.test import SimpleTestCase

from website.utils import months_difference


class UtilsTests(SimpleTestCase):

    def test_months_difference_is_correct(self):
        nov17 = date(2017, 11, 1)
        dec17 = date(2017, 12, 1)
        jan18 = date(2018, 1, 1)

        self.assertEqual(months_difference(nov17, dec17), 1)
        self.assertEqual(months_difference(dec17, jan18), 1)
        self.assertEqual(months_difference(jan18, dec17), -1)
        self.assertEqual(months_difference(dec17, nov17), -1)
