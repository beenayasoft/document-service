"""
ViewSets unifiés pour les documents commerciaux (devis et factures)
"""
from rest_framework import viewsets, status, filters, permissions
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import AllowAny
from django_filters.rest_framework import DjangoFilterBackend
from django.db.models import Count, Sum, Avg, Q, F
from django.db import transaction
from decimal import Decimal, InvalidOperation

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
from django.http import HttpResponse, Http404
from django.shortcuts import get_object_or_404
from django.utils import timezone

from .services.vat_rate_service import vat_rate_service
from .services.payment_term_service import PaymentTermService
# from .services.document_appearance_service import document_appearance_service  # SUPPRIMÉ
from .services.number_service import DocumentNumberService
import logging

logger = logging.getLogger(__name__)

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
    permission_classes = [AllowAny]  # La sécurité est gérée par l'API Gateway et le middleware tenant
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['status', 'opportunity_id', 'issue_date', 'expiry_date']
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
        elif self.action == 'update' or self.action == 'partial_update':
            # Utiliser QuoteCreateSerializer pour la mise à jour pour gérer les items
            return QuoteCreateSerializer
        elif self.action in ['send', 'accept', 'reject', 'cancel']:
            return DocumentActionSerializer
        elif self.action == 'convert_to_invoice':
            return DocumentActionSerializer
        elif self.action == 'export':
            return DocumentExportSerializer
        elif self.action == 'bulk_operations':
            return BulkDocumentOperationSerializer
        return QuoteSerializer
    
    def get_queryset(self):
        """Queryset optimisé avec filtres avancés et correction schéma"""
        # WORKAROUND: Forcer le bon schéma avant toute requête ORM
        if hasattr(self.request, 'schema_name'):
            from django.db import connection
            with connection.cursor() as cursor:
                cursor.execute(f"SET search_path TO {self.request.schema_name}, public")
        
        queryset = super().get_queryset()
        return self.apply_advanced_filters(queryset)
    
    def list(self, request, *args, **kwargs):
        """Liste des devis avec optimisations de performance"""
        from .utils_optimized import OptimizedDocumentUtils
        
        # Utiliser le queryset optimisé pour la liste
        self.queryset = OptimizedDocumentUtils.optimize_queryset_for_list(
            self.get_queryset(), include_items_count=True
        )
        
        # Utiliser la méthode parent optimisée
        response = super().list(request, *args, **kwargs)
        
        # Ajouter des métadonnées de performance
        response['X-Optimized'] = 'true'
        response['X-Query-Type'] = 'list-optimized'
        
        return response
    
    @action(detail=False, methods=['get'])
    def stats(self, request):
        """Statistiques globales des devis avec cache Redis"""
        # Désactiver temporairement le cache Redis
        # cached_response = self.get_cached_response('stats')
        # if cached_response:
        #     return cached_response
        
        # Calculer les stats avec une seule requête optimisée
        queryset = self.get_optimized_queryset('stats')
        
        # Stats de base
        base_stats = self.calculate_base_stats(queryset)
        
        # Stats spécifiques aux devis
        quote_specific = queryset.aggregate(
            # Comptes pour le taux d'acceptation
            accepted_count=Count('id', filter=Q(status=QuoteStatus.ACCEPTED)),
            total_count=Count('id'),
            # Montant moyen par statut
            avg_accepted_amount=Avg('total_ttc', filter=Q(status=QuoteStatus.ACCEPTED)) or Decimal('0'),
            # Délai moyen de validation
            avg_validation_days=Avg(
                F('updated_at') - F('created_at'),
                filter=Q(status__in=[QuoteStatus.ACCEPTED, QuoteStatus.REJECTED])
            )
        )
        
        # Calculer le taux d'acceptation en évitant la division par zéro
        total_quotes = quote_specific.get('total_count', 0)
        accepted_quotes = quote_specific.get('accepted_count', 0)
        acceptance_rate = (accepted_quotes * 100.0 / total_quotes) if total_quotes > 0 else 0.0
        
        # Ajouter le taux d'acceptation aux statistiques
        quote_specific['acceptance_rate'] = acceptance_rate
        
        stats_data = {**base_stats, **quote_specific}
        
        # Mettre en cache et retourner
        # return self.set_cached_response('stats', stats_data)
        return Response(stats_data)
    
    @action(detail=True, methods=['post'], serializer_class='DocumentSendSerializer')
    def send(self, request, pk=None):
        """Envoyer un devis par email"""
        from .serializers import DocumentSendSerializer
        
        quote = self.get_object()
        serializer = DocumentSendSerializer(data=request.data)
        
        if serializer.is_valid():
            return self.perform_document_action(
                quote, 'send', serializer.validated_data.get('message')
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
            # Créer une copie du devis avec numérotation correcte
            new_quote = Quote.objects.create(
                client_name=original_quote.client_name,
                client_address=original_quote.client_address,
                project_name=original_quote.project_name,
                project_address=original_quote.project_address,
                project_reference=original_quote.project_reference,
                opportunity_id=original_quote.opportunity_id,
                notes=original_quote.notes,
                terms_and_conditions=original_quote.terms_and_conditions,
                validity_period=original_quote.validity_period,
                margin=original_quote.margin,
                created_by=self.get_user_info()
            )
            
            # 🔧 CORRECTION: Définir tenant_id pour la numérotation séquentielle
            tenant_id = getattr(request, 'tenant_id', None)
            if tenant_id:
                new_quote._tenant_id = tenant_id
                # Forcer la regénération du numéro avec le bon tenant_id
                new_quote.number = ""  # Réinitialiser pour déclencher la génération
                new_quote.save()  # Déclenche la génération automatique avec tenant_id
            
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
            
            # Mettre à jour les totaux avec le tenant_id
            tenant_id = getattr(request, 'tenant_id', None)
            new_quote.update_totals(tenant_id=tenant_id)
            self._invalidate_cache()
            
            serializer = QuoteDetailSerializer(new_quote)
            return Response(serializer.data, status=status.HTTP_201_CREATED)
    
    @action(detail=True, methods=['post'])
    def convert_to_invoice(self, request, pk=None):
        """Convertir un devis en facture - Pattern Unit of Work avec gestion de session"""
        tenant_id = getattr(request, 'tenant_id', None)
        
        # Valider les données d'entrée
        required_fields = ['issueDate', 'dueDate', 'paymentTerms']
        data = request.data
        
        for field in required_fields:
            if field not in data:
                return Response(
                    {'error': f'Le champ {field} est requis'},
                    status=status.HTTP_400_BAD_REQUEST
                )
        
        try:
            # Pattern Unit of Work : Toutes les opérations dans une seule transaction atomique
            # avec gestion explicite des sessions et rechargement des objets
            with transaction.atomic():
                # 1. Récupérer le quote avec une requête fraîche pour éviter les problèmes de session
                quote = Quote.objects.select_related().prefetch_related('items').get(pk=pk)
                
                # 2. Convertir les dates
                from datetime import datetime
                try:
                    issue_date = datetime.strptime(data['issueDate'], '%Y-%m-%d').date()
                    due_date = datetime.strptime(data['dueDate'], '%Y-%m-%d').date()
                except ValueError as e:
                    return Response(
                        {'error': f'Format de date invalide: {str(e)}'},
                        status=status.HTTP_400_BAD_REQUEST
                    )
                
                # 3. Créer la facture avec un contexte de session propre
                invoice_data = {
                    'client_name': quote.client_name,
                    'client_address': quote.client_address,
                    'project_name': quote.project_name,
                    'project_address': quote.project_address,
                    'project_reference': quote.project_reference,
                    'issue_date': issue_date,
                    'due_date': due_date,
                    'payment_terms': int(data['paymentTerms']),
                    'notes': data.get('notes', ''),
                    'terms_and_conditions': quote.terms_and_conditions,
                    'created_by': "convert_to_invoice_api",
                    'status': InvoiceStatus.DRAFT,
                    'quote_id': str(quote.id),
                    'quote_number': quote.number
                }
                
                # ✅ Inclure le numéro si fourni par le frontend
                if 'number' in data and data['number']:
                    invoice_data['number'] = data['number']
                    logger.info(f"🔢 Numéro de facture fourni lors de la conversion: {data['number']}")
                
                # Utiliser le manager pour créer avec une session propre
                invoice = Invoice.objects.create(**invoice_data)
                
                # 4. Copier les éléments avec gestion des relations
                if data.get('copyItems', True):
                    self._copy_quote_items_to_invoice(quote, invoice)
                
                # 5. Mettre à jour le statut du quote
                self._update_quote_status(quote)
                
                # 6. Recalculer les totaux avec un contexte propre
                self._calculate_invoice_totals(invoice, tenant_id)
                
                # 7. Retourner la réponse avec une sérialisation sûre
                return self._create_conversion_response(invoice)
                
        except Quote.DoesNotExist:
            return Response(
                {'error': 'Devis introuvable'},
                status=status.HTTP_404_NOT_FOUND
            )
        except Exception as e:
            import traceback
            return Response(
                {
                    'error': f'Erreur lors de la conversion: {str(e)}',
                    'traceback': traceback.format_exc()
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    def _copy_quote_items_to_invoice(self, quote, invoice):
        """Copie les items du quote vers la facture avec gestion des relations parent/enfant"""
        # Récupérer tous les items avec leurs relations
        quote_items = list(quote.items.all().order_by('position'))
        item_mapping = {}
        tenant_id = getattr(self.request, 'tenant_id', None)
        
        # Premier passage : créer tous les items sans parent et recalculer les totaux
        for item in quote_items:
            new_item = InvoiceItem.objects.create(
                invoice=invoice,
                type=item.type,
                parent=None,
                position=item.position,
                reference=item.reference,
                designation=item.designation,
                description=item.description,
                unit=item.unit,
                quantity=item.quantity,
                unit_price=item.unit_price,
                discount=item.discount,
                vat_rate=item.vat_rate,
                work_id=item.work_id
            )
            
            # Recalculer les totaux pour ce nouvel item
            if new_item.type not in ["chapter", "section"]:
                new_item._calculate_item_totals(tenant_id)
                new_item.save(update_fields=['total_ht', 'total_ttc'], skip_document_update=True)
            
            item_mapping[item.id] = new_item
        
        # Deuxième passage : établir les relations parent/enfant
        for item in quote_items:
            if item.parent_id:
                new_item = item_mapping[item.id]
                parent_item = item_mapping.get(item.parent_id)
                if parent_item:
                    new_item.parent = parent_item
                    new_item.save(update_fields=['parent'])
    
    def _update_quote_status(self, quote):
        """Met à jour le statut du quote de manière atomique"""
        if quote.status in [QuoteStatus.DRAFT, QuoteStatus.SENT]:
            Quote.objects.filter(id=quote.id).update(status=QuoteStatus.ACCEPTED)
    
    def _calculate_invoice_totals(self, invoice, tenant_id):
        """Recalcule les totaux de la facture dans un contexte de session propre"""
        # Recharger l'invoice avec toutes ses relations
        invoice = Invoice.objects.prefetch_related('items').get(id=invoice.id)
        invoice.update_totals(tenant_id=tenant_id)
    
    def _create_conversion_response(self, invoice):
        """Crée la réponse de conversion avec une sérialisation sûre"""
        # Recharger une dernière fois pour s'assurer de la cohérence
        invoice = Invoice.objects.select_related().prefetch_related('items').get(id=invoice.id)
        
        # Utiliser un serializer simple pour éviter les problèmes de sérialisation complexe
        response_data = {
            'id': str(invoice.id),
            'number': invoice.number,
            'client_name': invoice.client_name,
            'project_name': invoice.project_name,
            'total_ht': str(invoice.total_ht),
            'total_vat': str(invoice.total_vat),
            'total_ttc': str(invoice.total_ttc),
            'status': invoice.status,
            'issue_date': invoice.issue_date.isoformat(),
            'due_date': invoice.due_date.isoformat(),
        }
        
        return Response({
            'message': 'Devis converti en facture avec succès',
            'invoice': response_data
        }, status=status.HTTP_201_CREATED)
    
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
    
    @action(detail=False, methods=['get'])
    def next_number(self, request):
        """Génère un aperçu du prochain numéro de devis pour ce tenant"""
        
        # Récupérer le tenant_id depuis le middleware
        tenant_id = getattr(request, 'tenant_id', None)
        
        if not tenant_id:
            return Response({
                'error': 'Tenant ID requis pour générer le numéro de devis'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            # Utiliser le service DocumentNumberService pour générer le prochain numéro
            next_number = DocumentNumberService.get_next_number_preview(tenant_id, 'quote')
            
            return Response({
                'number': next_number,
                'tenant_id': tenant_id,
                'document_type': 'quote'
            })
            
        except Exception as e:
            # En cas d'erreur, retourner un numéro de fallback
            from datetime import datetime
            fallback_number = f"DEV-{datetime.now().year}-{str(int(datetime.now().timestamp()))[-3:]}"
            
            return Response({
                'number': fallback_number,
                'tenant_id': tenant_id,
                'document_type': 'quote',
                'is_fallback': True,
                'error': str(e)
            })
    
    @action(detail=False, methods=['get'])
    def debug_numbering(self, request):
        """Endpoint de diagnostic pour la numérotation"""
        
        tenant_id = getattr(request, 'tenant_id', None)
        if not tenant_id:
            return Response({'error': 'Tenant ID requis'}, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            from .services.tenant_client import TenantConfigClient
            from .services.number_service import DocumentNumberService
            import datetime
            
            # 1. Récupérer la configuration brute
            config = TenantConfigClient.get_cached_numbering(tenant_id, 'quote')
            
            # 2. Tester la génération
            now = datetime.datetime.now()
            
            # 3. Appeler la méthode de génération directement
            if config and config.get('custom_format'):
                test_result = DocumentNumberService._generate_custom_format(config, now)
            else:
                test_result = "Pas de custom_format dans config"
            
            # 4. Générer via l'API normale
            normal_result = DocumentNumberService.get_next_number_preview(tenant_id, 'quote')
            
            return Response({
                'tenant_id': tenant_id,
                'config_complete': config,
                'custom_format': config.get('custom_format') if config else None,
                'next_number': config.get('next_number') if config else None,
                'padding': config.get('padding') if config else None,
                'test_generation_direct': test_result,
                'normal_generation_api': normal_result,
                'timestamp': now.isoformat(),
                'debug_info': {
                    'has_config': config is not None,
                    'is_fallback': config.get('_is_fallback', False) if config else True,
                    'config_keys': list(config.keys()) if config else []
                }
            })
            
        except Exception as e:
            import traceback
            return Response({
                'tenant_id': tenant_id,
                'error': str(e),
                'traceback': traceback.format_exc()
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    
    def perform_create(self, serializer):
        """Override pour passer le tenant_id lors de la création"""
        # Récupérer le tenant_id depuis la requête
        tenant_id = getattr(self.request, 'tenant_id', None)
        
        if not tenant_id:
            # Tenter de récupérer depuis le header X-Tenant-ID
            tenant_id = self.request.META.get('HTTP_X_TENANT_ID')
        
        # Sauvegarder avec le tenant_id pour générer le bon numéro
        instance = serializer.save(created_by=self.get_user_info())
        
        # Passer le tenant_id au modèle pour la génération du numéro
        if tenant_id:
            instance._tenant_id = tenant_id
            # Si le numéro n'a pas été généré correctement, le regénérer
            if not instance.number or (instance.number.startswith("DEV-") and len(instance.number.split('-')) == 3 and instance.number.split('-')[2].isdigit() and len(instance.number.split('-')[2]) >= 6):
                from .services.number_service import DocumentNumberService
                try:
                    instance.number = DocumentNumberService.generate_quote_number(tenant_id)
                    instance.save(update_fields=['number'])
                except Exception as e:
                    logger.error(f"Erreur génération numéro pour tenant {tenant_id}: {e}")
        
        # Mettre à jour les totaux avec le tenant_id
        instance.update_totals(tenant_id=tenant_id)
        
        # Invalider le cache
        self._invalidate_cache()


class QuoteItemViewSet(viewsets.ModelViewSet, AuditMixin):
    """ViewSet pour les éléments de devis"""
    
    queryset = QuoteItem.objects.all()
    serializer_class = QuoteItemSerializer
    permission_classes = [AllowAny]  # La sécurité est gérée par l'API Gateway et le middleware tenant
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
    permission_classes = [AllowAny]  # La sécurité est gérée par l'API Gateway et le middleware tenant
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['status', 'quote_id', 'is_credit_note', 'issue_date', 'due_date']
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
        queryset = super().get_queryset()
        return self.apply_advanced_filters(queryset)
    
    def list(self, request, *args, **kwargs):
        """Liste des factures avec optimisations de performance"""
        from .utils_optimized import OptimizedDocumentUtils
        
        # Utiliser le queryset optimisé pour la liste
        self.queryset = OptimizedDocumentUtils.optimize_queryset_for_list(
            self.get_queryset(), include_items_count=True
        )
        
        # Utiliser la méthode parent optimisée
        response = super().list(request, *args, **kwargs)
        
        # Ajouter des métadonnées de performance
        response['X-Optimized'] = 'true'
        response['X-Query-Type'] = 'invoice-list-optimized'
        
        return response
    
    @action(detail=False, methods=['get'])
    def stats(self, request):
        """Statistiques globales des factures avec cache Redis"""
        # Désactiver temporairement le cache Redis
        # cached_response = self.get_cached_response('stats')
        # if cached_response:
        #     return cached_response
        
        # Calculer les stats avec une seule requête optimisée
        queryset = self.get_optimized_queryset('stats')
        
        # Stats de base
        base_stats = self.calculate_base_stats(queryset)
        
        # Stats spécifiques aux factures
        logger.info("🔍 Calcul des statistiques de factures...")
        logger.info(f"📊 Nombre total de factures dans queryset: {queryset.count()}")
        
        # Mettre à jour automatiquement les statuts en retard basés sur les dates d'échéance
        logger.info("📅 Mise à jour automatique des statuts en retard...")
        from .models import Invoice
        updated_count = Invoice.update_all_overdue_statuses()
        logger.info(f"📅 {updated_count} factures mises à jour")
        
        # Debug: voir les montants paid_amount individuels
        paid_amounts = list(queryset.values('id', 'number', 'paid_amount', 'status', 'due_date'))
        logger.info(f"💰 Factures avec statuts et dates: {paid_amounts}")
        
        # Recalculer les montants payés pour toutes les factures pour corriger les incohérences
        logger.info("🔧 Vérification et correction des montants payés...")
        for invoice in queryset:
            invoice.recalculate_paid_amount()
        
        # Recalculer le queryset pour inclure les mises à jour de statut
        queryset = self.get_optimized_queryset('stats')
        
        invoice_specific = queryset.aggregate(
            # Montants de paiement
            total_paid=Sum('paid_amount') or Decimal('0'),
            total_outstanding=Sum('remaining_amount') or Decimal('0'),
            overdue_amount=Sum(
                'remaining_amount',
                filter=Q(status=InvoiceStatus.OVERDUE)
            ) or Decimal('0'),
            # Alternative: montant total des factures en retard
            overdue_total_amount=Sum(
                'total_ttc',
                filter=Q(status=InvoiceStatus.OVERDUE)
            ) or Decimal('0'),
            
            # Délai moyen de paiement
            avg_payment_delay=Avg(
                F('payments__date') - F('issue_date'),
                filter=Q(status=InvoiceStatus.PAID)
            ),
            
            # Comptes pour le taux de paiement
            paid_count=Count('id', filter=Q(status=InvoiceStatus.PAID)),
            total_count=Count('id')
        )
        
        logger.info(f"💰 Total paid calculé: {invoice_specific.get('total_paid', 0)}")
        logger.info(f"📊 Nombre de factures payées: {invoice_specific.get('paid_count', 0)}")
        logger.info(f"⚠️ Montant restant dû des factures en retard: {invoice_specific.get('overdue_amount', 0)}")
        logger.info(f"⚠️ Montant total des factures en retard: {invoice_specific.get('overdue_total_amount', 0)}")
        
        # Compter manuellement les factures en retard pour vérification
        from django.utils import timezone
        today = timezone.now().date()
        manual_overdue_count = queryset.filter(
            due_date__lt=today,
            status__in=[InvoiceStatus.SENT, InvoiceStatus.PARTIALLY_PAID, InvoiceStatus.OVERDUE]
        ).count()
        auto_overdue_count = queryset.filter(status=InvoiceStatus.OVERDUE).count()
        logger.info(f"📅 Factures en retard par date: {manual_overdue_count}, par statut: {auto_overdue_count}")
        
        # Calculer le taux de paiement en évitant la division par zéro
        total_invoices = invoice_specific.get('total_count', 0)
        paid_invoices = invoice_specific.get('paid_count', 0)
        payment_rate = (paid_invoices * 100.0 / total_invoices) if total_invoices > 0 else 0.0
        
        # Ajouter le taux de paiement aux statistiques
        invoice_specific['payment_rate'] = payment_rate
        
        # Préparer les données dans le format attendu par le serializer
        stats_data = {
            # Compteurs (depuis base_stats)
            'total_invoices': base_stats.get('total', 0),
            'draft_invoices': base_stats.get('draft', 0),
            'sent_invoices': base_stats.get('sent', 0),
            'paid_invoices': base_stats.get('paid', 0),
            'overdue_invoices': base_stats.get('overdue', 0),
            'partially_paid_invoices': base_stats.get('partially_paid', 0),
            'cancelled_invoices': base_stats.get('cancelled', 0),
            'credit_note_invoices': base_stats.get('cancelled_by_credit_note', 0),
            
            # Montants (depuis base_stats et invoice_specific)
            'total_amount_ht': base_stats.get('total_amount_ht', Decimal('0')),
            'total_amount_ttc': base_stats.get('total_amount_ttc', Decimal('0')),
            'total_paid': invoice_specific.get('total_paid', Decimal('0')),
            'total_outstanding': invoice_specific.get('total_outstanding', Decimal('0')),
            'overdue_amount': invoice_specific.get('overdue_amount', Decimal('0')),
            
            # Métriques calculées
            'payment_rate': invoice_specific.get('payment_rate', 0.0),
            'average_amount': base_stats.get('average_amount', Decimal('0')),
            'average_payment_delay': invoice_specific.get('avg_payment_delay', 0.0) or 0.0,
        }
        
        # Sérialiser les données avec le serializer approprié
        serializer = InvoiceStatsSerializer(stats_data)
        
        # Mettre en cache et retourner
        # return self.set_cached_response('stats', serializer.data)
        return Response(serializer.data)
    
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
    
    @action(detail=True, methods=['post'], serializer_class='DocumentSendSerializer')
    def send(self, request, pk=None):
        """Envoyer une facture par email"""
        from .serializers import DocumentSendSerializer
        
        invoice = self.get_object()
        serializer = DocumentSendSerializer(data=request.data)
        
        if serializer.is_valid():
            return self.perform_document_action(
                invoice, 'send', serializer.validated_data.get('message')
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
            
            # Recharger la facture pour avoir les données à jour
            invoice.refresh_from_db()
            
            # Retourner la structure attendue par le frontend
            payment_data = PaymentSerializer(payment).data
            invoice_data = InvoiceDetailSerializer(invoice).data
            
            logger.info(f"💳 Paiement enregistré avec succès pour facture {invoice.number}")
            logger.info(f"💰 Nouveau montant payé: {invoice.paid_amount}")
            logger.info(f"📊 Nouveau statut: {invoice.status}")
            
            return Response({
                'payment': payment_data,
                'invoice': invoice_data
            })
        
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
    @action(detail=True, methods=['post'])
    def credit_note_preview(self, request, pk=None):
        """Aperçu d'un avoir (simulation sans création)"""
        invoice = self.get_object()
        data = request.data
        
        try:
            is_full = data.get('is_full', True)
            selected_items = data.get('selected_items', [])
            
            # Calculer les totaux de l'avoir en simulation
            if is_full:
                # Avoir complet
                totalHT = float(invoice.total_ht or 0)
                totalVAT = float(invoice.total_vat or 0)
                totalTTC = float(invoice.total_ttc or 0)
                impact = f"Avoir complet de {totalTTC} MAD"
            else:
                # Avoir partiel basé sur les items sélectionnés
                totalHT = 0
                totalVAT = 0
                totalTTC = 0
                
                for item in invoice.items.filter(id__in=selected_items):
                    if item.type not in ["chapter", "section"]:
                        item_ht = float(item.total_ht or 0)
                        totalHT += item_ht
                        
                        # Calculer la TVA de l'item
                        try:
                            vat_rate = float(item.vat_rate or 0) / 100
                            item_vat = item_ht * vat_rate
                            totalVAT += item_vat
                        except (ValueError, TypeError):
                            pass
                
                totalTTC = totalHT + totalVAT
                impact = f"Avoir partiel de {totalTTC} MAD ({len(selected_items)} items)"
            
            # Calculer l'impact sur la facture
            new_remaining_amount = max(0, float(invoice.remaining_amount or 0) - totalTTC)
            
            # Préparer les détails des items (pour avoir partiel)
            selected_items_details = []
            if not is_full and selected_items:
                for item in invoice.items.filter(id__in=selected_items):
                    if item.type not in ["chapter", "section"]:
                        selected_items_details.append({
                            'id': str(item.id),
                            'designation': item.designation,
                            'quantity': float(item.quantity or 0),
                            'unit_price': float(item.unit_price or 0),
                            'total_ht': float(item.total_ht or 0),
                            'vat_rate': float(item.vat_rate or 0),
                            'total_ttc': float(item.total_ttc or 0)
                        })
            
            return Response({
                'totalHT': totalHT,
                'totalVAT': totalVAT,
                'totalTTC': totalTTC,
                'impact': impact,
                'selected_items_details': selected_items_details,
                'new_remaining_amount': new_remaining_amount,
                'original_remaining_amount': float(invoice.remaining_amount or 0),
                'items_count': len(selected_items) if not is_full else invoice.items.count()
            })
            
        except Exception as e:
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f"Erreur calcul aperçu avoir: {e}")
            return Response({
                'error': 'Erreur lors du calcul de l\'aperçu'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    
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
    permission_classes = [AllowAny]  # La sécurité est gérée par l'API Gateway et le middleware tenant
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
    permission_classes = [AllowAny]  # La sécurité est gérée par l'API Gateway et le middleware tenant
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
    """ViewSet tenant-aware pour les taux de TVA"""
    
    permission_classes = [AllowAny]  # La sécurité est gérée par l'API Gateway et le middleware tenant
    serializer_class = VATRateSerializer
    
    def list(self, request, *args, **kwargs):
        """Liste les taux de TVA tenant-specific"""
        
        # Récupérer le tenant_id depuis le middleware
        tenant_id = getattr(request, 'tenant_id', None)
        
        if not tenant_id:
            return Response({
                'error': 'Tenant ID requis pour récupérer les taux de TVA'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            # Utiliser le service pour récupérer les taux tenant-specific
            vat_rates = vat_rate_service.get_active_vat_rates(tenant_id)
            return Response(vat_rates)
        except Exception as e:
            return Response({
                'error': f'Erreur lors de la récupération des taux de TVA: {str(e)}'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    
    @action(detail=False, methods=['get'])
    def default(self, request):
        """Récupère le taux de TVA par défaut pour ce tenant"""
        
        tenant_id = getattr(request, 'tenant_id', None)
        
        if not tenant_id:
            return Response({
                'error': 'Tenant ID requis'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            default_rate = vat_rate_service.get_default_vat_rate(tenant_id)
            if default_rate:
                return Response(default_rate)
            else:
                return Response({
                    'error': 'Aucun taux de TVA par défaut trouvé'
                }, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            return Response({
                'error': f'Erreur: {str(e)}'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class QuoteStatusViewSet(viewsets.ReadOnlyModelViewSet):
    """ViewSet en lecture seule pour les statuts de devis"""
    
    permission_classes = [AllowAny]  # La sécurité est gérée par l'API Gateway et le middleware tenant
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
    
    permission_classes = [AllowAny]  # La sécurité est gérée par l'API Gateway et le middleware tenant
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
    
    permission_classes = [AllowAny]  # La sécurité est gérée par l'API Gateway et le middleware tenant
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


class PaymentTermViewSet(viewsets.ViewSet):
    """
    ViewSet pour les conditions de paiement
    """
    permission_classes = [permissions.AllowAny]
    
    def list(self, request):
        """
        Liste les conditions de paiement disponibles pour le tenant
        """
        tenant_id = request.headers.get('X-Tenant-ID')
        if not tenant_id:
            return Response({'error': 'X-Tenant-ID header is required'}, status=400)
        
        payment_terms = PaymentTermService.get_active_payment_terms(tenant_id)
        return Response(payment_terms)
    
    @action(detail=False, methods=['get'])
    def default(self, request):
        """
        Récupère la condition de paiement par défaut
        """
        tenant_id = request.headers.get('X-Tenant-ID')
        if not tenant_id:
            return Response({'error': 'X-Tenant-ID header is required'}, status=400)
        
        default_term = PaymentTermService.get_default_payment_term(tenant_id)
        return Response(default_term)
    
    @action(detail=True, methods=['get'])
    def by_id(self, request, pk=None):
        """
        Récupère une condition de paiement par son ID
        """
        tenant_id = request.headers.get('X-Tenant-ID')
        if not tenant_id:
            return Response({'error': 'X-Tenant-ID header is required'}, status=400)
        
        payment_term = PaymentTermService.get_payment_term_by_id(tenant_id, pk)
        if not payment_term:
            return Response({'error': f'Payment term with ID {pk} not found'}, status=404)
        
        return Response(payment_term)



@api_view(['GET'])
def health_check(request):
    """
    Endpoint de vérification de santé du service
    """
    try:
        # Vérifier la connexion à la base de données
        from django.db import connection
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
        
        # Vérifier les services externes (optionnel)
        tenant_id = getattr(request, 'tenant_id', 'test')
        
        return Response({
            'status': 'healthy',
            'service': 'document-service',
            'timestamp': '2024-01-01T00:00:00Z',
            'database': 'connected',
            'tenant_context': tenant_id is not None,
            'version': '1.0.0'
        }, status=status.HTTP_200_OK)
        
    except Exception as e:
        return Response({
            'status': 'unhealthy',
            'service': 'document-service',
            'error': str(e),
            'timestamp': '2024-01-01T00:00:00Z'
        }, status=status.HTTP_503_SERVICE_UNAVAILABLE)


@api_view(['GET'])
def performance_diagnostics(request):
    """
    Endpoint de diagnostics de performance - VERSION SIMPLIFIÉE
    """
    from .services.cache_service import TenantConfigCacheService
    from .services.tenant_client import TenantConfigClient
    
    tenant_id = getattr(request, 'tenant_id', None)
    if not tenant_id:
        return Response(
            {'error': 'Tenant ID requis pour les diagnostics'},
            status=status.HTTP_400_BAD_REQUEST
        )
    
    try:
        # Diagnostics simplifiés
        diagnostics = {
            'tenant_id': tenant_id,
            'cache_statistics': TenantConfigCacheService.get_cache_statistics(),
            'cache_health': TenantConfigCacheService.health_check(),
            'tenant_service_connection': TenantConfigClient.test_connection(),
            'timestamp': timezone.now().isoformat()
        }
        
        return Response(diagnostics, status=status.HTTP_200_OK)
        
    except Exception as e:
        return Response({
            'error': f'Erreur lors des diagnostics: {str(e)}',
            'tenant_id': tenant_id
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['POST'])
def test_document_creation_performance(request):
    """
    Endpoint de test de performance de création de documents - VERSION SIMPLIFIÉE
    """
    from .utils_optimized import OptimizedDocumentUtils
    from .models import Quote
    import time
    
    tenant_id = getattr(request, 'tenant_id', None)
    if not tenant_id:
        return Response(
            {'error': 'Tenant ID requis pour les tests de performance'},
            status=status.HTTP_400_BAD_REQUEST
        )
    
    try:
        items_count = request.data.get('items_count', 2)
        
        # Test simple de performance
        start_time = time.time()
        
        # Créer un devis de test
        quote = Quote.objects.create(
            number=f"TEST-PERF-{int(time.time())}",
            client_name="Client Test Performance",
            project_name="Test Performance",
            created_by="performance-test"
        )
        
        # Créer des items de test
        items_data = [
            {
                'designation': f'Item test {i}',
                'quantity': 1,
                'unit_price': 100,
                'vat_rate': '20',
                'type': 'material'
            }
            for i in range(items_count)
        ]
        
        # Test de création batch
        OptimizedDocumentUtils.bulk_create_quote_items(quote, items_data, tenant_id)
        
        end_time = time.time()
        duration = end_time - start_time
        
        # Nettoyer le test
        quote.delete()
        
        performance_test = {
            'tenant_id': tenant_id,
            'items_count': items_count,
            'duration_seconds': round(duration, 3),
            'items_per_second': round(items_count / duration, 2) if duration > 0 else 0,
            'status': 'success'
        }
        
        return Response(performance_test, status=status.HTTP_200_OK)
        
    except Exception as e:
        return Response({
            'error': f'Erreur lors du test de performance: {str(e)}',
            'tenant_id': tenant_id
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['POST'])
def warm_up_cache(request):
    """
    Endpoint pour préchauffer le cache d'un tenant - VERSION SIMPLIFIÉE
    """
    from .services.cache_service import TenantConfigCacheService
    
    tenant_id = getattr(request, 'tenant_id', None)
    if not tenant_id:
        return Response(
            {'error': 'Tenant ID requis pour préchauffer le cache'},
            status=status.HTTP_400_BAD_REQUEST
        )
    
    try:
        success = TenantConfigCacheService.warm_up_cache(tenant_id)
        
        return Response({
            'tenant_id': tenant_id,
            'cache_warmed_up': success,
            'message': 'Cache préchauffé avec succès' if success else 'Échec du préchauffage'
        }, status=status.HTTP_200_OK if success else status.HTTP_500_INTERNAL_SERVER_ERROR)
        
    except Exception as e:
        return Response({
            'error': f'Erreur lors du préchauffage: {str(e)}',
            'tenant_id': tenant_id
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


# =============================================================================
# ENDPOINTS POUR LA GESTION DES PROJETS
# =============================================================================

@api_view(['GET'])
def next_project_reference(request):
    """
    Génère une référence unique pour un projet (tenant-aware)
    """
    # Récupérer le tenant_id depuis le middleware
    tenant_id = getattr(request, 'tenant_id', None)
    
    if not tenant_id:
        return Response({
            'error': 'Tenant ID requis pour générer la référence projet'
        }, status=status.HTTP_400_BAD_REQUEST)
    
    try:
        # Utiliser le service DocumentNumberService pour générer la référence
        project_reference = DocumentNumberService.get_next_number_preview(tenant_id, 'project')
        
        return Response({
            'reference': project_reference,
            'tenant_id': tenant_id,
            'document_type': 'project'
        })
        
    except Exception as e:
        # En cas d'erreur, retourner une référence de fallback
        from datetime import datetime
        year = datetime.now().year
        fallback_ref = f"PROJ-{year}-TEMP"
        
        return Response({
            'reference': fallback_ref,
            'tenant_id': tenant_id,
            'document_type': 'project',
            'warning': f'Référence temporaire générée suite à une erreur: {str(e)}'
        }, status=status.HTTP_200_OK)
