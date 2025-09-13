from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    QuoteViewSet, InvoiceViewSet, QuoteItemViewSet, InvoiceItemViewSet,
    PaymentViewSet, VATRateViewSet, PaymentTermViewSet,
    health_check, PaymentMethodViewSet,
    performance_diagnostics, test_document_creation_performance, warm_up_cache,
    next_project_reference
)
# from .views_templates import DocumentTemplateViewSet, TemplateUsageLogViewSet
# from .views_pdf import PDFGenerationViewSet

router = DefaultRouter()
router.register(r'quotes', QuoteViewSet, basename='quote')
router.register(r'invoices', InvoiceViewSet, basename='invoice')
router.register(r'quote-items', QuoteItemViewSet, basename='quoteitem')
router.register(r'invoice-items', InvoiceItemViewSet, basename='invoiceitem')
router.register(r'payments', PaymentViewSet, basename='payment')
router.register(r'vat-rates', VATRateViewSet, basename='vatrate')
router.register(r'payment-terms', PaymentTermViewSet, basename='paymentterm')
router.register(r'payment-methods', PaymentMethodViewSet, basename='paymentmethod')

# API des templates de documents
# router.register(r'templates', DocumentTemplateViewSet, basename='documenttemplate')
# router.register(r'template-usage-logs', TemplateUsageLogViewSet, basename='templateusagelog')

# API de génération PDF
# router.register(r'pdf', PDFGenerationViewSet, basename='documentpdf')

# from rest_framework.decorators import api_view
# from rest_framework.response import Response
# from .services.template_service import initialize_templates

# @api_view(['POST'])
# def initialize_default_templates(request):
#     """Endpoint pour initialiser les templates par défaut"""
#     result = initialize_templates()
#     status_code = 200 if result['status'] != 'error' else 500
#     return Response(result, status=status_code)

urlpatterns = [
    path('', include(router.urls)),
    path('projects/next-reference/', next_project_reference, name='next_project_reference'),
    path('health/', health_check, name='health_check'),
    path('diagnostics/', performance_diagnostics, name='performance_diagnostics'),
    path('test-performance/', test_document_creation_performance, name='test_document_creation_performance'),
    path('warm-up-cache/', warm_up_cache, name='warm_up_cache'),
    
    # Templates
    # path('templates/initialize/', initialize_default_templates, name='initialize_default_templates'),
] 