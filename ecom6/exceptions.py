class PaymentError(Exception):
    pass


class PaymentUnsuccessfulError(PaymentError):
    pass


class PaymentIncompleteError(PaymentError):
    pass


class PaymentNotContinuousAuthorityError(PaymentError):
    pass
