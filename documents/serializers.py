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
            'id', 'number', 'tier_id', 'client_name', 'client_address', 'client_info',
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


class QuoteCreateSerializer(QuoteSerializer):
    """Serializer pour créer un devis"""
    
    # Éléments pour création
    items = QuoteItemSerializer(many=True, required=False)
    
    class Meta(QuoteSerializer.Meta):
        read_only_fields = ['id', 'created_at', 'updated_at']  # Enlever 'number' pour permettre la création
    
    def create(self, validated_data):
        """Créer un devis avec ses éléments"""
        items_data = validated_data.pop('items', [])
        
        # Créer le devis
        quote = Quote.objects.create(**validated_data)
        
        # Créer les éléments
        for item_data in items_data:
            QuoteItem.objects.create(quote=quote, **item_data)
        
        # Mettre à jour les totaux
        quote.update_totals()
        quote.refresh_from_db()
        
        return quote


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


class InvoiceCreateSerializer(InvoiceSerializer):
    """Serializer pour créer une facture"""
    
    # Éléments pour création
    items = InvoiceItemSerializer(many=True, required=False)
    
    class Meta(InvoiceSerializer.Meta):
        read_only_fields = ['id', 'created_at', 'updated_at']  # Enlever 'number' pour permettre la création
    
    def create(self, validated_data):
        """Créer une facture avec ses éléments"""
        items_data = validated_data.pop('items', [])
        
        # Créer la facture
        invoice = Invoice.objects.create(**validated_data)
        
        # Créer les éléments
        for item_data in items_data:
            InvoiceItem.objects.create(invoice=invoice, **item_data)
        
        # Mettre à jour les totaux
        invoice.update_totals()
        invoice.refresh_from_db()
        
        return invoice


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