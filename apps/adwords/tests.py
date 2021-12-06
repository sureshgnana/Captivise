from datetime import date

from django.test import SimpleTestCase

from adwords.adapter import Adapter


class AdapterTests(SimpleTestCase):

    def test_aggregate_metrics_to_monthly_is_correct_for_uncast_dates(self):
        data = {
            '2017-08-02': {'conversions': 1, 'cpc': 2, 'cost': 4},
            '2017-08-04': {'conversions': 8, 'cpc': 16, 'cost': 32},
            '2017-09-02': {'conversions': 64, 'cpc': 128, 'cost': 256},
            '2016-08-08': {'conversions': 512, 'cpc': 1024, 'cost': 2048},
        }

        expected = {
            '2017-08-01': {'conversions': 9, 'cpc': 18, 'cost': 36},
            '2017-09-01': {'conversions': 64, 'cpc': 128, 'cost': 256},
            '2016-08-01': {'conversions': 512, 'cpc': 1024, 'cost': 2048},
        }

        self.assertEqual(
            Adapter.aggregate_metrics_to_monthly(data, date_format='%Y-%m-%d'),
            expected,
        )

    def test_aggregate_metrics_to_monthly_is_correct_for_uncast_dates_with_averaged_columns(self):
        data = {
            '2017-08-02': {'conversions': 1, 'cpc': 2, 'cost': 4},
            '2017-08-04': {'conversions': 8, 'cpc': 16, 'cost': 32},
            '2017-09-02': {'conversions': 64, 'cpc': 128, 'cost': 256},
            '2016-08-08': {'conversions': 512, 'cpc': 1024, 'cost': 2048},
        }

        expected = {
            '2017-08-01': {'conversions': 9, 'cpc': 9, 'cost': 36},
            '2017-09-01': {'conversions': 64, 'cpc': 128, 'cost': 256},
            '2016-08-01': {'conversions': 512, 'cpc': 1024, 'cost': 2048},
        }

        self.assertEqual(
            Adapter.aggregate_metrics_to_monthly(data, date_format='%Y-%m-%d', average_columns=('cpc', )),
            expected,
        )

    def test_aggregate_metrics_to_monthly_is_correct_for_cast_dates(self):
        data = {
            date(2017, 8, 2): {'conversions': 1, 'cpc': 2, 'cost': 4},
            date(2017, 8, 4): {'conversions': 8, 'cpc': 16, 'cost': 32},
            date(2017, 9, 2): {'conversions': 64, 'cpc': 128, 'cost': 256},
            date(2016, 8, 8): {'conversions': 512, 'cpc': 1024, 'cost': 2048},
        }

        expected = {
            date(2017, 8, 1): {'conversions': 9, 'cpc': 18, 'cost': 36},
            date(2017, 9, 1): {'conversions': 64, 'cpc': 128, 'cost': 256},
            date(2016, 8, 1): {'conversions': 512, 'cpc': 1024, 'cost': 2048},
        }

        self.assertEqual(
            Adapter.aggregate_metrics_to_monthly(data),
            expected,
        )

    def test_aggregate_metrics_to_monthly_is_correct_with_averaged_columns(self):
        data = {
            date(2017, 8, 2): {'conversions': 1, 'cpc': 2, 'cost': 4},
            date(2017, 8, 4): {'conversions': 8, 'cpc': 16, 'cost': 32},
            date(2017, 9, 2): {'conversions': 64, 'cpc': 128, 'cost': 256},
            date(2016, 8, 8): {'conversions': 512, 'cpc': 1024, 'cost': 2048},
        }

        expected = {
            date(2017, 8, 1): {'conversions': 9, 'cpc': 9, 'cost': 36},
            date(2017, 9, 1): {'conversions': 64, 'cpc': 128, 'cost': 256},
            date(2016, 8, 1): {'conversions': 512, 'cpc': 1024, 'cost': 2048},
        }

        self.assertEqual(
            Adapter.aggregate_metrics_to_monthly(data, average_columns=('cpc', )),
            expected,
        )

    def test_aggregate_metrics_is_correct(self):
        data = [
            {0: 1, 2: 4},
            {0: 8, 2: 16},
        ]

        expected = {0: 9, 2: 20}

        self.assertEqual(
            Adapter._aggregate_metrics(data),
            expected,
        )

    def test_aggregate_metrics_is_correct_with_average_columns(self):
        data = [
            {0: 1, 2: 4},
            {0: 8, 2: 16},
        ]

        expected = {0: 4.5, 2: 20}

        self.assertEqual(
            Adapter._aggregate_metrics(data, average_columns=(0, )),
            expected,
        )

    def test_get_metric_shape_returns_correct_shape(self):
        metrics = {1: {2: 4, 8: ''}}
        metrics_list = [{16: 32, 64: ''}]
        empty_metrics = {}

        self.assertEqual(
            Adapter.get_metrics_shape(metrics),
            {2: 0, 8: 0},
        )

        self.assertEqual(
            Adapter.get_metrics_shape(metrics_list),
            {16: 0, 64: 0},
        )

        self.assertEqual(
            Adapter.get_metrics_shape(empty_metrics),
            {}
        )
