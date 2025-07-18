"""
ViewSets unifiés pour les documents commerciaux (devis et factures)
"""
from rest_framework import viewsets, status, filters
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django_filters.rest_framework import DjangoFilterBackend
from django.db.models import Count, Sum, Avg, Q, F
from django.db import transaction
from decimal import Decimal

from .models import (
    Quote, QuoteItem, Invoice, InvoiceItem, Payment,
    QuoteStatus, InvoiceStatus
)
from .serializers import (
    # Devis
    QuoteSerializer, QuoteDetailSerializer, QuoteCreateSerializer,
    QuoteItemSerializer, QuoteStatsSerializer,
    # Factures
    InvoiceSerializer, InvoiceDetailSerializer, InvoiceCreateSerializer,
    InvoiceItemSerializer, InvoiceStatsSerializer, PaymentSerializer,
    # Actions
    DocumentActionSerializer, RecordPaymentSerializer, CreateCreditNoteSerializer,
    BulkDocumentOperationSerializer, DocumentExportSerializer,
    # Configuration
    VATRateSerializer, QuoteStatusSerializer, InvoiceStatusSerializer, PaymentMethodSerializer
)
from .pagination import QuotesPagination, InvoicesPagination, DocumentItemsPagination
from .viewset_mixins import (
    CacheMixin, QueryOptimizationMixin, FilterMixin, StatsMixin,
    AuditMixin, DocumentActionMixin, BulkOperationMixin, ExportMixin
)

from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework import status

@api_view(['GET'])
def debug_headers(request):
    """
    Endpoint de debug pour vérifier les headers et l'authentification
    """
    return Response({
        'headers': dict(request.META),
        'tenant_id': getattr(request, 'tenant_id', None),
        'schema_name': getattr(request, 'schema_name', None),
        'user': str(request.user) if hasattr(request, 'user') else None,
        'path': request.path,
        'method': request.method,
        'x_tenant_id': request.META.get('HTTP_X_TENANT_ID'),
        'authorization': request.META.get('HTTP_AUTHORIZATION', '').replace('Bearer ', '')[:20] + '...' if request.META.get('HTTP_AUTHORIZATION') else None,
    }, status=status.HTTP_200_OK)


# =============================================================================
# VIEWSETS POUR LES DEVIS
# =============================================================================

class QuoteViewSet(viewsets.ModelViewSet,
                   CacheMixin, QueryOptimizationMixin, FilterMixin,
                   StatsMixin, AuditMixin, DocumentActionMixin,
                   BulkOperationMixin, ExportMixin):
    """
    ViewSet unifié pour les devis avec toutes les optimisations
    
    Endpoints disponibles:
    - CRUD standard: list, retrieve, create, update, destroy
    - Actions: stats, send, accept, reject, cancel, duplicate, export
    - Opérations en lot: bulk_operations
    """
    
    queryset = Quote.objects.all()
    serializer_class = QuoteSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['status', 'tier_id', 'opportunity_id', 'issue_date', 'expiry_date']
    search_fields = ['number', 'client_name', 'project_name', 'notes']
    ordering_fields = ['created_at', 'issue_date', 'expiry_date', 'total_ttc', 'number']
    ordering = ['-created_at']
    pagination_class = QuotesPagination
    
    def get_serializer_class(self):
        """Utilise le bon serializer selon l'action"""
        if self.action == 'retrieve':
            return QuoteDetailSerializer
        elif self.action == 'create':
            return QuoteCreateSerializer
        elif self.action in ['send', 'accept', 'reject', 'cancel']:
            return DocumentActionSerializer
        elif self.action == 'export':
            return DocumentExportSerializer
        elif self.action == 'bulk_operations':
            return BulkDocumentOperationSerializer
        return QuoteSerializer
    
    def get_queryset(self):
        """Queryset optimisé avec filtres avancés"""
        queryset = self.get_optimized_queryset()
        return self.apply_advanced_filters(queryset)
    
    def list(self, request, *args, **kwargs):
        """Liste des devis avec cache Redis"""
        # Essayer de récupérer depuis le cache
        cached_response = self.get_cached_response('list')
        if cached_response:
            return cached_response
        
        # Si pas en cache, utiliser la méthode parent
        response = super().list(request, *args, **kwargs)
        
        # Mettre en cache et retourner
        return self.set_cached_response('list', response.data)
    
    @action(detail=False, methods=['get'])
    def stats(self, request):
        """Statistiques globales des devis avec cache Redis"""
        # Essayer le cache d'abord
        cached_response = self.get_cached_response('stats')
        if cached_response:
            return cached_response
        
        # Calculer les stats avec une seule requête optimisée
        queryset = self.get_optimized_queryset('stats')
        
        # Stats de base
        base_stats = self.calculate_base_stats(queryset)
        
        # Stats spécifiques aux devis
        quote_specific = queryset.aggregate(
            # Taux d'acceptation
            acceptance_rate=Count('id', filter=Q(status=QuoteStatus.ACCEPTED)) * 100.0 / Count('id'),
            # Montant moyen par statut
            avg_accepted_amount=Avg('total_ttc', filter=Q(status=QuoteStatus.ACCEPTED)) or Decimal('0'),
            # Délai moyen de validation
            avg_validation_days=Avg(
                F('updated_at') - F('created_at'),
                filter=Q(status__in=[QuoteStatus.ACCEPTED, QuoteStatus.REJECTED])
            )
        )
        
        stats_data = {**base_stats, **quote_specific}
        
        # Mettre en cache et retourner
        return self.set_cached_response('stats', stats_data)
    
    @action(detail=True, methods=['post'])
    def send(self, request, pk=None):
        """Marquer un devis comme envoyé"""
        quote = self.get_object()
        serializer = self.get_serializer(data=request.data)
        
        if serializer.is_valid():
            return self.perform_document_action(
                quote, 'send', serializer.validated_data.get('note')
            )
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
    @action(detail=True, methods=['post'])
    def accept(self, request, pk=None):
        """Marquer un devis comme accepté"""
        quote = self.get_object()
        serializer = self.get_serializer(data=request.data)
        
        if serializer.is_valid():
            return self.perform_document_action(
                quote, 'accept', serializer.validated_data.get('note')
            )
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
    @action(detail=True, methods=['post'])
    def reject(self, request, pk=None):
        """Marquer un devis comme rejeté"""
        quote = self.get_object()
        serializer = self.get_serializer(data=request.data)
        
        if serializer.is_valid():
            return self.perform_document_action(
                quote, 'reject', serializer.validated_data.get('note')
            )
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
    @action(detail=True, methods=['post'])
    def cancel(self, request, pk=None):
        """Marquer un devis comme annulé"""
        quote = self.get_object()
        serializer = self.get_serializer(data=request.data)
        
        if serializer.is_valid():
            return self.perform_document_action(
                quote, 'cancel', serializer.validated_data.get('note')
            )
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
    @action(detail=True, methods=['post'])
    def duplicate(self, request, pk=None):
        """Dupliquer un devis"""
        original_quote = self.get_object()
        
        with transaction.atomic():
            # Créer une copie du devis
            new_quote = Quote.objects.create(
                tier_id=original_quote.tier_id,
                client_name=original_quote.client_name,
                client_address=original_quote.client_address,
                project_name=original_quote.project_name,
                project_address=original_quote.project_address,
                project_reference=original_quote.project_reference,
                notes=original_quote.notes,
                terms_and_conditions=original_quote.terms_and_conditions,
                validity_period=original_quote.validity_period,
                margin=original_quote.margin,
                created_by=self.get_user_info()
            )
            
            # Copier tous les éléments
            for item in original_quote.items.all():
                QuoteItem.objects.create(
                    quote=new_quote,
                    type=item.type,
                    parent=item.parent,
                    position=item.position,
                    reference=item.reference,
                    designation=item.designation,
                    description=item.description,
                    unit=item.unit,
                    quantity=item.quantity,
                    unit_price=item.unit_price,
                    discount=item.discount,
                    vat_rate=item.vat_rate,
                    margin=item.margin,
                    work_id=item.work_id
                )
            
            # Mettre à jour les totaux
            new_quote.update_totals()
            self._invalidate_cache()
            
            serializer = QuoteDetailSerializer(new_quote)
            return Response(serializer.data, status=status.HTTP_201_CREATED)
    
    @action(detail=True, methods=['post'])
    def export(self, request, pk=None):
        """Exporter un devis"""
        quote = self.get_object()
        serializer = self.get_serializer(data=request.data)
        
        if serializer.is_valid():
            return self.export_document(
                quote,
                serializer.validated_data.get('format', 'pdf'),
                serializer.validated_data.get('include_details', True)
            )
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
    @action(detail=False, methods=['post'])
    def bulk_operations(self, request):
        """Opérations en lot sur les devis"""
        serializer = self.get_serializer(data=request.data)
        
        if serializer.is_valid():
            return self.perform_bulk_operation(
                serializer.validated_data['action'],
                serializer.validated_data['document_ids']
            )
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class QuoteItemViewSet(viewsets.ModelViewSet, AuditMixin):
    """ViewSet pour les éléments de devis"""
    
    queryset = QuoteItem.objects.all()
    serializer_class = QuoteItemSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['quote', 'type', 'parent']
    search_fields = ['designation', 'description', 'reference']
    ordering_fields = ['position', 'designation', 'unit_price', 'total_ht']
    ordering = ['position']
    pagination_class = DocumentItemsPagination
    
    def get_queryset(self):
        """Queryset optimisé pour les éléments"""
        return QuoteItem.objects.select_related('quote', 'parent').prefetch_related('children')
    
    @action(detail=False, methods=['get'])
    def by_quote(self, request):
        """Récupérer les éléments d'un devis spécifique"""
        quote_id = request.query_params.get('quote_id')
        if not quote_id:
            return Response(
                {'error': 'quote_id requis'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        items = self.get_queryset().filter(quote_id=quote_id)
        serializer = self.get_serializer(items, many=True)
        return Response(serializer.data)


# =============================================================================
# VIEWSETS POUR LES FACTURES
# =============================================================================

class InvoiceViewSet(viewsets.ModelViewSet,
                     CacheMixin, QueryOptimizationMixin, FilterMixin,
                     StatsMixin, AuditMixin, DocumentActionMixin,
                     BulkOperationMixin, ExportMixin):
    """
    ViewSet unifié pour les factures avec toutes les optimisations
    
    Endpoints disponibles:
    - CRUD standard: list, retrieve, create, update, destroy
    - Actions: stats, validate, record_payment, create_credit_note, export
    - Opérations en lot: bulk_operations
    """
    
    queryset = Invoice.objects.all()
    serializer_class = InvoiceSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['status', 'tier_id', 'quote_id', 'is_credit_note', 'issue_date', 'due_date']
    search_fields = ['number', 'client_name', 'project_name', 'notes', 'quote_number']
    ordering_fields = ['created_at', 'issue_date', 'due_date', 'total_ttc', 'remaining_amount']
    ordering = ['-created_at']
    pagination_class = InvoicesPagination
    
    def get_serializer_class(self):
        """Utilise le bon serializer selon l'action"""
        if self.action == 'retrieve':
            return InvoiceDetailSerializer
        elif self.action == 'create':
            return InvoiceCreateSerializer
        elif self.action in ['validate', 'send']:
            return DocumentActionSerializer
        elif self.action == 'record_payment':
            return RecordPaymentSerializer
        elif self.action == 'create_credit_note':
            return CreateCreditNoteSerializer
        elif self.action == 'export':
            return DocumentExportSerializer
        elif self.action == 'bulk_operations':
            return BulkDocumentOperationSerializer
        return InvoiceSerializer
    
    def get_queryset(self):
        """Queryset optimisé avec filtres avancés"""
        queryset = self.get_optimized_queryset()
        return self.apply_advanced_filters(queryset)
    
    def list(self, request, *args, **kwargs):
        """Liste des factures avec cache Redis"""
        # Essayer de récupérer depuis le cache
        cached_response = self.get_cached_response('list')
        if cached_response:
            return cached_response
        
        # Si pas en cache, utiliser la méthode parent
        response = super().list(request, *args, **kwargs)
        
        # Mettre en cache et retourner
        return self.set_cached_response('list', response.data)
    
    @action(detail=False, methods=['get'])
    def stats(self, request):
        """Statistiques globales des factures avec cache Redis"""
        # Essayer le cache d'abord
        cached_response = self.get_cached_response('stats')
        if cached_response:
            return cached_response
        
        # Calculer les stats avec une seule requête optimisée
        queryset = self.get_optimized_queryset('stats')
        
        # Stats de base
        base_stats = self.calculate_base_stats(queryset)
        
        # Stats spécifiques aux factures
        invoice_specific = queryset.aggregate(
            # Montants de paiement
            total_paid=Sum('paid_amount') or Decimal('0'),
            total_outstanding=Sum('remaining_amount') or Decimal('0'),
            overdue_amount=Sum(
                'remaining_amount',
                filter=Q(status=InvoiceStatus.OVERDUE)
            ) or Decimal('0'),
            
            # Délai moyen de paiement
            avg_payment_delay=Avg(
                F('payments__date') - F('issue_date'),
                filter=Q(status=InvoiceStatus.PAID)
            ),
            
            # Taux de paiement
            payment_rate=Count('id', filter=Q(status=InvoiceStatus.PAID)) * 100.0 / Count('id')
        )
        
        stats_data = {**base_stats, **invoice_specific}
        
        # Mettre en cache et retourner
        return self.set_cached_response('stats', stats_data)
    
    @action(detail=True, methods=['post'])
    def validate(self, request, pk=None):
        """Valider et envoyer une facture"""
        invoice = self.get_object()
        serializer = self.get_serializer(data=request.data)
        
        if serializer.is_valid():
            return self.perform_document_action(
                invoice, 'validate', serializer.validated_data.get('note')
            )
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
    @action(detail=True, methods=['post'])
    def record_payment(self, request, pk=None):
        """Enregistrer un paiement"""
        invoice = self.get_object()
        serializer = self.get_serializer(data=request.data)
        
        if serializer.is_valid():
            data = serializer.validated_data
            
            # Vérifier que le montant ne dépasse pas le restant dû
            if data['amount'] > invoice.remaining_amount:
                return Response(
                    {'error': 'Le montant du paiement ne peut pas dépasser le restant dû'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            # Enregistrer le paiement
            payment = invoice.record_payment(
                amount=data['amount'],
                method=data['method'],
                date=data.get('date'),
                reference=data.get('reference'),
                notes=data.get('notes')
            )
            
            self._invalidate_cache()
            
            return Response({
                'message': 'Paiement enregistré avec succès',
                'payment_id': str(payment.id),
                'invoice_status': invoice.status,
                'remaining_amount': invoice.remaining_amount
            })
        
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
    @action(detail=True, methods=['post'])
    def create_credit_note(self, request, pk=None):
        """Créer un avoir"""
        invoice = self.get_object()
        serializer = self.get_serializer(data=request.data)
        
        if serializer.is_valid():
            data = serializer.validated_data
            
            # Créer l'avoir
            credit_note = invoice.create_credit_note(
                reason=data.get('reason', ''),
                is_full_credit_note=data.get('is_full_credit_note', True),
                selected_items=data.get('selected_items', [])
            )
            
            self._invalidate_cache()
            
            credit_note_serializer = InvoiceDetailSerializer(credit_note)
            return Response({
                'message': 'Avoir créé avec succès',
                'credit_note': credit_note_serializer.data
            }, status=status.HTTP_201_CREATED)
        
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
    @action(detail=True, methods=['post'])
    def export(self, request, pk=None):
        """Exporter une facture"""
        invoice = self.get_object()
        serializer = self.get_serializer(data=request.data)
        
        if serializer.is_valid():
            return self.export_document(
                invoice,
                serializer.validated_data.get('format', 'pdf'),
                serializer.validated_data.get('include_details', True)
            )
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
    @action(detail=False, methods=['post'])
    def bulk_operations(self, request):
        """Opérations en lot sur les factures"""
        serializer = self.get_serializer(data=request.data)
        
        if serializer.is_valid():
            return self.perform_bulk_operation(
                serializer.validated_data['action'],
                serializer.validated_data['document_ids']
            )
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class InvoiceItemViewSet(viewsets.ModelViewSet, AuditMixin):
    """ViewSet pour les éléments de factures"""
    
    queryset = InvoiceItem.objects.all()
    serializer_class = InvoiceItemSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['invoice', 'type', 'parent']
    search_fields = ['designation', 'description', 'reference']
    ordering_fields = ['position', 'designation', 'unit_price', 'total_ht']
    ordering = ['position']
    pagination_class = DocumentItemsPagination
    
    def get_queryset(self):
        """Queryset optimisé pour les éléments"""
        return InvoiceItem.objects.select_related('invoice', 'parent').prefetch_related('children')
    
    @action(detail=False, methods=['get'])
    def by_invoice(self, request):
        """Récupérer les éléments d'une facture spécifique"""
        invoice_id = request.query_params.get('invoice_id')
        if not invoice_id:
            return Response(
                {'error': 'invoice_id requis'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        items = self.get_queryset().filter(invoice_id=invoice_id)
        serializer = self.get_serializer(items, many=True)
        return Response(serializer.data)


class PaymentViewSet(viewsets.ModelViewSet, AuditMixin):
    """ViewSet pour les paiements"""
    
    queryset = Payment.objects.all()
    serializer_class = PaymentSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['invoice', 'method', 'date']
    search_fields = ['reference', 'notes']
    ordering_fields = ['date', 'amount', 'created_at']
    ordering = ['-date']
    
    def get_queryset(self):
        """Queryset optimisé pour les paiements"""
        return Payment.objects.select_related('invoice')
    
    @action(detail=False, methods=['get'])
    def by_invoice(self, request):
        """Récupérer les paiements d'une facture spécifique"""
        invoice_id = request.query_params.get('invoice_id')
        if not invoice_id:
            return Response(
                {'error': 'invoice_id requis'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        payments = self.get_queryset().filter(invoice_id=invoice_id)
        serializer = self.get_serializer(payments, many=True)
        return Response(serializer.data)


# =============================================================================
# VIEWSETS POUR LES MODÈLES DE CONFIGURATION
# =============================================================================

from .models import VATRate, PaymentMethod
from .serializers import VATRateSerializer, PaymentMethodSerializer

class VATRateViewSet(viewsets.ReadOnlyModelViewSet):
    """ViewSet en lecture seule pour les taux de TVA (TextChoices)"""
    
    # Les taux de TVA sont des données de référence qui peuvent être publiques
    permission_classes = []
    serializer_class = VATRateSerializer
    
    def list(self, request, *args, **kwargs):
        """Liste les taux de TVA disponibles"""
        vat_rates = [
            {
                'code': choice[0], 
                'name': choice[1], 
                'rate': float(choice[0]),
                'rate_display': f"{choice[0]}%",
                'description': f"Taux de TVA à {choice[0]}%",
                'is_default': choice[0] == VATRate.STANDARD,
                'is_active': True
            }
            for choice in VATRate.choices
        ]
        return Response(vat_rates)


class QuoteStatusViewSet(viewsets.ReadOnlyModelViewSet):
    """ViewSet en lecture seule pour les statuts de devis"""
    
    permission_classes = [IsAuthenticated]
    serializer_class = QuoteStatusSerializer
    
    def list(self, request, *args, **kwargs):
        """Liste les statuts disponibles"""
        statuses = [
            {'code': QuoteStatus.DRAFT, 'name': 'Brouillon', 'description': 'Devis en cours de rédaction'},
            {'code': QuoteStatus.SENT, 'name': 'Envoyé', 'description': 'Devis envoyé au client'},
            {'code': QuoteStatus.ACCEPTED, 'name': 'Accepté', 'description': 'Devis accepté par le client'},
            {'code': QuoteStatus.REJECTED, 'name': 'Refusé', 'description': 'Devis refusé par le client'},
            {'code': QuoteStatus.EXPIRED, 'name': 'Expiré', 'description': 'Devis expiré'},
            {'code': QuoteStatus.CANCELLED, 'name': 'Annulé', 'description': 'Devis annulé'},
        ]
        return Response(statuses)


class InvoiceStatusViewSet(viewsets.ReadOnlyModelViewSet):
    """ViewSet en lecture seule pour les statuts de factures"""
    
    permission_classes = [IsAuthenticated]
    serializer_class = InvoiceStatusSerializer
    
    def list(self, request, *args, **kwargs):
        """Liste les statuts disponibles"""
        statuses = [
            {'code': InvoiceStatus.DRAFT, 'name': 'Brouillon', 'description': 'Facture en cours de rédaction'},
            {'code': InvoiceStatus.SENT, 'name': 'Envoyée', 'description': 'Facture envoyée au client'},
            {'code': InvoiceStatus.PAID, 'name': 'Payée', 'description': 'Facture entièrement payée'},
            {'code': InvoiceStatus.PARTIALLY_PAID, 'name': 'Partiellement payée', 'description': 'Facture partiellement payée'},
            {'code': InvoiceStatus.OVERDUE, 'name': 'En retard', 'description': 'Facture en retard de paiement'},
            {'code': InvoiceStatus.CANCELLED, 'name': 'Annulée', 'description': 'Facture annulée'},
        ]
        return Response(statuses)


class PaymentMethodViewSet(viewsets.ReadOnlyModelViewSet):
    """ViewSet en lecture seule pour les moyens de paiement (TextChoices)"""
    
    permission_classes = [IsAuthenticated]
    serializer_class = PaymentMethodSerializer
    
    def list(self, request, *args, **kwargs):
        """Liste les moyens de paiement disponibles"""
        payment_methods = [
            {
                'code': choice[0], 
                'name': choice[1],
                'description': f"Paiement par {choice[1].lower()}",
                'requires_reference': choice[0] in ['bank_transfer', 'check'],
                'is_active': True
            }
            for choice in PaymentMethod.choices
        ]
        return Response(payment_methods)
