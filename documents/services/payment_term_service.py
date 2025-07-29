import json
import logging
import requests
from typing import Dict, List, Any, Optional
from django.conf import settings
from django.core.cache import cache

logger = logging.getLogger(__name__)

class PaymentTermService:
    """
    Service pour gérer les conditions de paiement avec cache Redis
    """
    
    # Clés de cache et TTL
    CACHE_KEY_PREFIX = "payment_terms"
    CACHE_TTL = getattr(settings, 'PAYMENT_TERMS_CACHE_TTL', 300)  # 5 minutes par défaut
    
    # Configuration des timeouts
    TIMEOUT = getattr(settings, 'TENANT_SERVICE_TIMEOUT', 5)
    
    @classmethod
    def get_active_payment_terms(cls, tenant_id: str) -> List[Dict[str, Any]]:
        """
        Récupère les conditions de paiement actives pour un tenant
        avec mise en cache Redis
        
        Args:
            tenant_id: ID du tenant
            
        Returns:
            Liste des conditions de paiement actives
        """
        cache_key = f"{cls.CACHE_KEY_PREFIX}:{tenant_id}"
        
        # Vérifier si les données sont en cache
        cached_data = cache.get(cache_key)
        if cached_data:
            logger.info(f"Cache hit pour les conditions de paiement du tenant {tenant_id}")
            return json.loads(cached_data)
        
        logger.info(f"Cache miss pour les conditions de paiement du tenant {tenant_id}")
        
        # Si pas en cache, récupérer depuis le tenant-service
        payment_terms = cls._fetch_payment_terms_from_service(tenant_id)
        
        # Mettre en cache
        if payment_terms:
            cache.set(cache_key, json.dumps(payment_terms), cls.CACHE_TTL)
        
        return payment_terms
    
    @classmethod
    def _fetch_payment_terms_from_service(cls, tenant_id: str) -> List[Dict[str, Any]]:
        """
        Récupère les conditions de paiement depuis le tenant-service
        
        Args:
            tenant_id: ID du tenant
            
        Returns:
            Liste des conditions de paiement
        """
        try:
            tenant_service_url = getattr(settings, 'TENANT_SERVICE_URL', 'http://localhost:8001')
            
            response = requests.get(
                f"{tenant_service_url}/api/payment_terms/",
                headers={'X-Tenant-ID': tenant_id},
                timeout=cls.TIMEOUT
            )
            
            if response.status_code == 200:
                payment_terms = response.json()
                logger.info(f"Récupération de {len(payment_terms)} conditions de paiement pour le tenant {tenant_id}")
                return payment_terms
            else:
                logger.warning(f"Erreur lors de la récupération des conditions de paiement: {response.status_code}")
                return cls._get_default_payment_terms()
                
        except requests.RequestException as e:
            logger.error(f"Erreur de connexion au tenant-service: {e}")
            return cls._get_default_payment_terms()
    
    @classmethod
    def _get_default_payment_terms(cls) -> List[Dict[str, Any]]:
        """
        Retourne des conditions de paiement par défaut en cas d'erreur
        
        Returns:
            Liste des conditions de paiement par défaut
        """
        return [
            {
                'id': 'default_0',
                'label': 'Paiement comptant',
                'days': 0,
                'description': 'Paiement à réception de facture',
                'is_default': False,
                'is_active': True
            },
            {
                'id': 'default_30',
                'label': '30 jours',
                'days': 30,
                'description': 'Paiement à 30 jours',
                'is_default': True,
                'is_active': True
            },
            {
                'id': 'default_45',
                'label': '45 jours',
                'days': 45,
                'description': 'Paiement à 45 jours',
                'is_default': False,
                'is_active': True
            },
            {
                'id': 'default_60',
                'label': '60 jours',
                'days': 60,
                'description': 'Paiement à 60 jours',
                'is_default': False,
                'is_active': True
            }
        ]
    
    @classmethod
    def invalidate_cache(cls, tenant_id: str) -> None:
        """
        Invalide le cache des conditions de paiement pour un tenant
        
        Args:
            tenant_id: ID du tenant
        """
        cache_key = f"{cls.CACHE_KEY_PREFIX}:{tenant_id}"
        cache.delete(cache_key)
        logger.info(f"Cache des conditions de paiement invalidé pour le tenant {tenant_id}")
    
    @classmethod
    def get_payment_term_by_id(cls, tenant_id: str, payment_term_id: str) -> Optional[Dict[str, Any]]:
        """
        Récupère une condition de paiement par son ID
        
        Args:
            tenant_id: ID du tenant
            payment_term_id: ID de la condition de paiement
            
        Returns:
            Condition de paiement ou None si non trouvée
        """
        payment_terms = cls.get_active_payment_terms(tenant_id)
        for term in payment_terms:
            if term.get('id') == payment_term_id:
                return term
        return None
    
    @classmethod
    def get_default_payment_term(cls, tenant_id: str) -> Dict[str, Any]:
        """
        Récupère la condition de paiement par défaut
        
        Args:
            tenant_id: ID du tenant
            
        Returns:
            Condition de paiement par défaut
        """
        payment_terms = cls.get_active_payment_terms(tenant_id)
        
        # Chercher la condition marquée comme défaut
        for term in payment_terms:
            if term.get('is_default'):
                return term
        
        # Si aucune n'est marquée par défaut, prendre la première
        if payment_terms:
            return payment_terms[0]
        
        # Si aucune condition n'est disponible, retourner une condition par défaut
        return {
            'id': 'default_30',
            'label': '30 jours',
            'days': 30,
            'description': 'Paiement à 30 jours',
            'is_default': True,
            'is_active': True
        } 