"""
Mixins partagés pour les serializers de documents
"""
from rest_framework import serializers
from decimal import Decimal
from datetime import datetime


class DocumentValidationMixin:
    """Mixin pour les validations communes aux documents"""
    
    def validate_quantity(self, value):
        """Valider que la quantité est positive"""
        if value < 0:
            raise serializers.ValidationError("La quantité ne peut pas être négative.")
        return value
    
    def validate_unit_price(self, value):
        """Valider que le prix unitaire est positif ou nul"""
        if value < 0:
            raise serializers.ValidationError("Le prix unitaire ne peut pas être négatif.")
        return value
    
    def validate_discount(self, value):
        """Valider que la remise est entre 0 et 100%"""
        if value < 0 or value > 100:
            raise serializers.ValidationError("La remise doit être comprise entre 0 et 100%.")
        return value
    
    def validate_validity_period(self, value):
        """Valider la durée de validité (pour les devis)"""
        if value <= 0:
            raise serializers.ValidationError("La durée de validité doit être positive.")
        if value > 365:
            raise serializers.ValidationError("La durée de validité ne peut pas dépasser 365 jours.")
        return value
    
    def validate_payment_terms(self, value):
        """Valider les délais de paiement (pour les factures)"""
        if value < 0:
            raise serializers.ValidationError("Le délai de paiement ne peut pas être négatif.")
        if value > 365:
            raise serializers.ValidationError("Le délai de paiement ne peut pas dépasser 365 jours.")
        return value


class DateValidationMixin:
    """Mixin pour les validations de dates"""
    
    def validate_dates(self, data, issue_field='issue_date', due_field=None, expiry_field=None):
        """Valide les cohérences de dates"""
        issue_date = data.get(issue_field)
        
        # Validation date d'échéance (factures)
        if due_field and due_field in data:
            due_date = data[due_field]
            if issue_date and due_date and due_date < issue_date:
                raise serializers.ValidationError({
                    due_field: "La date d'échéance ne peut pas être antérieure à la date d'émission."
                })
        
        # Validation date d'expiration (devis)
        if expiry_field and expiry_field in data:
            expiry_date = data[expiry_field]
            if issue_date and expiry_date and expiry_date <= issue_date:
                raise serializers.ValidationError({
                    expiry_field: "La date d'expiration doit être postérieure à la date d'émission."
                })
        
        return data


class BaseDocumentMixin:
    """Mixin pour les champs communs des documents"""
    
    def get_formatted_date(self, date_field):
        """Formater une date au format français"""
        if date_field:
            return date_field.strftime('%d/%m/%Y')
        return None
    
    def get_client_info(self, obj):
        """Récupérer les informations client simplifiées"""
        return {
            'id': str(obj.tier_id),
            'name': obj.client_name,
            'address': obj.client_address
        }
    
    def get_project_info(self, obj):
        """Récupérer les informations projet"""
        if obj.project_name:
            return {
                'name': obj.project_name,
                'address': obj.project_address,
                'reference': obj.project_reference
            }
        return None


class BaseDocumentItemMixin:
    """Mixin pour les champs communs des éléments de documents"""
    
    def get_parent_info(self, obj):
        """Récupérer les informations de l'élément parent"""
        if obj.parent:
            return {
                'id': str(obj.parent.id),
                'designation': obj.parent.designation,
                'type': obj.parent.type,
            }
        return None
    
    def get_children(self, obj):
        """Récupérer les sous-éléments"""
        if obj.type in ['chapter', 'section']:
            children = obj.children.all().order_by('position')
            # Import dynamique pour éviter la circularité
            from .serializers import BaseDocumentItemSerializer
            return BaseDocumentItemSerializer(children, many=True).data
        return []
    
    def validate_hierarchy(self, data):
        """Valider la hiérarchie des éléments"""
        # Vérifier que les chapitres/sections n'ont pas de parent
        if data.get('parent') and data.get('type') in ['chapter', 'section']:
            raise serializers.ValidationError(
                "Un chapitre ou une section ne peut pas avoir de parent."
            )
        
        # Vérifier que les éléments avec parent ne sont pas des chapitres/sections
        if data.get('parent') and data.get('type') in ['chapter', 'section']:
            raise serializers.ValidationError(
                "Les chapitres et sections ne peuvent pas être des sous-éléments."
            )
        
        return data


class DocumentStatsBaseMixin:
    """Mixin pour les statistiques de base des documents"""
    
    def get_acceptance_rate(self, stats_data):
        """Calculer le taux d'acceptation (pour devis)"""
        total = stats_data.get('total', 0)
        accepted = stats_data.get('accepted', 0)
        
        if total > 0:
            return round((accepted / total) * 100, 2)
        return 0
    
    def get_payment_rate(self, stats_data):
        """Calculer le taux de paiement (pour factures)"""
        total = stats_data.get('total_invoices', 0)
        paid = stats_data.get('paid_invoices', 0)
        
        if total > 0:
            return round((paid / total) * 100, 2)
        return 0
    
    def get_average_amount(self, total_amount, count):
        """Calculer le montant moyen"""
        if count > 0:
            return round(total_amount / count, 2)
        return 0


class ClientInfoMixin:
    """Mixin pour les informations client via API externe"""
    
    def get_client_details(self, tier_id):
        """
        Récupérer les détails client via l'API CRM
        TODO: Implémenter l'appel API vers le service CRM
        """
        # Pour l'instant, retourner des infos de base
        # Plus tard, faire un appel HTTP vers le service CRM
        return {
            'id': str(tier_id),
            'type': 'unknown',  # À récupérer via API
            'contacts': [],     # À récupérer via API
            'addresses': []     # À récupérer via API
        }


class RelatedDocumentMixin:
    """Mixin pour les relations entre documents"""
    
    def get_quote_info(self, obj):
        """Récupérer les informations du devis lié (pour factures)"""
        if hasattr(obj, 'quote_id') and obj.quote_id:
            # TODO: Appel API vers le service documents pour récupérer le devis
            return {
                'id': str(obj.quote_id),
                'number': obj.quote_number or 'Inconnu',
                'amount': None  # À récupérer via API
            }
        return None
    
    def get_invoice_info(self, obj):
        """Récupérer les informations de la facture liée (pour avoirs)"""
        if hasattr(obj, 'original_invoice_id') and obj.original_invoice_id:
            # TODO: Appel API interne pour récupérer la facture
            return {
                'id': str(obj.original_invoice_id),
                'number': 'À récupérer',  # À récupérer via API
                'amount': None  # À récupérer via API
            }
        return None


class BulkOperationMixin:
    """Mixin pour les opérations en lot"""
    
    def validate_bulk_ids(self, ids_list):
        """Valider une liste d'IDs pour les opérations en lot"""
        if not ids_list:
            raise serializers.ValidationError("Au moins un ID doit être fourni.")
        
        if len(ids_list) > 100:
            raise serializers.ValidationError("Maximum 100 éléments autorisés par opération en lot.")
        
        return ids_list
    
    def validate_bulk_action(self, action, allowed_actions):
        """Valider qu'une action est autorisée"""
        if action not in allowed_actions:
            raise serializers.ValidationError(f"Action '{action}' non autorisée. Actions disponibles : {', '.join(allowed_actions)}")
        
        return action


class CalculationMixin:
    """Mixin pour les calculs financiers"""
    
    def calculate_vat_breakdown(self, items):
        """Calculer la répartition de TVA par taux"""
        vat_breakdown = {}
        
        for item in items:
            if item.type not in ["chapter", "section"]:
                rate = str(item.vat_rate)
                
                if rate not in vat_breakdown:
                    vat_breakdown[rate] = {
                        'rate': rate,
                        'base_ht': Decimal('0'),
                        'vat_amount': Decimal('0')
                    }
                
                vat_breakdown[rate]['base_ht'] += item.total_ht or Decimal('0')
                
                # Calculer la TVA
                vat_rate_decimal = Decimal(item.vat_rate) / Decimal('100')
                vat_amount = item.total_ht * vat_rate_decimal
                vat_breakdown[rate]['vat_amount'] += vat_amount
        
        return list(vat_breakdown.values())
    
    def calculate_totals_summary(self, items):
        """Calculer un résumé des totaux"""
        total_ht = Decimal('0')
        total_vat = Decimal('0')
        items_count = 0
        
        for item in items:
            if item.type not in ["chapter", "section"]:
                total_ht += item.total_ht or Decimal('0')
                vat_rate = Decimal(item.vat_rate) / Decimal('100')
                total_vat += item.total_ht * vat_rate
                items_count += 1
        
        return {
            'items_count': items_count,
            'total_ht': total_ht,
            'total_vat': total_vat,
            'total_ttc': total_ht + total_vat
        } 