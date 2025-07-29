"""
Utilitaires optimisés pour les performances du document-service
Fonctions pour créations batch et calculs optimisés
"""
from decimal import Decimal
from django.db import transaction
from typing import List, Dict, Any
import logging

logger = logging.getLogger(__name__)

class OptimizedDocumentUtils:
    """
    Utilitaires pour optimiser les performances des documents
    """
    
    @staticmethod
    def bulk_create_quote_items(quote, items_data: List[Dict[str, Any]], tenant_id: str = None):
        """
        Création optimisée d'items de devis en batch
        
        Args:
            quote: Instance du devis
            items_data: Liste des données d'items
            tenant_id: ID du tenant pour les calculs de TVA
            
        Returns:
            Liste des items créés
        """
        from .models import QuoteItem
        
        with transaction.atomic():
            # Précalculer les taux de TVA pour tous les items
            vat_rates_cache = OptimizedDocumentUtils._preload_vat_rates(items_data, tenant_id)
            
            # Créer les items avec calculs optimisés
            items_to_create = []
            for item_data in items_data:
                item = QuoteItem(
                    quote=quote,
                    **{k: v for k, v in item_data.items() if k != 'tenant_id'}
                )
                
                # Calculs optimisés avec cache pré-chargé
                if item.type not in ["chapter", "section"]:
                    OptimizedDocumentUtils._calculate_item_totals_with_cache(
                        item, vat_rates_cache, tenant_id
                    )
                
                items_to_create.append(item)
            
            # Bulk create sans trigger de save individuel
            created_items = QuoteItem.objects.bulk_create(items_to_create)
            
            # Une seule mise à jour des totaux du document à la fin
            quote.update_totals(tenant_id=tenant_id)
            
            logger.info(f"Création batch de {len(created_items)} items pour devis {quote.id}")
            return created_items
    
    @staticmethod
    def bulk_create_invoice_items(invoice, items_data: List[Dict[str, Any]], tenant_id: str = None):
        """
        Création optimisée d'items de facture en batch
        """
        from .models import InvoiceItem
        
        with transaction.atomic():
            vat_rates_cache = OptimizedDocumentUtils._preload_vat_rates(items_data, tenant_id)
            
            items_to_create = []
            for item_data in items_data:
                item = InvoiceItem(
                    invoice=invoice,
                    **{k: v for k, v in item_data.items() if k != 'tenant_id'}
                )
                
                if item.type not in ["chapter", "section"]:
                    OptimizedDocumentUtils._calculate_item_totals_with_cache(
                        item, vat_rates_cache, tenant_id
                    )
                
                items_to_create.append(item)
            
            created_items = InvoiceItem.objects.bulk_create(items_to_create)
            invoice.update_totals(tenant_id=tenant_id)
            
            logger.info(f"Création batch de {len(created_items)} items pour facture {invoice.id}")
            return created_items
    
    @staticmethod
    def _preload_vat_rates(items_data: List[Dict[str, Any]], tenant_id: str = None) -> Dict[str, Decimal]:
        """
        Précharge tous les taux de TVA nécessaires en une seule fois
        """
        if not tenant_id:
            return {}
        
        try:
            from .services.vat_rate_service import vat_rate_service
            
            # Extraire tous les codes de TVA uniques
            vat_codes = {item.get('vat_rate', '20') for item in items_data}
            vat_rates_cache = {}
            
            # Récupérer tous les taux en une seule fois (si le service le supporte)
            for vat_code in vat_codes:
                try:
                    vat_rate_info = vat_rate_service.get_vat_rate_by_code(tenant_id, vat_code)
                    if vat_rate_info:
                        vat_rates_cache[vat_code] = Decimal(str(vat_rate_info['rate'])) / Decimal('100')
                    else:
                        vat_rates_cache[vat_code] = Decimal(str(vat_code)) / Decimal('100')
                except Exception as e:
                    logger.warning(f"Erreur récupération taux TVA {vat_code}: {e}")
                    vat_rates_cache[vat_code] = Decimal('0.20')  # Fallback 20%
            
            logger.debug(f"Taux TVA préchargés: {list(vat_codes)}")
            return vat_rates_cache
            
        except Exception as e:
            logger.error(f"Erreur préchargement taux TVA: {e}")
            return {}
    
    @staticmethod
    def _calculate_item_totals_with_cache(item, vat_rates_cache: Dict[str, Decimal], tenant_id: str = None):
        """
        Calcule les totaux d'un item avec cache de taux de TVA pré-chargé
        """
        try:
            unit_price = Decimal(str(item.unit_price)) if item.unit_price else Decimal('0')
            quantity = Decimal(str(item.quantity)) if item.quantity else Decimal('1')
            discount = Decimal(str(item.discount)) if item.discount else Decimal('0')
            
            # Calculs avec types Decimal uniformes
            discount_factor = Decimal('1') - (discount / Decimal('100'))
            net_price = unit_price * discount_factor
            item.total_ht = net_price * quantity
            
            # Utiliser le cache pré-chargé ou fallback
            vat_rate_decimal = vat_rates_cache.get(
                item.vat_rate, 
                Decimal(str(item.vat_rate)) / Decimal('100') if item.vat_rate else Decimal('0.20')
            )
            
            vat_amount = item.total_ht * vat_rate_decimal
            item.total_ttc = item.total_ht + vat_amount
            
        except Exception as e:
            logger.warning(f"Erreur calcul totaux item: {e}")
            item.total_ht = Decimal('0')
            item.total_ttc = Decimal('0')
    
    @staticmethod
    def optimize_queryset_for_list(queryset, include_items_count=True):
        """
        Optimise un queryset pour l'affichage en liste
        
        Args:
            queryset: Queryset de base
            include_items_count: Inclure le nombre d'items
            
        Returns:
            Queryset optimisé
        """
        optimized = queryset.defer(
            'notes', 'terms_and_conditions', 'client_address', 'project_address'
        ).order_by('-created_at')
        
        if include_items_count:
            from django.db.models import Count
            optimized = optimized.annotate(items_count=Count('items'))
        
        return optimized
    
    @staticmethod
    def optimize_queryset_for_detail(queryset):
        """
        Optimise un queryset pour l'affichage détaillé
        """
        return queryset.prefetch_related(
            'items__parent',
            'items__children'
        ).select_related()
    
    @staticmethod
    def batch_update_document_totals(documents, tenant_id: str = None):
        """
        Met à jour les totaux de plusieurs documents en batch
        
        Args:
            documents: Liste ou queryset de documents
            tenant_id: ID du tenant pour les calculs
        """
        updated_count = 0
        
        try:
            with transaction.atomic():
                for document in documents:
                    document.update_totals(tenant_id=tenant_id)
                    updated_count += 1
                
            logger.info(f"Totaux mis à jour pour {updated_count} documents")
            
        except Exception as e:
            logger.error(f"Erreur mise à jour batch totaux: {e}")
            raise