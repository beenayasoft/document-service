"""
Service de gestion des informations d'entreprise tenant-spécifiques
"""
import logging
from typing import Dict, Any, Optional
from django.core.cache import cache
from django.conf import settings
from .tenant_client import TenantConfigClient
from .cache_service import CacheService

logger = logging.getLogger(__name__)


class CompanyInfoService:
    """
    Service pour récupérer et mettre en cache les informations d'entreprise
    spécifiques à chaque tenant pour la génération de documents PDF
    """
    
    CACHE_KEY_PREFIX = "company_info"
    CACHE_TTL = 3600  # 1 heure
    
    def __init__(self):
        self.tenant_client = TenantConfigClient()
        self.cache_service = CacheService()
    
    def get_company_info(self, tenant_id: str) -> Dict[str, Any]:
        """
        Récupère les informations complètes de l'entreprise pour un tenant
        
        Args:
            tenant_id: ID du tenant
            
        Returns:
            Dict contenant toutes les informations nécessaires pour le PDF
            
        Format retourné:
        {
            'name': str,
            'address_line_1': str,
            'address_line_2': str,
            'city': str,
            'postal_code': str,
            'country': str,
            'full_address': str,
            'phone': str,
            'email': str,
            'website': str,
            'siret': str,
            'ice': str,
            'legal_form': str,
            'logo_url': str,
            'logo_data': str,  # base64
            'primary_color': str,
            'secondary_color': str,
            'accent_color': str
        }
        """
        if not tenant_id:
            logger.warning("Tenant ID manquant pour get_company_info")
            return self._get_fallback_company_info()
        
        cache_key = f"{self.CACHE_KEY_PREFIX}:{tenant_id}"
        
        # Vérifier le cache L1 (Redis)
        cached_info = self.cache_service.get(cache_key)
        if cached_info:
            logger.debug(f"Informations entreprise récupérées du cache pour tenant {tenant_id}")
            return cached_info
        
        # Récupérer depuis tenant-service
        try:
            logger.info(f"Récupération des informations entreprise depuis tenant-service pour tenant {tenant_id}")
            company_info = self._fetch_from_tenant_service(tenant_id)
            
            # Mettre en cache
            self.cache_service.set(cache_key, company_info, self.CACHE_TTL)
            
            logger.info(f"Informations entreprise récupérées et mises en cache pour tenant {tenant_id}")
            return company_info
            
        except Exception as e:
            logger.error(f"Erreur lors de la récupération des informations entreprise pour tenant {tenant_id}: {str(e)}")
            return self._get_fallback_company_info()
    
    def _fetch_from_tenant_service(self, tenant_id: str) -> Dict[str, Any]:
        """
        Récupère les données du tenant-service et les formate pour le PDF
        
        Args:
            tenant_id: ID du tenant
            
        Returns:
            Dict avec les informations formatées
        """
        # Récupérer les informations du tenant
        tenant_info = self.tenant_client.get_tenant_info(tenant_id)
        
        if not tenant_info:
            raise Exception("Impossible de récupérer les informations du tenant")
        
        # Extraire les informations de base du tenant
        company_info = {
            'name': tenant_info.get('name', ''),
            'address_line_1': tenant_info.get('address_line_1', ''),
            'address_line_2': tenant_info.get('address_line_2', ''),
            'city': tenant_info.get('city', ''),
            'postal_code': tenant_info.get('postal_code', ''),
            'country': tenant_info.get('country', 'France'),
            'full_address': tenant_info.get('full_address', ''),
            'phone': tenant_info.get('phone', ''),
            'email': tenant_info.get('email', ''),
            'website': tenant_info.get('website', ''),
            'siret': tenant_info.get('siret', ''),
            'ice': tenant_info.get('ice', ''),
            'legal_form': tenant_info.get('legal_form', ''),
        }
        
        # Extraire les paramètres visuels depuis les settings du tenant
        settings_info = tenant_info.get('settings', {})
        company_info.update({
            'logo_url': settings_info.get('logo_url', ''),
            'logo_base64': settings_info.get('logo_base64', ''),
            'primary_color': settings_info.get('primary_color', '#007bff'),
            'secondary_color': settings_info.get('secondary_color', '#6c757d'),
            'accent_color': settings_info.get('accent_color', '#28a745'),
        })
        
        # Construire l'adresse complète si elle n'est pas déjà formatée
        if not company_info['full_address']:
            address_parts = [
                company_info['address_line_1'],
                company_info['address_line_2'],
                f"{company_info['postal_code']} {company_info['city']}".strip(),
                company_info['country']
            ]
            company_info['full_address'] = ', '.join([part for part in address_parts if part])
        
        return company_info
    
    def _get_fallback_company_info(self) -> Dict[str, Any]:
        """
        Retourne des informations par défaut en cas d'erreur
        
        Returns:
            Dict avec des valeurs par défaut
        """
        logger.info("Utilisation des informations entreprise par défaut (fallback)")
        
        return {
            'name': 'Votre Entreprise',
            'address_line_1': 'Adresse à configurer',
            'address_line_2': '',
            'city': 'Ville',
            'postal_code': '00000',
            'country': 'France',
            'full_address': 'Adresse à configurer, Ville 00000, France',
            'phone': 'Téléphone à configurer',
            'email': 'email@exemple.fr',
            'website': '',
            'siret': 'SIRET à configurer',
            'ice': 'ICE à configurer',
            'legal_form': '',
            'logo_url': '',
            'logo_base64': '',
            'primary_color': '#007bff',
            'secondary_color': '#6c757d',
            'accent_color': '#28a745',
        }
    
    def invalidate_cache(self, tenant_id: str) -> bool:
        """
        Invalide le cache des informations entreprise pour un tenant
        
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
            logger.info(f"Cache invalidé pour les informations entreprise du tenant {tenant_id}")
            return True
        except Exception as e:
            logger.error(f"Erreur lors de l'invalidation du cache pour tenant {tenant_id}: {str(e)}")
            return False
    
    def refresh_company_info(self, tenant_id: str) -> Dict[str, Any]:
        """
        Force le rechargement des informations entreprise depuis le tenant-service
        
        Args:
            tenant_id: ID du tenant
            
        Returns:
            Dict avec les informations actualisées
        """
        # Invalider le cache
        self.invalidate_cache(tenant_id)
        
        # Récupérer les nouvelles données
        return self.get_company_info(tenant_id)


# Instance globale du service
company_info_service = CompanyInfoService()