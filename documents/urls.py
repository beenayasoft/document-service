from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    QuoteViewSet, InvoiceViewSet, QuoteItemViewSet, InvoiceItemViewSet,
    PaymentViewSet, VATRateViewSet, PaymentTermViewSet,
    generate_pdf, health_check, PaymentMethodViewSet,
    performance_diagnostics, test_document_creation_performance, warm_up_cache,
    next_project_reference
)

router = DefaultRouter()
router.register(r'quotes', QuoteViewSet, basename='quote')
router.register(r'invoices', InvoiceViewSet, basename='invoice')
router.register(r'quote-items', QuoteItemViewSet, basename='quoteitem')
router.register(r'invoice-items', InvoiceItemViewSet, basename='invoiceitem')
router.register(r'payments', PaymentViewSet, basename='payment')
router.register(r'vat-rates', VATRateViewSet, basename='vatrate')
router.register(r'payment-terms', PaymentTermViewSet, basename='paymentterm')
router.register(r'payment-methods', PaymentMethodViewSet, basename='paymentmethod')

urlpatterns = [
    path('', include(router.urls)),
    path('quotes/<uuid:pk>/pdf/', generate_pdf, name='generate_pdf'),
    path('invoices/<uuid:pk>/pdf/', generate_pdf, name='generate_invoice_pdf'),
    path('projects/next-reference/', next_project_reference, name='next_project_reference'),
    path('health/', health_check, name='health_check'),
    path('diagnostics/', performance_diagnostics, name='performance_diagnostics'),
    path('test-performance/', test_document_creation_performance, name='test_document_creation_performance'),
    path('warm-up-cache/', warm_up_cache, name='warm_up_cache'),
] 