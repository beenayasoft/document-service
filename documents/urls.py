from django.urls import path, include
from rest_framework.routers import DefaultRouter

from .views import (
    QuoteViewSet,
    QuoteItemViewSet,
    InvoiceViewSet,
    InvoiceItemViewSet,
    PaymentViewSet,
    VATRateViewSet,
    QuoteStatusViewSet,
    InvoiceStatusViewSet,
    PaymentMethodViewSet,
    debug_headers
)

# Configuration du router REST
router = DefaultRouter()
router.register(r'quotes', QuoteViewSet, basename='quote')
router.register(r'quote-items', QuoteItemViewSet, basename='quoteitem')
router.register(r'invoices', InvoiceViewSet, basename='invoice')
router.register(r'invoice-items', InvoiceItemViewSet, basename='invoiceitem')
router.register(r'payments', PaymentViewSet, basename='payment')
router.register(r'vat-rates', VATRateViewSet, basename='vatrate')
router.register(r'quote-statuses', QuoteStatusViewSet, basename='quotestatus')
router.register(r'invoice-statuses', InvoiceStatusViewSet, basename='invoicestatus')
router.register(r'payment-methods', PaymentMethodViewSet, basename='paymentmethod')

# URL Patterns
urlpatterns = [
    path('', include(router.urls)),
    path('debug/', debug_headers, name='debug-headers'),
] 