"""
Optimisations de performance pour la génération PDF
Mise en cache avancée, pool de ressources et optimisations mémoire
"""
import logging
import time
import threading
from typing import Dict, Any, Optional, List, Tuple
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from functools import lru_cache, wraps
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta
import hashlib
import weakref
import gc

from django.core.cache import cache
from django.conf import settings
from django.utils import timezone

logger = logging.getLogger(__name__)


@dataclass
class PerformanceMetrics:
    """Métriques de performance pour la génération PDF"""
    total_generations: int = 0
    cache_hits: int = 0
    cache_misses: int = 0
    avg_generation_time: float = 0.0
    avg_html_render_time: float = 0.0
    avg_pdf_generation_time: float = 0.0
    memory_usage_mb: float = 0.0
    recent_generation_times: deque = field(default_factory=lambda: deque(maxlen=100))
    errors_count: int = 0
    last_reset: datetime = field(default_factory=timezone.now)


class MemoryManager:
    """Gestionnaire de mémoire pour optimiser l'utilisation des ressources"""
    
    def __init__(self, max_memory_mb: int = 512):
        self.max_memory_mb = max_memory_mb
        self._cached_objects = weakref.WeakValueDictionary()
        self._lock = threading.Lock()
        
    def track_object(self, key: str, obj: Any) -> None:
        """Suit un objet en mémoire"""
        with self._lock:
            self._cached_objects[key] = obj
    
    def cleanup_if_needed(self) -> bool:
        """Nettoie la mémoire si nécessaire"""
        try:
            import psutil
            process = psutil.Process()
            memory_mb = process.memory_info().rss / 1024 / 1024
            
            if memory_mb > self.max_memory_mb:
                with self._lock:
                    self._cached_objects.clear()
                gc.collect()
                logger.info(f"Nettoyage mémoire effectué. Avant: {memory_mb:.2f}MB")
                return True
                
        except ImportError:
            # psutil non disponible, nettoyage basique
            if len(self._cached_objects) > 100:
                with self._lock:
                    self._cached_objects.clear()
                gc.collect()
                return True
                
        return False
    
    def get_memory_usage(self) -> float:
        """Retourne l'utilisation mémoire en MB"""
        try:
            import psutil
            process = psutil.Process()
            return process.memory_info().rss / 1024 / 1024
        except ImportError:
            return 0.0


class ResourcePool:
    """Pool de ressources réutilisables pour WeasyPrint"""
    
    def __init__(self, max_size: int = 5):
        self.max_size = max_size
        self._pool = deque()
        self._lock = threading.Lock()
        self._created_count = 0
    
    def get_font_config(self):
        """Récupère une configuration de police du pool"""
        with self._lock:
            if self._pool:
                return self._pool.popleft()
            
            # Créer une nouvelle config si le pool est vide
            if self._created_count < self.max_size:
                config = self._create_font_config()
                self._created_count += 1
                return config
                
        return None
    
    def return_font_config(self, config):
        """Remet une configuration de police dans le pool"""
        if config:
            with self._lock:
                if len(self._pool) < self.max_size:
                    self._pool.append(config)
    
    def _create_font_config(self):
        """Crée une nouvelle configuration de police"""
        try:
            from weasyprint.text.fonts import FontConfiguration
            
            font_config = FontConfiguration()
            
            # Ajouter les polices personnalisées
            fonts_dir = Path(__file__).parent.parent / 'static' / 'fonts'
            if fonts_dir.exists():
                for font_file in fonts_dir.glob('*.ttf'):
                    try:
                        font_config.add_font_face(font_file)
                    except Exception as e:
                        logger.warning(f"Impossible de charger la police {font_file}: {e}")
            
            return font_config
            
        except ImportError:
            return None


class CacheStrategy:
    """Stratégie de mise en cache avancée"""
    
    def __init__(self):
        self.html_cache_ttl = 900  # 15 minutes
        self.pdf_cache_ttl = 1800  # 30 minutes
        self.css_cache_ttl = 3600  # 1 heure
        
    def get_html_cache_key(self, template_id: str, variables_hash: str, tenant_id: str) -> str:
        """Génère une clé de cache pour HTML"""
        return f"html_cache:{template_id}:{variables_hash}:{tenant_id}"
    
    def get_pdf_cache_key(self, html_hash: str, options_hash: str, tenant_id: str) -> str:
        """Génère une clé de cache pour PDF"""
        return f"pdf_cache:{html_hash}:{options_hash}:{tenant_id}"
    
    def get_css_cache_key(self, styles_hash: str) -> str:
        """Génère une clé de cache pour CSS"""
        return f"css_cache:{styles_hash}"
    
    def cache_html(self, key: str, html_content: str) -> bool:
        """Met en cache du contenu HTML"""
        try:
            cache.set(key, html_content, self.html_cache_ttl)
            return True
        except Exception as e:
            logger.warning(f"Erreur cache HTML: {e}")
            return False
    
    def get_cached_html(self, key: str) -> Optional[str]:
        """Récupère du HTML depuis le cache"""
        try:
            return cache.get(key)
        except Exception:
            return None
    
    def cache_pdf(self, key: str, pdf_bytes: bytes, metadata: Dict[str, Any]) -> bool:
        """Met en cache un PDF avec ses métadonnées"""
        try:
            cache_data = {
                'pdf_bytes': pdf_bytes,
                'metadata': metadata,
                'cached_at': timezone.now().isoformat()
            }
            cache.set(key, cache_data, self.pdf_cache_ttl)
            return True
        except Exception as e:
            logger.warning(f"Erreur cache PDF: {e}")
            return False
    
    def get_cached_pdf(self, key: str) -> Optional[Tuple[bytes, Dict[str, Any]]]:
        """Récupère un PDF depuis le cache"""
        try:
            cache_data = cache.get(key)
            if cache_data:
                return cache_data['pdf_bytes'], cache_data['metadata']
        except Exception:
            pass
        return None


class PerformanceOptimizer:
    """Optimiseur de performance principal"""
    
    def __init__(self):
        self.metrics = PerformanceMetrics()
        self.memory_manager = MemoryManager()
        self.resource_pool = ResourcePool()
        self.cache_strategy = CacheStrategy()
        self.executor = ThreadPoolExecutor(max_workers=3, thread_name_prefix="pdf_gen")
        self._lock = threading.Lock()
    
    def time_operation(self, operation_name: str):
        """Décorateur pour mesurer le temps d'exécution"""
        def decorator(func):
            @wraps(func)
            def wrapper(*args, **kwargs):
                start_time = time.time()
                try:
                    result = func(*args, **kwargs)
                    execution_time = time.time() - start_time
                    self._record_timing(operation_name, execution_time)
                    return result
                except Exception as e:
                    self.metrics.errors_count += 1
                    raise
            return wrapper
        return decorator
    
    def _record_timing(self, operation: str, duration: float) -> None:
        """Enregistre une mesure de temps"""
        with self._lock:
            self.metrics.recent_generation_times.append(duration)
            
            if operation == "pdf_generation":
                # Mettre à jour la moyenne glissante
                recent_times = list(self.metrics.recent_generation_times)
                if recent_times:
                    self.metrics.avg_generation_time = sum(recent_times) / len(recent_times)
    
    def optimize_html_generation(self, template_hash: str, variables: Dict[str, Any], tenant_id: str):
        """Optimise la génération HTML avec cache"""
        variables_hash = hashlib.md5(str(sorted(variables.items())).encode()).hexdigest()[:16]
        cache_key = self.cache_strategy.get_html_cache_key(template_hash, variables_hash, tenant_id)
        
        # Vérifier le cache
        cached_html = self.cache_strategy.get_cached_html(cache_key)
        if cached_html:
            self.metrics.cache_hits += 1
            return cached_html, True
        
        self.metrics.cache_misses += 1
        return None, False
    
    def optimize_pdf_generation(self, html_hash: str, options: Dict[str, Any], tenant_id: str):
        """Optimise la génération PDF avec cache"""
        options_hash = hashlib.md5(str(sorted(options.items())).encode()).hexdigest()[:16]
        cache_key = self.cache_strategy.get_pdf_cache_key(html_hash, options_hash, tenant_id)
        
        # Vérifier le cache
        cached_result = self.cache_strategy.get_cached_pdf(cache_key)
        if cached_result:
            pdf_bytes, metadata = cached_result
            metadata['from_cache'] = True
            self.metrics.cache_hits += 1
            return pdf_bytes, metadata, True
        
        self.metrics.cache_misses += 1
        return None, None, False
    
    def store_html_cache(self, template_hash: str, variables_hash: str, tenant_id: str, html_content: str):
        """Stocke du HTML dans le cache"""
        cache_key = self.cache_strategy.get_html_cache_key(template_hash, variables_hash, tenant_id)
        self.cache_strategy.cache_html(cache_key, html_content)
    
    def store_pdf_cache(self, html_hash: str, options_hash: str, tenant_id: str, 
                       pdf_bytes: bytes, metadata: Dict[str, Any]):
        """Stocke un PDF dans le cache"""
        cache_key = self.cache_strategy.get_pdf_cache_key(html_hash, options_hash, tenant_id)
        self.cache_strategy.cache_pdf(cache_key, pdf_bytes, metadata)
    
    def get_font_config(self):
        """Récupère une configuration de police optimisée"""
        return self.resource_pool.get_font_config()
    
    def return_font_config(self, config):
        """Remet une configuration de police dans le pool"""
        self.resource_pool.return_font_config(config)
    
    def should_cleanup_memory(self) -> bool:
        """Vérifie si un nettoyage mémoire est nécessaire"""
        return self.memory_manager.cleanup_if_needed()
    
    def get_performance_report(self) -> Dict[str, Any]:
        """Génère un rapport de performance"""
        memory_usage = self.memory_manager.get_memory_usage()
        
        cache_hit_rate = 0.0
        total_requests = self.metrics.cache_hits + self.metrics.cache_misses
        if total_requests > 0:
            cache_hit_rate = (self.metrics.cache_hits / total_requests) * 100
        
        return {
            'total_generations': self.metrics.total_generations,
            'cache_hit_rate_percent': round(cache_hit_rate, 2),
            'cache_hits': self.metrics.cache_hits,
            'cache_misses': self.metrics.cache_misses,
            'avg_generation_time_ms': round(self.metrics.avg_generation_time * 1000, 2),
            'memory_usage_mb': round(memory_usage, 2),
            'errors_count': self.metrics.errors_count,
            'recent_generation_count': len(self.metrics.recent_generation_times),
            'pool_status': {
                'font_configs_available': len(self.resource_pool._pool),
                'font_configs_created': self.resource_pool._created_count
            },
            'uptime_hours': round((timezone.now() - self.metrics.last_reset).total_seconds() / 3600, 2)
        }
    
    def reset_metrics(self):
        """Remet à zéro les métriques"""
        with self._lock:
            self.metrics = PerformanceMetrics()
            logger.info("Métriques de performance réinitialisées")
    
    def shutdown(self):
        """Ferme proprement l'optimiseur"""
        self.executor.shutdown(wait=True)
        logger.info("Optimiseur de performance fermé")


# Instance globale
performance_optimizer = PerformanceOptimizer()


# Fonctions utilitaires

def optimize_for_production():
    """Configure l'optimiseur pour la production"""
    # Augmenter les TTL de cache
    performance_optimizer.cache_strategy.html_cache_ttl = 1800  # 30 minutes
    performance_optimizer.cache_strategy.pdf_cache_ttl = 3600   # 1 heure
    performance_optimizer.cache_strategy.css_cache_ttl = 7200   # 2 heures
    
    logger.info("Optimiseur configuré pour la production")


@lru_cache(maxsize=128)
def get_cached_css_variables(styles_hash: str) -> str:
    """Cache LRU pour les variables CSS"""
    # Cette fonction sera appelée par le générateur CSS
    # Le décorateur @lru_cache gère automatiquement le cache
    return styles_hash


def warm_up_cache(templates_data: List[Dict[str, Any]], tenant_ids: List[str]):
    """Préchauffage du cache avec les templates les plus utilisés"""
    logger.info(f"Préchauffage du cache pour {len(templates_data)} templates et {len(tenant_ids)} tenants")
    
    # Cette fonction sera implémentée selon les besoins spécifiques
    # Elle peut être appelée au démarrage ou de façon périodique
    pass


def cleanup_expired_cache():
    """Nettoie les entrées de cache expirées"""
    # Django cache gère automatiquement l'expiration
    # Cette fonction peut être utilisée pour un nettoyage manuel si nécessaire
    performance_optimizer.memory_manager.cleanup_if_needed()
    logger.info("Nettoyage de cache expiré effectué")