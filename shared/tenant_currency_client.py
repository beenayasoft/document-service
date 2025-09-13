"""
Client unifié pour récupération des informations de devise du tenant
Utilisé par tous les services SOA pour éliminer le hardcoding
"""

import requests
import logging
from typing import Optional, Dict, Any
from django.core.cache import cache
from django.conf import settings
import json

logger = logging.getLogger(__name__)


class TenantCurrencyClient:
    """
    Client pour récupérer les informations de devise du tenant depuis le tenant-service
    """
    
    # Configuration par défaut si impossible de récupérer depuis tenant-service
    DEFAULT_CONFIG = {
        'currency': 'MAD',
        'currency_symbol': 'DH',
        'currency_position': 'after',
        'locale': 'fr-MA',
        'timezone': 'Africa/Casablanca',
        'language': 'fr'
    }
    
    # Cache TTL (30 minutes)
    CACHE_TTL = 30 * 60
    
    @classmethod
    def get_tenant_currency_config(cls, tenant_id: str) -> Dict[str, Any]:
        """
        Récupère la configuration de devise du tenant
        
        Args:
            tenant_id: ID du tenant
            
        Returns:
            Dict avec configuration de devise
        """
        # Vérifier le cache d'abord
        cache_key = f"tenant_currency_{tenant_id}"
        cached_config = cache.get(cache_key)
        
        if cached_config:
            logger.debug(f"Configuration devise récupérée depuis le cache pour {tenant_id}")
            return cached_config
        
        # Récupérer depuis le tenant-service
        try:
            config = cls._fetch_from_tenant_service(tenant_id)
            if config:
                # Mettre en cache
                cache.set(cache_key, config, cls.CACHE_TTL)
                logger.info(f"Configuration devise récupérée et mise en cache pour {tenant_id}")
                return config
        except Exception as e:
            logger.error(f"Erreur lors de la récupération de la devise pour {tenant_id}: {e}")
        
        # Fallback sur la configuration par défaut
        logger.warning(f"Utilisation de la configuration par défaut pour {tenant_id}")
        return cls.DEFAULT_CONFIG.copy()
    
    @classmethod
    def _fetch_from_tenant_service(cls, tenant_id: str) -> Optional[Dict[str, Any]]:
        """
        Récupère les données directement depuis le tenant-service
        """
        tenant_service_url = getattr(settings, 'TENANT_SERVICE_URL', 'http://localhost:8001')
        
        try:
            # Appeler l'API du tenant-service
            response = requests.get(
                f"{tenant_service_url}/api/tenants/{tenant_id}/tenant_info/",
                headers={
                    'Content-Type': 'application/json',
                    'X-Tenant-ID': tenant_id
                },
                timeout=5
            )
            
            if response.status_code == 200:
                data = response.json()
                settings_data = data.get('settings', {})
                
                return {
                    'currency': settings_data.get('currency', cls.DEFAULT_CONFIG['currency']),
                    'currency_symbol': settings_data.get('currency_symbol', cls.DEFAULT_CONFIG['currency_symbol']),
                    'currency_position': settings_data.get('currency_position', cls.DEFAULT_CONFIG['currency_position']),
                    'locale': settings_data.get('locale', cls.DEFAULT_CONFIG['locale']),
                    'timezone': settings_data.get('timezone', cls.DEFAULT_CONFIG['timezone']),
                    'language': settings_data.get('language', cls.DEFAULT_CONFIG['language'])
                }
            else:
                logger.error(f"Erreur HTTP {response.status_code} lors de la récupération des données tenant")
                
        except requests.RequestException as e:
            logger.error(f"Erreur réseau lors de la récupération des données tenant: {e}")
        except json.JSONDecodeError as e:
            logger.error(f"Erreur de décodage JSON: {e}")
        
        return None
    
    @classmethod
    def format_currency(cls, amount: float, tenant_id: str) -> str:
        """
        Formate un montant selon la devise du tenant
        
        Args:
            amount: Montant à formater
            tenant_id: ID du tenant
            
        Returns:
            Montant formaté avec devise
        """
        config = cls.get_tenant_currency_config(tenant_id)
        
        # Formater le montant
        formatted_amount = f"{amount:,.2f}"
        
        # Appliquer la position du symbole de devise
        if config['currency_position'] == 'before':
            return f"{config['currency_symbol']}{formatted_amount}"
        else:
            return f"{formatted_amount} {config['currency_symbol']}"
    
    @classmethod
    def get_currency_code(cls, tenant_id: str) -> str:
        """
        Récupère uniquement le code de devise
        
        Args:
            tenant_id: ID du tenant
            
        Returns:
            Code de devise (ex: MAD, EUR, USD)
        """
        config = cls.get_tenant_currency_config(tenant_id)
        return config['currency']
    
    @classmethod
    def get_currency_symbol(cls, tenant_id: str) -> str:
        """
        Récupère uniquement le symbole de devise
        
        Args:
            tenant_id: ID du tenant
            
        Returns:
            Symbole de devise (ex: DH, €, $)
        """
        config = cls.get_tenant_currency_config(tenant_id)
        return config['currency_symbol']
    
    @classmethod
    def invalidate_cache(cls, tenant_id: str) -> None:
        """
        Invalide le cache pour un tenant donné
        
        Args:
            tenant_id: ID du tenant
        """
        cache_key = f"tenant_currency_{tenant_id}"
        cache.delete(cache_key)
        logger.info(f"Cache invalidé pour le tenant {tenant_id}")
    
    @classmethod
    def warm_cache(cls, tenant_id: str) -> None:
        """
        Précharge le cache pour un tenant
        
        Args:
            tenant_id: ID du tenant
        """
        cls.get_tenant_currency_config(tenant_id)
        logger.info(f"Cache pré-chargé pour le tenant {tenant_id}")


class TenantCurrencyMixin:
    """
    Mixin pour les modèles Django qui ont besoin d'accès aux informations de devise
    """
    
    def get_tenant_currency_config(self) -> Dict[str, Any]:
        """
        Récupère la configuration de devise pour ce modèle
        Nécessite que le modèle ait un attribut _tenant_id
        """
        tenant_id = getattr(self, '_tenant_id', None)
        if not tenant_id:
            # Essayer de récupérer depuis le contexte de requête ou autre
            tenant_id = self._get_tenant_id_from_context()
        
        if tenant_id:
            return TenantCurrencyClient.get_tenant_currency_config(tenant_id)
        
        return TenantCurrencyClient.DEFAULT_CONFIG.copy()
    
    def format_currency(self, amount: float) -> str:
        """
        Formate un montant selon la devise du tenant
        """
        tenant_id = getattr(self, '_tenant_id', None)
        if not tenant_id:
            tenant_id = self._get_tenant_id_from_context()
        
        if tenant_id:
            return TenantCurrencyClient.format_currency(amount, tenant_id)
        
        # Fallback
        return f"{amount:,.2f} {TenantCurrencyClient.DEFAULT_CONFIG['currency_symbol']}"
    
    def _get_tenant_id_from_context(self) -> Optional[str]:
        """
        Récupère le tenant_id depuis le contexte (à surcharger dans chaque service)
        """
        # Cette méthode doit être surchargée dans chaque service
        # selon leur façon de gérer le contexte tenant
        return None