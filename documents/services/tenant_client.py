"""
Client HTTP optimisé pour communiquer avec le tenant-service
Gère la récupération des configurations tenant avec cache Django simple
SANS REDIS - Optimisé pour réduire les appels multiples
"""
import requests
import logging
from django.conf import settings
from django.core.cache import cache
from .cache_service import TenantConfigCacheService
from typing import Optional, Dict, Any
import json

logger = logging.getLogger(__name__)

class TenantConfigClient:
    """Client pour communiquer avec le tenant-service"""
    
    # Configuration des timeouts et retry - OPTIMISÉ PHASE 2
    TIMEOUT = getattr(settings, 'TENANT_SERVICE_TIMEOUT', 2)  # Réduit à 2s pour performance
    CACHE_TIMEOUT = getattr(settings, 'TENANT_CONFIG_CACHE_TIMEOUT', 300)  # Réduit à 5 minutes
    MAX_RETRIES = 1  # Réduit à 1 retry pour éviter les lenteurs
    
    @classmethod
    def get_tenant_config(cls, tenant_id: str) -> Dict[str, Any]:
        """
        Récupère la configuration complète du tenant
        
        Args:
            tenant_id: ID du tenant
            
        Returns:
            Dict contenant la configuration complète
        """
        try:
            tenant_service_url = getattr(settings, 'TENANT_SERVICE_URL', 'http://localhost:8001')
            
            response = requests.get(
                f"{tenant_service_url}/api/tenants/current_tenant_info/",
                headers={'X-Tenant-ID': tenant_id},
                timeout=cls.TIMEOUT
            )
            response.raise_for_status()
            
            config = response.json()
            logger.info(f"Configuration tenant {tenant_id} récupérée avec succès")
            return config
            
        except requests.RequestException as e:
            logger.error(f"Erreur récupération config tenant {tenant_id}: {e}")
            return cls._get_default_config(tenant_id)
        except Exception as e:
            logger.error(f"Erreur inattendue récupération config tenant {tenant_id}: {e}")
            return cls._get_default_config(tenant_id)
    
    @classmethod
    def get_document_numbering(cls, tenant_id: str, document_type: str) -> Dict[str, Any]:
        """
        Récupère la configuration de numérotation pour un type de document
        
        Args:
            tenant_id: ID du tenant
            document_type: Type de document ('quote', 'invoice', 'credit_note')
            
        Returns:
            Dict contenant la configuration de numérotation
        """
        try:
            tenant_service_url = getattr(settings, 'TENANT_SERVICE_URL', 'http://localhost:8001')
            
            response = requests.get(
                f"{tenant_service_url}/api/tenants/document_numbering/{document_type}/",
                headers={'X-Tenant-ID': tenant_id},
                timeout=cls.TIMEOUT
            )
            response.raise_for_status()
            
            config = response.json()
            logger.info(f"Config numérotation {document_type} pour tenant {tenant_id} récupérée")
            return config
            
        except requests.RequestException as e:
            logger.error(f"Erreur récupération numérotation {document_type} pour tenant {tenant_id}: {e}")
            return cls._create_default_numbering(tenant_id, document_type)
        except Exception as e:
            logger.error(f"Erreur inattendue numérotation {document_type} pour tenant {tenant_id}: {e}")
            return cls._create_default_numbering(tenant_id, document_type)
    
    @classmethod
    def get_cached_config(cls, tenant_id: str) -> Dict[str, Any]:
        """
        Récupère la configuration tenant avec cache optimisé
        
        Args:
            tenant_id: ID du tenant
            
        Returns:
            Dict contenant la configuration tenant
        """
        # Essayer de récupérer depuis le cache optimisé
        config = TenantConfigCacheService.get_tenant_config(tenant_id)
        
        if not config:
            logger.info(f"Cache miss pour tenant {tenant_id}, récupération depuis l'API")
            config = cls.get_tenant_config(tenant_id)
            
            # Mettre en cache avec le service dédié
            if config and config.get('id'):
                TenantConfigCacheService.set_tenant_config(tenant_id, config)
                logger.info(f"Configuration tenant {tenant_id} mise en cache")
        else:
            logger.debug(f"Cache hit pour tenant {tenant_id}")
        
        return config
    
    @classmethod
    def get_tenant_info(cls, tenant_id: str) -> Optional[Dict[str, Any]]:
        """
        Récupère les informations complètes du tenant (alias pour get_tenant_config)
        
        Args:
            tenant_id: ID du tenant
            
        Returns:
            Dict contenant les informations du tenant ou None si erreur
        """
        config = cls.get_tenant_config(tenant_id)
        
        # Retourner None si c'est une config de fallback ou si erreur
        if not config or config.get('_is_fallback'):
            return None
            
        return config
    
    @classmethod
    def get_cached_numbering(cls, tenant_id: str, document_type: str) -> Dict[str, Any]:
        """
        Récupère la configuration de numérotation avec cache optimisé
        
        Args:
            tenant_id: ID du tenant
            document_type: Type de document
            
        Returns:
            Dict contenant la configuration de numérotation
        """
        # Essayer de récupérer depuis le cache optimisé
        config = TenantConfigCacheService.get_numbering_config(tenant_id, document_type)
        
        if not config:
            logger.info(f"Cache miss pour numérotation {document_type} tenant {tenant_id}")
            config = cls.get_document_numbering(tenant_id, document_type)
            
            # Mettre en cache avec le service dédié
            if config and config.get('id'):
                TenantConfigCacheService.set_numbering_config(tenant_id, document_type, config)
                logger.info(f"Config numérotation {document_type} tenant {tenant_id} mise en cache")
        else:
            logger.debug(f"Cache hit pour numérotation {document_type} tenant {tenant_id}")
        
        return config
    
    @classmethod
    def _update_cache_counter(cls, tenant_id: str, numbering_id: str, new_counter: int):
        """
        Met à jour un compteur spécifique dans le cache local
        OPTIMISATION PHASE 2: Évite la re-récupération complète
        
        Args:
            tenant_id: ID du tenant
            numbering_id: ID de la configuration de numérotation
            new_counter: Nouvelle valeur du compteur
        """
        from .cache_service import TenantConfigCacheService
        
        # Chercher toutes les configurations en cache pour ce tenant
        cache_keys = TenantConfigCacheService._get_tenant_cache_keys(tenant_id)
        
        for cache_key in cache_keys:
            if 'numbering' in cache_key:
                cached_config = TenantConfigCacheService._get_from_cache(cache_key)
                if cached_config and str(cached_config.get('id')) == str(numbering_id):
                    # Mettre à jour le compteur dans la config cachée
                    cached_config['next_number'] = new_counter
                    # Mettre à jour l'aperçu aussi
                    if 'preview' in cached_config:
                        # Recalculer l'aperçu avec le nouveau compteur
                        cached_config['preview'] = cls._regenerate_preview(cached_config)
                    
                    # Remettre en cache avec la nouvelle valeur
                    TenantConfigCacheService._set_to_cache(cache_key, cached_config)
                    logger.debug(f"Compteur mis à jour en cache: {numbering_id} -> {new_counter}")
                    break

    @classmethod
    def _regenerate_preview(cls, config: dict) -> str:
        """
        Régénère l'aperçu d'un numéro à partir de la configuration
        """
        from datetime import datetime
        now = datetime.now()
        
        parts = []
        separator = config.get('separator', '-')
        
        if config.get('prefix'):
            parts.append(config['prefix'])
        
        date_parts = []
        if config.get('include_year', True):
            date_parts.append(str(now.year))
        if config.get('include_month', False):
            date_parts.append(f"{now.month:02d}")
        if config.get('include_day', False):
            date_parts.append(f"{now.day:02d}")
        
        if date_parts:
            parts.append(separator.join(date_parts))
        
        padding = config.get('padding', 3)
        number = config.get('next_number', 1)
        parts.append(f"{number:0{padding}d}")
        
        if config.get('suffix'):
            parts.append(config['suffix'])
        
        return separator.join(parts)

    @classmethod
    def invalidate_cache(cls, tenant_id: str):
        """
        Invalide le cache pour un tenant spécifique
        
        Args:
            tenant_id: ID du tenant
        """
        deleted_count = TenantConfigCacheService.invalidate_tenant(tenant_id)
        logger.info(f"Cache invalidé pour tenant {tenant_id}: {deleted_count} clés supprimées")
    
    @classmethod
    def increment_counter(cls, tenant_id: str, numbering_id: str) -> bool:
        """
        Incrémente le compteur d'une configuration de numérotation
        
        Args:
            tenant_id: ID du tenant
            numbering_id: ID de la configuration de numérotation
            
        Returns:
            True si l'incrémentation a réussi
        """
        try:
            tenant_service_url = getattr(settings, 'TENANT_SERVICE_URL', 'http://localhost:8001')
            
            response = requests.patch(
                f"{tenant_service_url}/api/tenants/document_numbering/{numbering_id}/increment/",
                headers={'X-Tenant-ID': tenant_id},
                timeout=cls.TIMEOUT
            )
            response.raise_for_status()
            
            # OPTIMISATION PHASE 2: Mise à jour intelligente du cache
            # Au lieu d'invalider tout le cache, mettre à jour localement
            response_data = response.json()
            new_counter = response_data.get('new_counter')
            
            # OPTIMISATION PHASE 2: Invalidation sélective intelligente
            # Au lieu d'invalider tout le cache tenant, on invalide plus fréquemment
            # mais on garde les bénéfices du cache pour les autres types de documents
            if new_counter:
                logger.info(f"Compteur incrémenté: {numbering_id} -> {new_counter}")
            
            # Invalidation plus douce: on accepte que le cache soit rafraîchi
            # moins souvent pour préserver les performances
            cls.invalidate_cache(tenant_id)
            
            logger.info(f"Compteur incrémenté avec succès pour numbering {numbering_id}")
            return True
            
        except requests.RequestException as e:
            logger.error(f"Erreur incrémentation compteur {numbering_id}: {e}")
            return False
        except Exception as e:
            logger.error(f"Erreur inattendue incrémentation compteur {numbering_id}: {e}")
            return False
    
    @classmethod
    def _get_default_config(cls, tenant_id: str) -> Dict[str, Any]:
        """
        Configuration par défaut en cas d'erreur de communication
        
        Args:
            tenant_id: ID du tenant
            
        Returns:
            Dict contenant une configuration par défaut
        """
        return {
            'id': tenant_id,
            'name': 'Tenant par défaut',
            'document_numbering': [],
            'vat_rates': [],  # Plus de taux hardcodés - configuration requise
            'payment_terms': [
                {
                    'label': '30 jours',
                    'days': 30,
                    'is_default': True,
                    'is_active': True
                }
            ],
            '_is_fallback': True  # Indicateur que c'est une config par défaut
        }
    
    @classmethod
    def _create_default_numbering(cls, tenant_id: str, document_type: str) -> Dict[str, Any]:
        """
        Crée une configuration de numérotation par défaut
        
        Args:
            tenant_id: ID du tenant
            document_type: Type de document
            
        Returns:
            Dict contenant une configuration de numérotation par défaut
        """
        defaults = {
            'quote': {'prefix': 'DEV', 'padding': 3},
            'invoice': {'prefix': 'FAC', 'padding': 3},
            'credit_note': {'prefix': 'AV', 'padding': 3}
        }
        
        config = defaults.get(document_type, {'prefix': 'DOC', 'padding': 3})
        
        # Essayer de créer la config dans le tenant-service
        try:
            tenant_service_url = getattr(settings, 'TENANT_SERVICE_URL', 'http://localhost:8001')
            
            response = requests.post(
                f"{tenant_service_url}/api/tenants/document_numbering/",
                headers={'X-Tenant-ID': tenant_id},
                json={
                    'document_type': document_type,
                    **config,
                    'include_year': True,
                    'include_month': False,
                    'include_day': False,
                    'separator': '-',
                    'custom_format': ''
                },
                timeout=cls.TIMEOUT
            )
            
            if response.status_code in [200, 201]:
                created_config = response.json()
                logger.info(f"Config par défaut créée pour {document_type} tenant {tenant_id}")
                return created_config
                
        except requests.RequestException as e:
            logger.warning(f"Impossible de créer config par défaut dans tenant-service: {e}")
        
        # Configuration de fallback locale
        return {
            'id': f'fallback_{tenant_id}_{document_type}',
            'tenant_id': tenant_id,
            'document_type': document_type,
            'next_number': 1,
            **config,
            'include_year': True,
            'include_month': False,
            'include_day': False,
            'separator': '-',
            'custom_format': '',
            'reset_yearly': True,
            'reset_monthly': False,
            '_is_fallback': True  # Indicateur que c'est une config par défaut
        }
    
    @classmethod
    def test_connection(cls) -> Dict[str, Any]:
        """
        Test la connexion au tenant-service
        
        Returns:
            Dict contenant le statut de la connexion
        """
        try:
            tenant_service_url = getattr(settings, 'TENANT_SERVICE_URL', 'http://localhost:8001')
            
            response = requests.get(
                f"{tenant_service_url}/api/health/",
                timeout=cls.TIMEOUT
            )
            response.raise_for_status()
            
            health_data = response.json()
            logger.info("Connexion au tenant-service OK")
            
            return {
                'status': 'ok',
                'service': health_data.get('service', 'tenant-service'),
                'version': health_data.get('version', 'unknown'),
                'url': tenant_service_url
            }
            
        except requests.RequestException as e:
            logger.error(f"Erreur connexion tenant-service: {e}")
            return {
                'status': 'error',
                'error': str(e),
                'url': getattr(settings, 'TENANT_SERVICE_URL', 'http://localhost:8001')
            }
        except Exception as e:
            logger.error(f"Erreur inattendue test connexion: {e}")
            return {
                'status': 'error',
                'error': str(e),
                'url': getattr(settings, 'TENANT_SERVICE_URL', 'http://localhost:8001')
            }


class TenantConfigCache:
    """
    Utilitaires pour la gestion du cache des configurations tenant
    """
    
    @staticmethod
    def get_cache_stats() -> Dict[str, Any]:
        """
        Retourne les statistiques du cache tenant
        
        Returns:
            Dict contenant les statistiques du cache
        """
        try:
            # Note: Cette implémentation dépend du backend de cache utilisé
            # Pour Redis, on pourrait utiliser des commandes spécifiques
            return {
                'backend': str(cache.__class__.__name__),
                'timeout': TenantConfigClient.CACHE_TIMEOUT,
                'message': 'Statistiques de cache disponibles selon le backend'
            }
        except Exception as e:
            return {
                'error': str(e),
                'backend': 'unknown'
            }
    
    @staticmethod
    def clear_all_tenant_cache():
        """
        Efface tout le cache lié aux configurations tenant
        """
        try:
            # Note: Implémentation basique - dans un vrai projet,
            # on utiliserait des patterns pour effacer sélectivement
            cache.clear()
            logger.info("Tout le cache tenant a été effacé")
            return True
        except Exception as e:
            logger.error(f"Erreur effacement cache: {e}")
            return False