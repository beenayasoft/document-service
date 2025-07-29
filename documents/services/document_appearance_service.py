"""
Service de récupération des paramètres d'apparence des documents tenant-spécifiques
"""
import logging
from typing import Dict, Any, Optional
from django.core.cache import cache
from django.conf import settings
from .tenant_client import TenantConfigClient
from .cache_service import CacheService

logger = logging.getLogger(__name__)


class DocumentAppearanceService:
    """
    Service pour récupérer et mettre en cache les paramètres d'apparence
    des documents spécifiques à chaque tenant
    """
    
    CACHE_KEY_PREFIX = "document_appearance"
    CACHE_TTL = 1800  # 30 minutes
    
    def __init__(self):
        self.tenant_client = TenantConfigClient()
        self.cache_service = CacheService()
    
    def get_appearance_settings(self, tenant_id: str) -> Dict[str, Any]:
        """
        Récupère les paramètres d'apparence complets pour un tenant
        
        Args:
            tenant_id: ID du tenant
            
        Returns:
            Dict contenant tous les paramètres d'apparence pour la génération PDF
            
        Format retourné:
        {
            'document_template': 'modern' | 'classic' | 'minimal',
            'primary_color': '#1B333F',
            'show_logo': True,
            'show_client_address': True,
            'show_project_info': True,
            'show_notes': True,
            'show_payment_terms': True,
            'show_bank_details': True,
            'show_signature_area': True,
            'logo_position': 'left',
            'font_family': 'Arial',
            'font_size': 11,
            'line_spacing': 1.5,
            'margin_top': 25,
            'margin_right': 20,
            'margin_bottom': 25,
            'margin_left': 20,
            'header_text': '',
            'footer_text': '',
            'legal_mentions': '',
            'table_header_color': '#f8f9fa',
            'table_alternate_color': '#f2f2f2'
        }
        """
        if not tenant_id:
            logger.warning("Tenant ID manquant pour get_appearance_settings")
            return self._get_fallback_appearance_settings()
        
        cache_key = f"{self.CACHE_KEY_PREFIX}:{tenant_id}"
        
        # Vérifier le cache L1 (Redis)
        cached_settings = self.cache_service.get(cache_key)
        if cached_settings:
            logger.debug(f"Paramètres d'apparence récupérés du cache pour tenant {tenant_id}")
            return cached_settings
        
        # Récupérer depuis tenant-service
        try:
            logger.info(f"Récupération des paramètres d'apparence depuis tenant-service pour tenant {tenant_id}")
            appearance_settings = self._fetch_from_tenant_service(tenant_id)
            
            # Mettre en cache
            self.cache_service.set(cache_key, appearance_settings, self.CACHE_TTL)
            
            logger.info(f"Paramètres d'apparence récupérés et mis en cache pour tenant {tenant_id}")
            return appearance_settings
            
        except Exception as e:
            logger.error(f"Erreur lors de la récupération des paramètres d'apparence pour tenant {tenant_id}: {str(e)}")
            return self._get_fallback_appearance_settings()
    
    def _fetch_from_tenant_service(self, tenant_id: str) -> Dict[str, Any]:
        """
        Récupère les paramètres d'apparence depuis le tenant-service
        
        Args:
            tenant_id: ID du tenant
            
        Returns:
            Dict avec les paramètres formatés
        """
        import requests
        
        tenant_service_url = getattr(settings, 'TENANT_SERVICE_URL', 'http://localhost:8001')
        timeout = getattr(settings, 'TENANT_SERVICE_TIMEOUT', 5)
        
        try:
            response = requests.get(
                f"{tenant_service_url}/api/document_appearance/",
                headers={'X-Tenant-ID': tenant_id},
                timeout=timeout
            )
            response.raise_for_status()
            
            appearance_data = response.json()
            logger.info(f"Paramètres d'apparence récupérés depuis tenant-service pour tenant {tenant_id}")
            
            return appearance_data
            
        except requests.RequestException as e:
            logger.error(f"Erreur HTTP lors de la récupération des paramètres d'apparence: {e}")
            raise Exception(f"Impossible de récupérer les paramètres d'apparence depuis tenant-service: {e}")
        except Exception as e:
            logger.error(f"Erreur inattendue lors de la récupération des paramètres d'apparence: {e}")
            raise
    
    def _get_fallback_appearance_settings(self) -> Dict[str, Any]:
        """
        Retourne des paramètres d'apparence par défaut en cas d'erreur
        
        Returns:
            Dict avec des valeurs par défaut
        """
        logger.info("Utilisation des paramètres d'apparence par défaut (fallback)")
        
        return {
            'document_template': 'modern',
            'primary_color': '#1B333F',
            'show_logo': True,
            'show_client_address': True,
            'show_project_info': True,
            'show_notes': True,
            'show_payment_terms': True,
            'show_bank_details': True,
            'show_signature_area': True,
            'logo_position': 'left',
            'font_family': 'Arial',
            'font_size': 11,
            'line_spacing': 1.5,
            'margin_top': 25,
            'margin_right': 20,
            'margin_bottom': 25,
            'margin_left': 20,
            'header_text': '',
            'footer_text': '',
            'legal_mentions': '',
            'table_header_color': '#f8f9fa',
            'table_alternate_color': '#f2f2f2',
            'show_payment_details': True,
            'show_legal_mentions': True,
        }
    
    def invalidate_cache(self, tenant_id: str) -> bool:
        """
        Invalide le cache des paramètres d'apparence pour un tenant
        
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
            logger.info(f"Cache invalidé pour les paramètres d'apparence du tenant {tenant_id}")
            return True
        except Exception as e:
            logger.error(f"Erreur lors de l'invalidation du cache pour tenant {tenant_id}: {str(e)}")
            return False
    
    def refresh_appearance_settings(self, tenant_id: str) -> Dict[str, Any]:
        """
        Force le rechargement des paramètres d'apparence depuis le tenant-service
        
        Args:
            tenant_id: ID du tenant
            
        Returns:
            Dict avec les paramètres actualisés
        """
        # Invalider le cache
        self.invalidate_cache(tenant_id)
        
        # Récupérer les nouvelles données
        return self.get_appearance_settings(tenant_id)
    
    def get_template_config(self, template_name: str) -> Dict[str, Any]:
        """
        Retourne la configuration spécifique à un template
        
        Args:
            template_name: Nom du template ('modern', 'classic', 'minimal')
            
        Returns:
            Dict avec la configuration du template
        """
        template_configs = {
            'modern': {
                'use_gradients': True,
                'rounded_corners': True,
                'shadow_effects': True,
                'accent_colors': True,
            },
            'classic': {
                'use_gradients': False,
                'rounded_corners': False,
                'shadow_effects': False,
                'accent_colors': False,
                'border_style': 'solid',
            },
            'minimal': {
                'use_gradients': False,
                'rounded_corners': False,
                'shadow_effects': False,
                'accent_colors': False,
                'minimal_spacing': True,
                'clean_lines': True,
            }
        }
        
        return template_configs.get(template_name, template_configs['modern'])


# Instance globale du service
document_appearance_service = DocumentAppearanceService()