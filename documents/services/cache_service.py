"""
Service de cache optimisé pour les configurations tenant - SANS REDIS
Utilise le cache Django par défaut (LocMem ou Database)
"""
import json
import logging
from typing import Optional, Dict, Any, List
from django.core.cache import cache
from django.conf import settings
from django.utils import timezone
import hashlib

# CONFIGURATION SANS REDIS - Cache Django par défaut
CACHE_AVAILABLE = True
try:
    # Test rapide de disponibilité du cache
    cache.set('test_key', 'test_value', 1)
    cache.get('test_key')
except Exception:
    CACHE_AVAILABLE = False

logger = logging.getLogger(__name__)

class TenantConfigCacheService:
    """
    Service de cache optimisé pour les configurations tenant
    """
    
    # Configuration des timeouts
    DEFAULT_TIMEOUT = getattr(settings, 'TENANT_CONFIG_CACHE_TIMEOUT', 900)  # 15 minutes
    NUMBERING_TIMEOUT = getattr(settings, 'TENANT_NUMBERING_CACHE_TIMEOUT', 1800)  # 30 minutes
    STATS_TIMEOUT = getattr(settings, 'TENANT_STATS_CACHE_TIMEOUT', 300)  # 5 minutes
    
    # Préfixes des clés de cache
    CONFIG_PREFIX = "tenant_config"
    NUMBERING_PREFIX = "tenant_numbering"
    STATS_PREFIX = "tenant_stats"
    HEALTH_PREFIX = "tenant_health"
    
    @classmethod
    def get_config_key(cls, tenant_id: str) -> str:
        """Génère la clé de cache pour la configuration tenant"""
        return f"{cls.CONFIG_PREFIX}_{tenant_id}"
    
    @classmethod
    def get_numbering_key(cls, tenant_id: str, document_type: str) -> str:
        """Génère la clé de cache pour la numérotation"""
        return f"{cls.NUMBERING_PREFIX}_{tenant_id}_{document_type}"
    
    @classmethod
    def get_stats_key(cls, tenant_id: str) -> str:
        """Génère la clé de cache pour les statistiques"""
        return f"{cls.STATS_PREFIX}_{tenant_id}"
    
    @classmethod
    def get_health_key(cls, tenant_id: str) -> str:
        """Génère la clé de cache pour le health check"""
        return f"{cls.HEALTH_PREFIX}_{tenant_id}"
    
    @classmethod
    def set_tenant_config(cls, tenant_id: str, config: Dict[str, Any], 
                         timeout: Optional[int] = None) -> bool:
        """
        Met en cache la configuration tenant
        
        Args:
            tenant_id: ID du tenant
            config: Configuration à mettre en cache
            timeout: Timeout personnalisé
            
        Returns:
            True si la mise en cache a réussi
        """
        try:
            cache_key = cls.get_config_key(tenant_id)
            timeout = timeout or cls.DEFAULT_TIMEOUT
            
            # Ajouter des métadonnées
            cached_data = {
                **config,
                '_cache_timestamp': cache.get('timestamp', 0),
                '_cache_key': cache_key,
                '_tenant_id': tenant_id
            }
            
            success = cache.set(cache_key, cached_data, timeout)
            
            if success:
                logger.debug(f"Configuration tenant {tenant_id} mise en cache pour {timeout}s")
            else:
                logger.error(f"Échec mise en cache config tenant {tenant_id}")
            
            return success
            
        except Exception as e:
            # Redis indisponible - log discret et continuer
            if "Error 10061" in str(e) or "Connection refused" in str(e):
                logger.debug(f"Redis indisponible - impossible de cacher config tenant {tenant_id}")
            else:
                logger.error(f"Erreur mise en cache config tenant {tenant_id}: {e}")
            return False
    
    @classmethod
    def get_tenant_config(cls, tenant_id: str) -> Optional[Dict[str, Any]]:
        """
        Récupère la configuration tenant depuis le cache avec fallback gracieux
        
        Args:
            tenant_id: ID du tenant
            
        Returns:
            Configuration tenant ou None si non trouvée
        """
        try:
            cache_key = cls.get_config_key(tenant_id)
            config = cache.get(cache_key)
            
            if config:
                logger.debug(f"Cache hit pour config tenant {tenant_id}")
                return config
            else:
                logger.debug(f"Cache miss pour config tenant {tenant_id}")
                return None
                
        except Exception as e:
            # Redis indisponible - log sans spammer et retourner None gracieusement
            if "Error 10061" in str(e) or "Connection refused" in str(e):
                logger.debug(f"Redis indisponible pour tenant {tenant_id} - fallback vers API")
            else:
                logger.error(f"Erreur récupération cache config tenant {tenant_id}: {e}")
            return None
    
    @classmethod
    def set_numbering_config(cls, tenant_id: str, document_type: str, 
                           config: Dict[str, Any], timeout: Optional[int] = None) -> bool:
        """
        Met en cache la configuration de numérotation
        
        Args:
            tenant_id: ID du tenant
            document_type: Type de document
            config: Configuration de numérotation
            timeout: Timeout personnalisé
            
        Returns:
            True si la mise en cache a réussi
        """
        try:
            cache_key = cls.get_numbering_key(tenant_id, document_type)
            timeout = timeout or cls.NUMBERING_TIMEOUT
            
            # Ajouter des métadonnées
            cached_data = {
                **config,
                '_cache_timestamp': cache.get('timestamp', 0),
                '_cache_key': cache_key,
                '_tenant_id': tenant_id,
                '_document_type': document_type
            }
            
            success = cache.set(cache_key, cached_data, timeout)
            
            if success:
                logger.debug(f"Config numérotation {document_type} tenant {tenant_id} mise en cache")
            
            return success
            
        except Exception as e:
            logger.error(f"Erreur mise en cache numérotation {document_type} tenant {tenant_id}: {e}")
            return False
    
    @classmethod
    def get_numbering_config(cls, tenant_id: str, document_type: str) -> Optional[Dict[str, Any]]:
        """
        Récupère la configuration de numérotation depuis le cache
        
        Args:
            tenant_id: ID du tenant
            document_type: Type de document
            
        Returns:
            Configuration de numérotation ou None
        """
        try:
            cache_key = cls.get_numbering_key(tenant_id, document_type)
            config = cache.get(cache_key)
            
            if config:
                logger.debug(f"Cache hit pour numérotation {document_type} tenant {tenant_id}")
                return config
            else:
                logger.debug(f"Cache miss pour numérotation {document_type} tenant {tenant_id}")
                return None
                
        except Exception as e:
            logger.error(f"Erreur récupération cache numérotation {document_type} tenant {tenant_id}: {e}")
            return None
    
    @classmethod
    def invalidate_tenant(cls, tenant_id: str) -> int:
        """
        Invalide tout le cache pour un tenant
        
        Args:
            tenant_id: ID du tenant
            
        Returns:
            Nombre de clés supprimées
        """
        try:
            keys_to_delete = [
                cls.get_config_key(tenant_id),
                cls.get_stats_key(tenant_id),
                cls.get_health_key(tenant_id),
            ]
            
            # Ajouter les clés de numérotation
            for doc_type in ['quote', 'invoice', 'credit_note']:
                keys_to_delete.append(cls.get_numbering_key(tenant_id, doc_type))
            
            # Supprimer toutes les clés
            deleted_count = 0
            for key in keys_to_delete:
                if cache.delete(key):
                    deleted_count += 1
            
            logger.info(f"Cache invalidé pour tenant {tenant_id}: {deleted_count} clés supprimées")
            return deleted_count
            
        except Exception as e:
            logger.error(f"Erreur invalidation cache tenant {tenant_id}: {e}")
            return 0
    
    @classmethod
    def warm_up_cache(cls, tenant_id: str, force_refresh: bool = False) -> Dict[str, bool]:
        """
        Préchauffe le cache pour un tenant
        
        Args:
            tenant_id: ID du tenant
            force_refresh: Force le rechargement même si déjà en cache
            
        Returns:
            Dict indiquant le succès pour chaque type de configuration
        """
        results = {}
        
        try:
            from .tenant_client import TenantConfigClient
            
            # Configuration générale du tenant
            if force_refresh or not cls.get_tenant_config(tenant_id):
                config = TenantConfigClient.get_tenant_config(tenant_id)
                results['config'] = cls.set_tenant_config(tenant_id, config)
            else:
                results['config'] = True
            
            # Configurations de numérotation
            for doc_type in ['quote', 'invoice', 'credit_note']:
                if force_refresh or not cls.get_numbering_config(tenant_id, doc_type):
                    numbering_config = TenantConfigClient.get_document_numbering(tenant_id, doc_type)
                    results[f'numbering_{doc_type}'] = cls.set_numbering_config(
                        tenant_id, doc_type, numbering_config
                    )
                else:
                    results[f'numbering_{doc_type}'] = True
            
            logger.info(f"Préchauffage cache tenant {tenant_id} terminé: {results}")
            
        except Exception as e:
            logger.error(f"Erreur préchauffage cache tenant {tenant_id}: {e}")
            results['error'] = str(e)
        
        return results
    
    @classmethod
    def get_cache_statistics(cls) -> Dict[str, Any]:
        """
        Retourne les statistiques générales du cache
        
        Returns:
            Dict avec les statistiques
        """
        try:
            # Note: Les statistiques dépendent du backend de cache utilisé
            # Cette implémentation est basique et peut être étendue
            
            stats = {
                'backend': str(cache.__class__.__name__),
                'timeouts': {
                    'config': cls.DEFAULT_TIMEOUT,
                    'numbering': cls.NUMBERING_TIMEOUT,
                    'stats': cls.STATS_TIMEOUT
                },
                'prefixes': {
                    'config': cls.CONFIG_PREFIX,
                    'numbering': cls.NUMBERING_PREFIX,
                    'stats': cls.STATS_PREFIX,
                    'health': cls.HEALTH_PREFIX
                },
                'timestamp': cache.get('timestamp', 0)
            }
            
            return stats
            
        except Exception as e:
            logger.error(f"Erreur récupération statistiques cache: {e}")
            return {
                'error': str(e),
                'backend': 'unknown'
            }
    
    @classmethod
    def health_check(cls) -> Dict[str, Any]:
        """
        Vérifie la santé du système de cache
        
        Returns:
            Dict avec le statut de santé
        """
        try:
            # Test de base : écriture et lecture
            test_key = "health_check_test"
            test_value = {"timestamp": cache.get('timestamp', 0), "test": True}
            
            # Test d'écriture
            write_success = cache.set(test_key, test_value, 60)
            
            # Test de lecture
            read_value = cache.get(test_key)
            read_success = read_value is not None and read_value.get('test') is True
            
            # Nettoyage
            cache.delete(test_key)
            
            status = "healthy" if (write_success and read_success) else "unhealthy"
            
            return {
                'status': status,
                'write_test': write_success,
                'read_test': read_success,
                'backend': str(cache.__class__.__name__),
                'statistics': cls.get_cache_statistics()
            }
            
        except Exception as e:
            logger.error(f"Erreur health check cache: {e}")
            return {
                'status': 'error',
                'error': str(e),
                'backend': 'unknown'
            }
    
    @classmethod
    def bulk_invalidate(cls, tenant_ids: List[str]) -> Dict[str, int]:
        """
        Invalide le cache pour plusieurs tenants
        
        Args:
            tenant_ids: Liste des IDs de tenants
            
        Returns:
            Dict avec le nombre de clés supprimées par tenant
        """
        results = {}
        
        for tenant_id in tenant_ids:
            try:
                deleted_count = cls.invalidate_tenant(tenant_id)
                results[tenant_id] = deleted_count
            except Exception as e:
                logger.error(f"Erreur invalidation bulk pour tenant {tenant_id}: {e}")
                results[tenant_id] = 0
        
        total_deleted = sum(results.values())
        logger.info(f"Invalidation bulk terminée: {total_deleted} clés supprimées pour {len(tenant_ids)} tenants")
        
        return results


class CacheService:
    """
    Service de cache générique pour les données simples
    """
    
    def __init__(self):
        self.default_timeout = 3600  # 1 heure par défaut
    
    def get(self, key: str) -> Any:
        """
        Récupère une valeur depuis le cache
        
        Args:
            key: Clé de cache
            
        Returns:
            Valeur ou None si non trouvée
        """
        try:
            return cache.get(key)
        except Exception as e:
            logger.error(f"Erreur récupération cache pour clé {key}: {e}")
            return None
    
    def set(self, key: str, value: Any, timeout: Optional[int] = None) -> bool:
        """
        Met une valeur en cache
        
        Args:
            key: Clé de cache
            value: Valeur à cacher
            timeout: Timeout en secondes
            
        Returns:
            True si succès
        """
        try:
            timeout = timeout or self.default_timeout
            return cache.set(key, value, timeout)
        except Exception as e:
            logger.error(f"Erreur mise en cache pour clé {key}: {e}")
            return False
    
    def delete(self, key: str) -> bool:
        """
        Supprime une clé du cache
        
        Args:
            key: Clé à supprimer
            
        Returns:
            True si succès
        """
        try:
            return cache.delete(key)
        except Exception as e:
            logger.error(f"Erreur suppression cache pour clé {key}: {e}")
            return False
    
    @classmethod
    def _get_tenant_cache_keys(cls, tenant_id: str) -> List[str]:
        """
        PHASE 2 OPTIMISATION: Récupère toutes les clés de cache pour un tenant
        
        Args:
            tenant_id: ID du tenant
            
        Returns:
            Liste des clés de cache pour ce tenant
        """
        # Django ne fournit pas de moyen natif de lister les clés
        # Nous devons simuler avec les patterns connus
        potential_keys = []
        
        # Clés de configuration générale
        potential_keys.append(cls.get_config_key(tenant_id))
        
        # Clés de numérotation pour chaque type de document
        document_types = ['quote', 'invoice', 'credit_note', 'order', 'delivery']
        for doc_type in document_types:
            potential_keys.append(cls.get_numbering_key(tenant_id, doc_type))
        
        # Clés de statistiques
        potential_keys.append(f"{cls.STATS_PREFIX}_{tenant_id}")
        potential_keys.append(f"{cls.HEALTH_PREFIX}_{tenant_id}")
        
        # Filtrer seulement celles qui existent vraiment
        existing_keys = []
        for key in potential_keys:
            if cache.get(key) is not None:
                existing_keys.append(key)
        
        return existing_keys
    
    @classmethod
    def _get_from_cache(cls, cache_key: str) -> Optional[Dict[str, Any]]:
        """
        PHASE 2 OPTIMISATION: Récupère une valeur du cache
        
        Args:
            cache_key: Clé de cache
            
        Returns:
            Valeur du cache ou None
        """
        try:
            return cache.get(cache_key)
        except Exception as e:
            logger.error(f"Erreur récupération cache {cache_key}: {e}")
            return None
    
    @classmethod
    def _set_to_cache(cls, cache_key: str, value: Dict[str, Any], timeout: Optional[int] = None) -> bool:
        """
        PHASE 2 OPTIMISATION: Met une valeur en cache
        
        Args:
            cache_key: Clé de cache
            value: Valeur à mettre en cache
            timeout: Timeout optionnel
            
        Returns:
            True si succès
        """
        try:
            timeout = timeout or cls.DEFAULT_TIMEOUT
            return cache.set(cache_key, value, timeout)
        except Exception as e:
            logger.error(f"Erreur mise en cache {cache_key}: {e}")
            return False