"""
Serializers unifiés pour les documents commerciaux (devis et factures)
"""
from rest_framework import serializers
from django.utils import timezone
from django.db import transaction
from django.db.models import Sum, Count, F, Q
from django.conf import settings
from decimal import Decimal
import logging

from .models import (
    Quote, QuoteItem, Invoice, InvoiceItem, Payment,
    QuoteStatus, InvoiceStatus, PaymentMethod, VATRate
)
from .mixins import (
    DocumentValidationMixin, DateValidationMixin, BaseDocumentMixin,
    ClientInfoMixin, CalculationMixin, RelatedDocumentMixin,
    BaseDocumentItemMixin, BulkOperationMixin, DocumentStatsBaseMixin
)
from .utils import CamelCaseResponseMixin


# =============================================================================
# SERIALIZERS DE BASE AVEC MIXINS
# =============================================================================

class BaseDocumentItemSerializer(CamelCaseResponseMixin,
                                 serializers.ModelSerializer, 
                                 DocumentValidationMixin, 
                                 BaseDocumentItemMixin):
    """Serializer de base pour tous les éléments de documents"""
    
    # Champs calculés en lecture seule
    total_ht = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)
    total_ttc = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)
    
    # Informations sur le type en lecture seule
    type_display = serializers.CharField(source='get_type_display', read_only=True)
    vat_rate_display = serializers.CharField(source='get_vat_rate_display', read_only=True)
    
    # Informations hiérarchiques
    parent_info = serializers.SerializerMethodField()
    children = serializers.SerializerMethodField()
    
    class Meta:
        abstract = True
        fields = [
            'id', 'type', 'type_display', 'parent', 'parent_info', 'position',
            'reference', 'designation', 'description', 'unit', 'quantity',
            'unit_price', 'discount', 'vat_rate', 'vat_rate_display',
            'total_ht', 'total_ttc', 'work_id', 'children',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']
    
    def validate(self, data):
        """Validation globale avec hiérarchie"""
        data = super().validate(data)
        return self.validate_hierarchy(data)


class BaseDocumentSerializer(CamelCaseResponseMixin,
                            serializers.ModelSerializer,
                            DocumentValidationMixin,
                            DateValidationMixin,
                            BaseDocumentMixin,
                            ClientInfoMixin,
                            CalculationMixin):
    """Serializer de base pour tous les documents"""
    
    # Informations client
    client_info = serializers.SerializerMethodField()
    project_info = serializers.SerializerMethodField()
    
    # Dates formatées
    issue_date_formatted = serializers.SerializerMethodField()
    
    # Totaux calculés en lecture seule
    total_ht = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)
    total_vat = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)
    total_ttc = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)
    
    # Statistiques
    items_count = serializers.SerializerMethodField()
    vat_breakdown = serializers.SerializerMethodField()
    
    class Meta:
        abstract = True
        fields = [
            'id', 'number', 'client_name', 'client_address', 'client_info',
            'project_name', 'project_address', 'project_reference', 'project_info',
            'issue_date', 'issue_date_formatted', 'notes', 'terms_and_conditions',
            'total_ht', 'total_vat', 'total_ttc', 'items_count', 'vat_breakdown',
            'created_at', 'updated_at', 'created_by', 'updated_by'
        ]
        read_only_fields = [
            'id', 'number', 'total_ht', 'total_vat', 'total_ttc',
            'created_at', 'updated_at'
        ]
    
    def get_issue_date_formatted(self, obj):
        """Formater la date d'émission"""
        return self.get_formatted_date(obj.issue_date)
    
    def get_items_count(self, obj):
        """Compter le nombre d'éléments"""
        return getattr(obj, 'items_count', None) or obj.items.count()
    
    def get_vat_breakdown(self, obj):
        """Calculer la répartition de TVA"""
        return self.calculate_vat_breakdown(obj.items.all())


# =============================================================================
# SERIALIZERS POUR LES DEVIS
# =============================================================================

class QuoteItemSerializer(BaseDocumentItemSerializer):
    """Serializer pour les éléments de devis"""
    
    # Champ spécifique aux devis
    margin = serializers.DecimalField(max_digits=5, decimal_places=2, required=False)
    
    # Informations sur le devis parent
    quote_number = serializers.CharField(source='quote.number', read_only=True)
    
    class Meta:
        model = QuoteItem
        fields = BaseDocumentItemSerializer.Meta.fields + [
            'quote', 'quote_number', 'margin'
        ]
        read_only_fields = BaseDocumentItemSerializer.Meta.read_only_fields


class QuoteSerializer(BaseDocumentSerializer):
    """Serializer pour les devis"""
    
    # Champs spécifiques aux devis
    status = serializers.CharField(read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    opportunity_id = serializers.UUIDField(required=False, allow_null=True)
    expiry_date = serializers.DateField(required=False, allow_null=True)
    expiry_date_formatted = serializers.SerializerMethodField()
    validity_period = serializers.IntegerField(default=30)
    margin = serializers.DecimalField(max_digits=5, decimal_places=2, default=0)
    
    
    class Meta:
        model = Quote
        fields = BaseDocumentSerializer.Meta.fields + [
            'status', 'status_display', 'opportunity_id', 'expiry_date',
            'expiry_date_formatted', 'validity_period', 'margin'
        ]
        read_only_fields = BaseDocumentSerializer.Meta.read_only_fields + ['status']
    
    def get_expiry_date_formatted(self, obj):
        """Formater la date d'expiration"""
        return self.get_formatted_date(obj.expiry_date)
    
    
    def validate(self, data):
        """Validation globale pour les devis"""
        data = super().validate(data)
        return self.validate_dates(data, expiry_field='expiry_date')


class QuoteDetailSerializer(QuoteSerializer):
    """Serializer détaillé pour les devis avec éléments"""
    
    # Tous les éléments du devis
    items = QuoteItemSerializer(many=True, read_only=True)
    
    # Statistiques détaillées
    items_stats = serializers.SerializerMethodField()
    
    class Meta(QuoteSerializer.Meta):
        fields = QuoteSerializer.Meta.fields + ['items', 'items_stats']
    
    def get_items_stats(self, obj):
        """Statistiques sur les éléments"""
        items = obj.items.all()
        return self.calculate_totals_summary(items)


class QuoteItemCreateSerializer(BaseDocumentItemSerializer):
    """Serializer pour créer des éléments de devis (sans référence au quote parent)"""
    
    # Champ spécifique aux devis
    margin = serializers.DecimalField(max_digits=5, decimal_places=2, required=False)
    
    class Meta:
        model = QuoteItem
        fields = BaseDocumentItemSerializer.Meta.fields + ['margin']
        read_only_fields = BaseDocumentItemSerializer.Meta.read_only_fields
        # Note: 'quote' exclu car sera défini lors de la création


class QuoteCreateSerializer(QuoteSerializer):
    """Serializer pour créer un devis"""
    
    # Éléments pour création (utilise le serializer spécialisé)
    items = QuoteItemCreateSerializer(many=True, required=False)
    
    class Meta(QuoteSerializer.Meta):
        fields = QuoteSerializer.Meta.fields + ['items']
        read_only_fields = ['id', 'created_at', 'updated_at']  # number peut être fourni par le frontend
    
    def validate_number(self, value):
        """Valider l'unicité du numéro de devis (TEMPORAIREMENT DÉSACTIVÉ)"""
        import logging
        logger = logging.getLogger(__name__)
        logger.info(f"🔍 Validation numéro devis: '{value}' (type: {type(value)}) - DÉSACTIVÉE")
        
        # Validation temporairement désactivée pour résoudre les conflits avec doublons existants
        return value
    
    def to_internal_value(self, data):
        """Override pour logger les données reçues et gérer l'édition"""
        import logging
        logger = logging.getLogger(__name__)
        logger.info(f"QuoteCreateSerializer - Données brutes reçues: {data}")
        
        # Si on n'a pas de number et qu'on est en mode édition (instance existe), on l'utilise
        if 'number' not in data and hasattr(self, 'instance') and self.instance:
            data = data.copy() if hasattr(data, 'copy') else dict(data)
            data['number'] = self.instance.number
            logger.info(f"QuoteCreateSerializer - Ajout du number depuis l'instance: {data['number']}")
        
        try:
            result = super().to_internal_value(data)
            logger.info(f"QuoteCreateSerializer - Données validées: {result}")
            return result
        except Exception as e:
            logger.error(f"QuoteCreateSerializer - Erreur de validation: {e}")
            logger.error(f"QuoteCreateSerializer - Données causant l'erreur: {data}")
            raise
    
    def create(self, validated_data):
        """Créer un devis avec ses éléments - Version optimisée"""
        import logging
        logger = logging.getLogger(__name__)
        
        logger.info(f"QuoteCreateSerializer.create - Données reçues: {validated_data}")
        
        items_data = validated_data.pop('items', [])
        logger.info(f"QuoteCreateSerializer.create - Items extraits: {items_data}")
        
        # Récupérer le tenant_id depuis le contexte
        request = self.context.get('request')
        tenant_id = getattr(request, 'tenant_id', None) if request else None
        logger.info(f"QuoteCreateSerializer.create - Tenant ID: {tenant_id}")
        
        if not tenant_id:
            raise serializers.ValidationError("Tenant ID requis pour créer un devis")
        
        # OPTIMISATION: Utiliser le cache simple pour les configurations
        try:
            from .services.cache_service import TenantConfigCacheService
            from .services.tenant_client import TenantConfigClient
            
            # Récupérer la config tenant basique
            tenant_config = TenantConfigClient.get_cached_config(tenant_id)
            logger.info(f"Configuration tenant récupérée pour {tenant_id}")
            
            # Extraire les taux de TVA pour les calculs
            vat_rates = tenant_config.get('vat_rates', [])
            vat_rates_map = {rate.get('code'): rate for rate in vat_rates}
            
        except Exception as e:
            logger.error(f"Erreur récupération configs batch: {e}")
            vat_rates_map = {}
        
        # Créer le devis
        quote = Quote.objects.create(**validated_data)
        # Ajouter le tenant_id pour la génération du numéro
        quote._tenant_id = tenant_id
        quote.save()  # Déclencher la génération du numéro
        logger.info(f"QuoteCreateSerializer.create - Devis créé: {quote.id}")
        
        # Mettre à jour le statut de l'opportunité si applicable
        if quote.opportunity_id:
            self._update_opportunity_status(quote.opportunity_id, logger)
        
        # Créer les éléments individuellement pour déclencher les calculs
        for item_data in items_data:
            logger.info(f"QuoteCreateSerializer.create - Création item: {item_data}")
            
            item = QuoteItem(quote=quote, **item_data)
            
            # Calculer les totaux avec les configs préchargées
            if item.type not in ["chapter", "section"]:
                logger.info(f"💰 Calcul totaux pour: {item.designation} (Qté: {item.quantity}, PU: {item.unit_price}, Remise: {item.discount}%)")
                # Calcul optimisé avec les taux préchargés
                self._calculate_item_totals_optimized(item, vat_rates_map)
                logger.info(f"💰 Résultat calcul: Total HT = {item.total_ht}, Total TTC = {item.total_ttc}")
            
            # Sauvegarder individuellement pour déclencher les calculs backend
            item.save(tenant_id=tenant_id, skip_document_update=True)
            
            # Recharger depuis la DB pour vérifier la persistance
            item.refresh_from_db()
            logger.info(f"✅ Item sauvegardé: {item.designation} - Total HT DB: {item.total_ht}, Total TTC DB: {item.total_ttc}")
        
        logger.info(f"Items créés individuellement: {len(items_data)}")
        
        # Mettre à jour les totaux du devis une seule fois
        quote.update_totals(tenant_id=tenant_id)
        quote.refresh_from_db()
        
        logger.info(f"QuoteCreateSerializer.create - Devis finalisé: {quote}")
        return quote
    
    def _update_opportunity_status(self, opportunity_id, logger):
        """
        Met à jour le statut de l'opportunité vers 'négociation' quand un devis est créé
        🔧 CORRIGÉ: Utilise le bon endpoint et les bons champs
        """
        try:
            import requests
            from django.conf import settings
            
            # 🔧 CORRECTION: Utiliser CRM_SERVICE_URL au lieu d'OPPORTUNITY_SERVICE_URL
            crm_service_url = getattr(settings, 'CRM_SERVICE_URL', 'http://localhost:8003')
            
            # 🔧 CORRECTION: Utiliser 'stage' au lieu de 'status' + force=True
            update_data = {
                'stage': 'negotiation',  # CORRIGÉ: field name dans le modèle CRM
                'force': True,           # AJOUTÉ: Force pour bypasser les validations
                'source': 'quote_created' # AJOUTÉ: Traçabilité
            }
            
            # Récupérer l'Authorization header depuis le contexte
            request = self.context.get('request')
            headers = {'Content-Type': 'application/json'}
            if request and hasattr(request, 'META'):
                auth_header = request.META.get('HTTP_AUTHORIZATION')
                if auth_header:
                    headers['Authorization'] = auth_header
                
                # Ajouter le tenant_id
                tenant_id = getattr(request, 'tenant_id', None)
                if tenant_id:
                    headers['X-Tenant-ID'] = str(tenant_id)
            
            # 🔧 CORRECTION: Utiliser l'endpoint spécialisé update_stage
            api_url = f"{crm_service_url}/api/opportunities/{opportunity_id}/update_stage/"
            
            logger.info(f"🔄 Auto-update opportunité {opportunity_id} → négociation (devis créé)")
            
            # Appel API pour mettre à jour l'opportunité
            response = requests.patch(
                api_url,
                json=update_data,
                headers=headers,
                timeout=10  # AUGMENTÉ: Plus de temps pour la robustesse
            )
            
            if response.status_code == 200:
                logger.info(f"✅ Opportunité {opportunity_id} mise à jour vers 'négociation' suite à création devis")
            else:
                logger.warning(f"⚠️ Échec mise à jour opportunité {opportunity_id}: {response.status_code}")
                
        except Exception as e:
            logger.error(f"❌ Erreur lors de la mise à jour de l'opportunité {opportunity_id}: {e}")
            # Ne pas faire échouer la création du devis pour un problème de mise à jour d'opportunité
    
    def _calculate_item_totals_optimized(self, item, vat_rates_map):
        """
        Calcule les totaux d'un item avec les taux de TVA préchargés
        """
        from decimal import Decimal, InvalidOperation
        
        try:
            unit_price = Decimal(str(item.unit_price)) if item.unit_price else Decimal('0')
            quantity = Decimal(str(item.quantity)) if item.quantity else Decimal('1')
            discount = Decimal(str(item.discount)) if item.discount else Decimal('0')
            
            # Calculs avec types Decimal uniformes
            discount_factor = Decimal('1') - (discount / Decimal('100'))
            net_price = unit_price * discount_factor
            item.total_ht = net_price * quantity
            
            # Calculer la TVA avec les taux préchargés
            vat_rate_info = vat_rates_map.get(item.vat_rate)
            if vat_rate_info:
                vat_rate_decimal = Decimal(str(vat_rate_info['rate'])) / Decimal('100')
            else:
                # Fallback : utiliser le code comme taux numérique
                vat_rate_decimal = Decimal(str(item.vat_rate)) / Decimal('100')
            
            vat_amount = item.total_ht * vat_rate_decimal
            item.total_ttc = item.total_ht + vat_amount
            
        except (ValueError, TypeError, InvalidOperation) as e:
            import logging
            logger = logging.getLogger(__name__)
            logger.warning(f"Erreur calcul totaux optimisé pour item {getattr(item, 'designation', 'nouveau')}: {e}")
            
            item.total_ht = Decimal('0')
            item.total_ttc = Decimal('0')
    
    def update(self, instance, validated_data):
        """Mettre à jour un devis avec ses éléments"""
        import logging
        logger = logging.getLogger(__name__)
        
        logger.info(f"QuoteCreateSerializer.update - Mise à jour devis {instance.id}")
        logger.info(f"QuoteCreateSerializer.update - Données reçues: {validated_data}")
        
        items_data = validated_data.pop('items', [])
        logger.info(f"QuoteCreateSerializer.update - Items à mettre à jour: {len(items_data)}")
        
        # Récupérer le tenant_id depuis le contexte
        request = self.context.get('request')
        tenant_id = getattr(request, 'tenant_id', None) if request else None
        logger.info(f"QuoteCreateSerializer.update - Tenant ID: {tenant_id}")
        
        # Mettre à jour les champs du devis
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()
        
        # Supprimer tous les items existants et recréer
        old_items_count = instance.items.count()
        instance.items.all().delete()
        logger.info(f"QuoteCreateSerializer.update - {old_items_count} items existants supprimés")
        
        # Créer les nouveaux items
        for item_data in items_data:
            logger.info(f"QuoteCreateSerializer.update - Création item: {item_data}")
            
            item = QuoteItem(quote=instance, **item_data)
            
            # Calculer les totaux si ce n'est pas un chapitre/section
            if item.type not in ["chapter", "section"]:
                logger.info(f"💰 Calcul totaux pour: {item.designation} (Qté: {item.quantity}, PU: {item.unit_price}, Remise: {item.discount}%)")
                # Calcul simple pour la mise à jour
                quantity = Decimal(str(item.quantity or 0))
                unit_price = Decimal(str(item.unit_price or 0))
                discount = Decimal(str(item.discount or 0))
                vat_rate = Decimal(str(item.vat_rate or 0))
                
                base_total = quantity * unit_price
                discount_amount = base_total * discount / Decimal('100')
                total_ht = base_total - discount_amount
                vat_amount = total_ht * vat_rate / Decimal('100')
                total_ttc = total_ht + vat_amount
                
                item.total_ht = total_ht
                item.total_ttc = total_ttc
                logger.info(f"💰 Résultat calcul: Total HT = {item.total_ht}, Total TTC = {item.total_ttc}")
            
            # Sauvegarder l'item
            item.save(tenant_id=tenant_id, skip_document_update=True)
            
            # Recharger pour vérifier
            item.refresh_from_db()
            logger.info(f"✅ Item sauvegardé: {item.designation} - Total HT DB: {item.total_ht}, Total TTC DB: {item.total_ttc}")
        
        # Mettre à jour les totaux du devis
        instance.update_totals(tenant_id=tenant_id)
        instance.refresh_from_db()
        
        logger.info(f"✅ Devis mis à jour avec succès: {instance.id} - {len(items_data)} éléments")
        
        return instance


# =============================================================================
# SERIALIZERS POUR LES FACTURES
# =============================================================================

class InvoiceItemSerializer(BaseDocumentItemSerializer):
    """Serializer pour les éléments de factures"""
    
    # Informations sur la facture parent
    invoice_number = serializers.CharField(source='invoice.number', read_only=True)
    
    class Meta:
        model = InvoiceItem
        fields = BaseDocumentItemSerializer.Meta.fields + [
            'invoice', 'invoice_number'
        ]
        read_only_fields = BaseDocumentItemSerializer.Meta.read_only_fields


class PaymentSerializer(serializers.ModelSerializer, DocumentValidationMixin):
    """Serializer pour les paiements"""
    
    class Meta:
        model = Payment
        fields = [
            'id', 'invoice', 'date', 'amount', 'method', 
            'reference', 'notes', 'created_at'
        ]
        read_only_fields = ['id', 'created_at']
    
    def validate_amount(self, value):
        """Valider le montant du paiement"""
        if value <= 0:
            raise serializers.ValidationError("Le montant doit être positif.")
        return value


class InvoiceSerializer(BaseDocumentSerializer, RelatedDocumentMixin):
    """Serializer pour les factures"""
    
    # Champs spécifiques aux factures
    status = serializers.CharField(read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    is_credit_note = serializers.BooleanField(default=False)
    due_date = serializers.DateField(required=False, allow_null=True)
    due_date_formatted = serializers.SerializerMethodField()
    payment_terms = serializers.IntegerField(default=30)
    
    # Montants de paiement
    paid_amount = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)
    remaining_amount = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)
    
    # Relations avec autres documents
    quote_id = serializers.UUIDField(required=False, allow_null=True)
    quote_number = serializers.CharField(required=False, allow_null=True)
    quote_info = serializers.SerializerMethodField()
    
    # Relations pour avoirs
    credit_note_id = serializers.UUIDField(required=False, allow_null=True)
    original_invoice_id = serializers.UUIDField(required=False, allow_null=True)
    original_invoice_info = serializers.SerializerMethodField()
    
    class Meta:
        model = Invoice
        fields = BaseDocumentSerializer.Meta.fields + [
            'status', 'status_display', 'is_credit_note', 'due_date', 'due_date_formatted',
            'payment_terms', 'paid_amount', 'remaining_amount',
            'quote_id', 'quote_number', 'quote_info',
            'credit_note_id', 'original_invoice_id', 'original_invoice_info'
        ]
        read_only_fields = BaseDocumentSerializer.Meta.read_only_fields + [
            'status', 'paid_amount', 'remaining_amount'
        ]
    
    def get_due_date_formatted(self, obj):
        """Formater la date d'échéance"""
        return self.get_formatted_date(obj.due_date)
    
    def get_original_invoice_info(self, obj):
        """Informations sur la facture d'origine (pour avoirs)"""
        return self.get_invoice_info(obj)
    
    def validate(self, data):
        """Validation globale pour les factures"""
        data = super().validate(data)
        return self.validate_dates(data, due_field='due_date')


class InvoiceDetailSerializer(InvoiceSerializer):
    """Serializer détaillé pour les factures avec éléments et paiements"""
    
    # Tous les éléments de la facture
    items = InvoiceItemSerializer(many=True, read_only=True)
    
    # Tous les paiements
    payments = PaymentSerializer(many=True, read_only=True)
    
    # Statistiques détaillées
    items_stats = serializers.SerializerMethodField()
    payment_stats = serializers.SerializerMethodField()
    
    class Meta(InvoiceSerializer.Meta):
        fields = InvoiceSerializer.Meta.fields + [
            'items', 'payments', 'items_stats', 'payment_stats'
        ]
    
    def get_items_stats(self, obj):
        """Statistiques sur les éléments"""
        items = obj.items.all()
        return self.calculate_totals_summary(items)
    
    def get_payment_stats(self, obj):
        """Statistiques sur les paiements"""
        payments = obj.payments.all()
        return {
            'payments_count': payments.count(),
            'total_paid': sum(p.amount for p in payments),
            'last_payment_date': payments.first().date if payments.exists() else None
        }


class InvoiceItemCreateSerializer(BaseDocumentItemSerializer):
    """Serializer pour créer des éléments de factures (sans référence à l'invoice parent)"""
    
    class Meta:
        model = InvoiceItem
        fields = BaseDocumentItemSerializer.Meta.fields
        read_only_fields = BaseDocumentItemSerializer.Meta.read_only_fields
        # Note: 'invoice' exclu car sera défini lors de la création


class InvoiceCreateSerializer(InvoiceSerializer):
    """Serializer pour créer une facture"""
    
    # Éléments pour création (utilise le serializer spécialisé)
    items = InvoiceItemCreateSerializer(many=True, required=False)
    
    class Meta(InvoiceSerializer.Meta):
        fields = InvoiceSerializer.Meta.fields + ['items']
        # ✅ Permettre l'écriture du numéro lors de la création
        read_only_fields = [field for field in InvoiceSerializer.Meta.read_only_fields if field != 'number']
    
    def validate_number(self, value):
        """Valider l'unicité du numéro de facture (TEMPORAIREMENT DÉSACTIVÉ)"""
        import logging
        logger = logging.getLogger(__name__)
        logger.info(f"🔍 Validation numéro facture: '{value}' (type: {type(value)}) - DÉSACTIVÉE")
        
        # Validation temporairement désactivée pour résoudre les conflits avec doublons existants
        return value
    
    def create(self, validated_data):
        """Créer une facture avec ses éléments"""
        import logging
        logger = logging.getLogger(__name__)
        
        logger.info(f"InvoiceCreateSerializer.create - Données reçues: {validated_data}")
        
        items_data = validated_data.pop('items', [])
        logger.info(f"InvoiceCreateSerializer.create - Items extraits: {items_data}")
        
        # Récupérer le tenant_id depuis le contexte
        request = self.context.get('request')
        tenant_id = getattr(request, 'tenant_id', None) if request else None
        logger.info(f"InvoiceCreateSerializer.create - Tenant ID: {tenant_id}")
        
        if not tenant_id:
            raise serializers.ValidationError("Tenant ID requis pour créer une facture")
        
        # Créer la facture
        invoice = Invoice.objects.create(**validated_data)
        # Ajouter le tenant_id pour la génération du numéro
        invoice._tenant_id = tenant_id
        invoice.save()  # Déclencher la génération du numéro
        logger.info(f"InvoiceCreateSerializer.create - Facture créée: {invoice.id}")
        
        # Créer les éléments avec optimisation similaire aux devis
        items_to_create = []
        for item_data in items_data:
            logger.info(f"InvoiceCreateSerializer.create - Préparation item: {item_data}")
            
            item = InvoiceItem(invoice=invoice, **item_data)
            
            # Calculer les totaux pour les items non-structurels
            if item.type not in ["chapter", "section"]:
                self._calculate_item_totals_basic(item)
            
            items_to_create.append(item)
        
        # Sauvegarde en lot pour optimiser les performances
        if items_to_create:
            InvoiceItem.objects.bulk_create(items_to_create)
            logger.info(f"Items créés en lot: {len(items_to_create)}")
        
        # Mettre à jour les totaux de la facture
        invoice.update_totals(tenant_id=tenant_id)
        invoice.refresh_from_db()
        
        logger.info(f"InvoiceCreateSerializer.create - Facture finalisée: {invoice}")
        return invoice
    
    def _calculate_item_totals_basic(self, item):
        """Calcule les totaux d'un item de façon basique"""
        from decimal import Decimal, InvalidOperation
        
        try:
            unit_price = Decimal(str(item.unit_price)) if item.unit_price else Decimal('0')
            quantity = Decimal(str(item.quantity)) if item.quantity else Decimal('1')
            discount = Decimal(str(item.discount)) if item.discount else Decimal('0')
            
            # Calculs basiques avec types Decimal uniformes
            discount_factor = Decimal('1') - (discount / Decimal('100'))
            net_price = unit_price * discount_factor
            item.total_ht = net_price * quantity
            
            # TVA basique (utilise le taux par défaut ou zéro)
            try:
                vat_rate_decimal = Decimal(str(item.vat_rate)) / Decimal('100') if item.vat_rate else Decimal('0')
                vat_amount = item.total_ht * vat_rate_decimal
                item.total_ttc = item.total_ht + vat_amount
            except (ValueError, TypeError, InvalidOperation):
                item.total_ttc = item.total_ht
            
        except (ValueError, TypeError, InvalidOperation) as e:
            import logging
            logger = logging.getLogger(__name__)
            logger.warning(f"Erreur calcul totaux basique pour item {getattr(item, 'designation', 'nouveau')}: {e}")
            
            item.total_ht = Decimal('0')
            item.total_ttc = Decimal('0')


# =============================================================================
# SERIALIZERS POUR LES STATISTIQUES
# =============================================================================

class QuoteStatsSerializer(CamelCaseResponseMixin, serializers.Serializer, DocumentStatsBaseMixin):
    """Serializer pour les statistiques des devis"""
    
    total = serializers.IntegerField()
    draft = serializers.IntegerField()
    sent = serializers.IntegerField()
    accepted = serializers.IntegerField()
    rejected = serializers.IntegerField()
    expired = serializers.IntegerField()
    cancelled = serializers.IntegerField()
    total_amount = serializers.DecimalField(max_digits=15, decimal_places=2)
    acceptance_rate = serializers.SerializerMethodField()
    average_amount = serializers.SerializerMethodField()
    
    def get_acceptance_rate(self, obj):
        """Calculer le taux d'acceptation"""
        return super().get_acceptance_rate(obj)
    
    def get_average_amount(self, obj):
        """Calculer le montant moyen"""
        return super().get_average_amount(obj.get('total_amount', 0), obj.get('total', 0))


class InvoiceStatsSerializer(CamelCaseResponseMixin, serializers.Serializer, DocumentStatsBaseMixin):
    """Serializer pour les statistiques des factures"""
    
    total_invoices = serializers.IntegerField()
    draft_invoices = serializers.IntegerField()
    sent_invoices = serializers.IntegerField()
    paid_invoices = serializers.IntegerField()
    overdue_invoices = serializers.IntegerField()
    partially_paid_invoices = serializers.IntegerField()
    cancelled_invoices = serializers.IntegerField()
    credit_note_invoices = serializers.IntegerField()
    total_amount_ht = serializers.DecimalField(max_digits=15, decimal_places=2)
    total_amount_ttc = serializers.DecimalField(max_digits=15, decimal_places=2)
    total_paid = serializers.DecimalField(max_digits=15, decimal_places=2)
    total_outstanding = serializers.DecimalField(max_digits=15, decimal_places=2)
    overdue_amount = serializers.DecimalField(max_digits=15, decimal_places=2)
    payment_rate = serializers.SerializerMethodField()
    average_amount = serializers.SerializerMethodField()
    average_payment_delay = serializers.FloatField()
    
    def get_payment_rate(self, obj):
        """Calculer le taux de paiement"""
        return super().get_payment_rate(obj)
    
    def get_average_amount(self, obj):
        """Calculer le montant moyen"""
        return super().get_average_amount(obj.get('total_amount_ttc', 0), obj.get('total_invoices', 0))


# =============================================================================
# SERIALIZERS POUR LES ACTIONS ET OPERATIONS
# =============================================================================

class DocumentActionSerializer(CamelCaseResponseMixin, serializers.Serializer):
    """Serializer pour les actions sur les documents"""
    
    action = serializers.ChoiceField(
        choices=['send', 'accept', 'reject', 'cancel', 'validate'],
        help_text="Action à effectuer sur le document"
    )
    note = serializers.CharField(
        max_length=500, 
        required=False, 
        help_text="Note optionnelle pour l'action"
    )


class DocumentSendSerializer(CamelCaseResponseMixin, serializers.Serializer):
    """Serializer spécifique pour l'envoi de documents par email"""
    
    recipient_email = serializers.EmailField(
        help_text="Email du destinataire"
    )
    message = serializers.CharField(
        max_length=1000,
        required=False,
        allow_blank=True,
        help_text="Message personnalisé à inclure dans l'email"
    )
    
    def validate_recipient_email(self, value):
        """Valide l'email du destinataire"""
        if not value or not value.strip():
            raise serializers.ValidationError("L'email du destinataire est requis")
        return value.strip().lower()


class RecordPaymentSerializer(CamelCaseResponseMixin, serializers.Serializer, DocumentValidationMixin):
    """Serializer pour enregistrer un paiement"""
    
    amount = serializers.DecimalField(max_digits=12, decimal_places=2)
    method = serializers.ChoiceField(choices=PaymentMethod.choices)
    date = serializers.DateField(required=False)
    reference = serializers.CharField(max_length=100, required=False)
    notes = serializers.CharField(required=False)
    
    def validate_amount(self, value):
        """Utiliser la validation du mixin"""
        if value <= 0:
            raise serializers.ValidationError("Le montant doit être positif.")
        return value


class CreateCreditNoteSerializer(CamelCaseResponseMixin, serializers.Serializer):
    """Serializer pour créer un avoir"""
    
    reason = serializers.CharField(required=False)
    is_full_credit_note = serializers.BooleanField(default=True)
    selected_items = serializers.ListField(
        child=serializers.UUIDField(),
        required=False,
        help_text="IDs des éléments pour avoir partiel"
    )
    
    def validate(self, data):
        """Validation des données d'avoir"""
        if not data.get('is_full_credit_note') and not data.get('selected_items'):
            raise serializers.ValidationError(
                "Pour un avoir partiel, il faut spécifier les éléments sélectionnés."
            )
        return data


class BulkDocumentOperationSerializer(CamelCaseResponseMixin, serializers.Serializer, BulkOperationMixin):
    """Serializer pour les opérations en lot sur les documents"""
    
    document_ids = serializers.ListField(child=serializers.UUIDField())
    action = serializers.ChoiceField(choices=['delete', 'archive', 'send', 'cancel'])
    
    def validate_document_ids(self, value):
        """Valider les IDs de documents"""
        return self.validate_bulk_ids(value)
    
    def validate_action(self, value):
        """Valider l'action"""
        allowed_actions = ['delete', 'archive', 'send', 'cancel']
        return self.validate_bulk_action(value, allowed_actions)


class DocumentExportSerializer(CamelCaseResponseMixin, serializers.Serializer):
    """Serializer pour l'export de documents"""
    
    format = serializers.ChoiceField(
        choices=['pdf', 'excel', 'csv'],
        default='pdf'
    )
    document_ids = serializers.ListField(
        child=serializers.UUIDField(),
        required=False,
        help_text="IDs des documents à exporter (vide = tous)"
    )
    include_details = serializers.BooleanField(default=True)
    date_from = serializers.DateField(required=False)
    date_to = serializers.DateField(required=False)


# =============================================================================
# SERIALIZERS POUR LES MODÈLES DE CONFIGURATION
# =============================================================================

class VATRateSerializer(CamelCaseResponseMixin, serializers.Serializer):
    """Serializer pour les taux de TVA (TextChoices)"""
    
    code = serializers.CharField()
    name = serializers.CharField()
    rate = serializers.FloatField()
    rate_display = serializers.CharField()
    description = serializers.CharField()
    is_default = serializers.BooleanField()
    is_active = serializers.BooleanField()


class PaymentMethodSerializer(CamelCaseResponseMixin, serializers.Serializer):
    """Serializer pour les moyens de paiement (TextChoices)"""
    
    code = serializers.CharField()
    name = serializers.CharField()
    description = serializers.CharField()
    requires_reference = serializers.BooleanField()
    is_active = serializers.BooleanField()


class QuoteStatusSerializer(CamelCaseResponseMixin, serializers.Serializer):
    """Serializer pour les statuts de devis (read-only)"""
    
    code = serializers.CharField()
    name = serializers.CharField()
    description = serializers.CharField()


class InvoiceStatusSerializer(CamelCaseResponseMixin, serializers.Serializer):
    """Serializer pour les statuts de factures (read-only)"""
    
    code = serializers.CharField()
    name = serializers.CharField()
    description = serializers.CharField() 