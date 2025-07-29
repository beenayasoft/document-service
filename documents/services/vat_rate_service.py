"""
Service pour la gestion des taux de TVA tenant-specific
"""
import logging
from typing import List, Dict, Any, Optional
from django.core.cache import cache
from .tenant_client import TenantConfigClient

logger = logging.getLogger(__name__)


class VatRateService:
    """Service pour récupérer et gérer les taux de TVA par tenant"""
    
    CACHE_KEY_PREFIX = "vat_rates"
    CACHE_TTL = 300  # 5 minutes
    
    def __init__(self):
        self.tenant_client = TenantConfigClient()
        self.cache_service = cache
    
    def get_vat_rates(self, tenant_id: str) -> List[Dict[str, Any]]:
        """
        Récupère les taux de TVA pour un tenant spécifique
        
        Args:
            tenant_id: ID du tenant
            
        Returns:
            Liste des taux de TVA avec leur structure:
            [
                {
                    'id': str,
                    'code': str,
                    'name': str,
                    'rate': float,
                    'rate_display': str,
                    'description': str,
                    'is_default': bool,
                    'is_active': bool
                },
                ...
            ]
        """
        if not tenant_id:
            logger.warning("Tenant ID manquant pour get_vat_rates")
            return self._get_fallback_vat_rates()
        
        cache_key = f"{self.CACHE_KEY_PREFIX}:{tenant_id}"
        
        # Vérifier le cache Redis (avec gestion gracieuse des erreurs)
        try:
            cached_rates = self.cache_service.get(cache_key)
            if cached_rates:
                logger.debug(f"Taux de TVA récupérés du cache pour tenant {tenant_id}")
                return cached_rates
        except Exception as e:
            logger.debug(f"Cache indisponible pour les taux de TVA tenant {tenant_id}: {e}")
            # Continuer sans cache
        
        # Récupérer depuis tenant-service
        try:
            logger.info(f"Récupération des taux de TVA depuis tenant-service pour tenant {tenant_id}")
            vat_rates = self._fetch_from_tenant_service(tenant_id)
            
            # Mettre en cache (avec gestion gracieuse des erreurs)
            try:
                self.cache_service.set(cache_key, vat_rates, self.CACHE_TTL)
                logger.debug(f"Taux de TVA mis en cache pour tenant {tenant_id}")
            except Exception as e:
                logger.debug(f"Impossible de mettre en cache les taux de TVA pour tenant {tenant_id}: {e}")
                # Continuer sans cache
            
            logger.info(f"Taux de TVA récupérés et mis en cache pour tenant {tenant_id}")
            return vat_rates
            
        except Exception as e:
            logger.error(f"Erreur lors de la récupération des taux de TVA pour tenant {tenant_id}: {str(e)}")
            return self._get_fallback_vat_rates()
    
    def _fetch_from_tenant_service(self, tenant_id: str) -> List[Dict[str, Any]]:
        """
        Récupère les taux de TVA depuis le tenant-service
        
        Args:
            tenant_id: ID du tenant
            
        Returns:
            Liste des taux de TVA formatés
        """
        # Récupérer les informations complètes du tenant
        tenant_info = self.tenant_client.get_tenant_info(tenant_id)
        
        if not tenant_info:
            raise Exception("Impossible de récupérer les informations du tenant")
        
        # Extraire les taux de TVA
        vat_rates = tenant_info.get('vat_rates', [])
        
        if not vat_rates:
            logger.info(f"Aucun taux de TVA personnalisé pour tenant {tenant_id}, utilisation des taux par défaut")
            return self._get_default_vat_rates()
        
        # Formater les taux pour l'utilisation dans les documents
        formatted_rates = []
        for rate in vat_rates:
            formatted_rate = {
                'id': rate.get('id', ''),
                'code': rate.get('code', ''),
                'name': rate.get('name', ''),
                'rate': float(rate.get('rate', 0)),
                'rate_display': rate.get('rate_display', f"{rate.get('rate', 0)}%"),
                'description': rate.get('description', ''),
                'is_default': rate.get('is_default', False),
                'is_active': rate.get('is_active', True)
            }
            formatted_rates.append(formatted_rate)
        
        # S'assurer qu'il y a au moins un taux par défaut
        default_rates = [r for r in formatted_rates if r['is_default']]
        if not default_rates and formatted_rates:
            # Si aucun taux n'est marqué comme défaut, marquer le premier comme défaut
            formatted_rates[0]['is_default'] = True
        
        return formatted_rates
    
    def _get_default_vat_rates(self) -> List[Dict[str, Any]]:
        """
        Retourne une liste vide - plus de taux par défaut hardcodés
        Le tenant doit configurer ses propres taux de TVA
        
        Returns:
            Liste vide - forcer la configuration tenant-specific
        """
        logger.warning("Aucun taux de TVA configuré pour ce tenant - configuration requise")
        return []
    
    def _get_fallback_vat_rates(self) -> List[Dict[str, Any]]:
        """
        Retourne une liste vide en cas d'erreur - plus de fallback hardcodé
        
        Returns:
            Liste vide - forcer la configuration tenant-specific
        """
        logger.error("Erreur de récupération des taux de TVA - aucun taux disponible")
        return []
    
    def get_default_vat_rate(self, tenant_id: str) -> Optional[Dict[str, Any]]:
        """
        Récupère le taux de TVA par défaut pour un tenant
        
        Args:
            tenant_id: ID du tenant
            
        Returns:
            Taux de TVA par défaut ou None
        """
        vat_rates = self.get_vat_rates(tenant_id)
        
        # Chercher le taux marqué comme défaut
        for rate in vat_rates:
            if rate['is_default'] and rate['is_active']:
                return rate
        
        # Si aucun taux par défaut, retourner le premier taux actif
        for rate in vat_rates:
            if rate['is_active']:
                return rate
        
        return None
    
    def get_vat_rate_by_code(self, tenant_id: str, code: str) -> Optional[Dict[str, Any]]:
        """
        Récupère un taux de TVA spécifique par son code
        
        Args:
            tenant_id: ID du tenant
            code: Code du taux de TVA
            
        Returns:
            Taux de TVA correspondant ou None
        """
        vat_rates = self.get_vat_rates(tenant_id)
        
        for rate in vat_rates:
            if rate['code'] == code and rate['is_active']:
                return rate
        
        return None
    
    def get_active_vat_rates(self, tenant_id: str) -> List[Dict[str, Any]]:
        """
        Récupère uniquement les taux de TVA actifs pour un tenant
        
        Args:
            tenant_id: ID du tenant
            
        Returns:
            Liste des taux de TVA actifs
        """
        vat_rates = self.get_vat_rates(tenant_id)
        return [rate for rate in vat_rates if rate['is_active']]
    
    def invalidate_cache(self, tenant_id: str) -> bool:
        """
        Invalide le cache des taux de TVA pour un tenant
        
        Args:
            tenant_id: ID du tenant
            
        Returns:
            True si le cache a été invalidé avec succès
        """
        if not tenant_id:
            return False
            
        cache_key = f"{self.CACHE_KEY_PREFIX}:{tenant_id}"
        
        try:
            self.cache_service.delete(cache_key)
            logger.info(f"Cache invalidé pour les taux de TVA du tenant {tenant_id}")
            return True
        except Exception as e:
            logger.error(f"Erreur lors de l'invalidation du cache pour tenant {tenant_id}: {str(e)}")
            return False
    
    def refresh_vat_rates(self, tenant_id: str) -> List[Dict[str, Any]]:
        """
        Force la récupération des taux de TVA depuis le tenant-service
        
        Args:
            tenant_id: ID du tenant
            
        Returns:
            Liste des taux de TVA mis à jour
        """
        # Invalider le cache
        self.invalidate_cache(tenant_id)
        
        # Récupérer les nouvelles données
        return self.get_vat_rates(tenant_id)


# Instance globale du service
vat_rate_service = VatRateService()