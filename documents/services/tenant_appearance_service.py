"""
Service pour récupérer les paramètres d'apparence des documents depuis le tenant-service
"""
import logging
import requests
from typing import Dict, Any, Optional
from django.core.cache import cache
from django.conf import settings

logger = logging.getLogger(__name__)


class TenantAppearanceService:
    """Service pour gérer les paramètres d'apparence des documents par tenant"""
    
    CACHE_TIMEOUT = 300  # 5 minutes
    
    def __init__(self):
        self.tenant_service_url = getattr(settings, 'TENANT_SERVICE_URL', 'http://tenant-service:8002')
    
    def get_document_appearance(self, tenant_id: str) -> Dict[str, Any]:
        """
        Récupère les paramètres d'apparence des documents pour un tenant
        
        Args:
            tenant_id: ID du tenant
            
        Returns:
            Dict contenant les paramètres d'apparence
        """
        if not tenant_id:
            logger.warning("Aucun tenant_id fourni, utilisation des paramètres par défaut")
            return self._get_default_appearance_settings()
        
        # Vérifier le cache d'abord
        cache_key = f"tenant_appearance_{tenant_id}"
        cached_settings = cache.get(cache_key)
        
        if cached_settings is not None:
            logger.info(f"Paramètres d'apparence récupérés depuis le cache pour tenant {tenant_id}")
            return cached_settings
        
        try:
            # Appel API vers le tenant-service
            url = f"{self.tenant_service_url}/api/tenants/document-appearance/"
            headers = {
                'X-Tenant-ID': tenant_id,
                'Content-Type': 'application/json'
            }
            
            logger.info(f"Récupération des paramètres d'apparence pour tenant {tenant_id}")
            response = requests.get(url, headers=headers, timeout=10)
            
            if response.status_code == 200:
                appearance_data = response.json()
                logger.info(f"Paramètres d'apparence récupérés avec succès pour tenant {tenant_id}")
                
                # Mettre en cache
                cache.set(cache_key, appearance_data, self.CACHE_TIMEOUT)
                
                return appearance_data
            
            elif response.status_code == 404:
                logger.warning(f"Configuration d'apparence non trouvée pour tenant {tenant_id}, création des paramètres par défaut")
                # Le tenant existe mais n'a pas encore de configuration d'apparence
                # Retourner les valeurs par défaut et laisser l'API créer la configuration au besoin
                default_settings = self._get_default_appearance_settings()
                cache.set(cache_key, default_settings, self.CACHE_TIMEOUT)
                return default_settings
            
            else:
                logger.error(f"Erreur lors de la récupération des paramètres d'apparence: {response.status_code} - {response.text}")
                return self._get_default_appearance_settings()
        
        except requests.exceptions.RequestException as e:
            logger.error(f"Erreur de connexion au tenant-service: {str(e)}")
            return self._get_default_appearance_settings()
        
        except Exception as e:
            logger.error(f"Erreur inattendue lors de la récupération des paramètres d'apparence: {str(e)}")
            return self._get_default_appearance_settings()
    
    def _get_default_appearance_settings(self) -> Dict[str, Any]:
        """
        Retourne les paramètres d'apparence par défaut
        
        Returns:
            Dict avec les paramètres par défaut
        """
        return {
            'document_template': 'modern',
            'primary_color': '#1B333F',
            'font_family': 'Inter',
            'font_size': 11,
            'line_spacing': 1.4,
            
            # Logo et en-tête
            'show_logo': True,
            'logo_size': 12,  # Converti en unités compatibles avec DocumentPreview
            'logo_position': 'left',
            'show_company_name': True,
            'show_company_slogan': True,
            
            # Éléments du document
            'show_company_address': True,
            'show_company_phone': True,
            'show_company_email': True,
            'show_company_siret': True,
            'show_company_vat': True,
            'show_client_address': True,
            'show_project_info': True,
            'show_notes': True,
            'show_payment_terms': True,
            'show_bank_details': True,
            'show_signature_area': True,
            'show_legal_mentions': True,
            
            # Styles de tableaux
            'table_border_style': 'rounded',
            'table_border_horizontal': True,
            'table_border_vertical': True,
            'table_border_width': 1,
            'table_border_color': '#dee2e6',
            'section_contrast': True,
            'show_section_subtotals': True,
            'table_row_padding': 8,
            'table_column_spacing': 12,
            
            # Couleurs
            'table_header_color': '#f8f9fa',
            'table_alternate_color': '#f2f2f2',
            'section_contrast_color': '#f8f9fa',
            
            # Marges (en mm pour PDF)
            'margin_top': 25,
            'margin_right': 20,
            'margin_bottom': 25,
            'margin_left': 20,
        }
    
    def invalidate_cache(self, tenant_id: str):
        """
        Invalide le cache des paramètres d'apparence pour un tenant
        
        Args:
            tenant_id: ID du tenant
        """
        cache_key = f"tenant_appearance_{tenant_id}"
        cache.delete(cache_key)
        logger.info(f"Cache des paramètres d'apparence invalidé pour tenant {tenant_id}")
    
    def convert_to_pdf_appearance(self, appearance_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Convertit les paramètres d'apparence du format tenant-service vers le format PDF service
        
        Args:
            appearance_data: Paramètres depuis le tenant-service
            
        Returns:
            Dict formaté pour le PDF service
        """
        # Adapter le logoSize pour le PDF (multiplier par 4 pour avoir la taille en pixels)
        logo_size_pdf = appearance_data.get('logo_size', 12) * 4
        
        return {
            # Styles généraux
            'primary_color': appearance_data.get('primary_color', '#1B333F'),
            'font_family': appearance_data.get('font_family', 'Inter'),
            'font_size': appearance_data.get('font_size', 11),
            'line_spacing': appearance_data.get('line_spacing', 1.4),
            
            # Logo et en-tête
            'show_logo': appearance_data.get('show_logo', True),
            'logo_size_px': logo_size_pdf,
            'logo_position': appearance_data.get('logo_position', 'left'),
            'show_company_name': appearance_data.get('show_company_name', True),
            'show_company_slogan': appearance_data.get('show_company_slogan', True),
            
            # Informations entreprise
            'show_company_address': appearance_data.get('show_company_address', True),
            'show_company_phone': appearance_data.get('show_company_phone', True),
            'show_company_email': appearance_data.get('show_company_email', True),
            'show_company_siret': appearance_data.get('show_company_siret', True),
            'show_company_vat': appearance_data.get('show_company_vat', True),
            
            # Éléments du document
            'show_client_address': appearance_data.get('show_client_address', True),
            'show_project_info': appearance_data.get('show_project_info', True),
            'show_notes': appearance_data.get('show_notes', True),
            'show_payment_terms': appearance_data.get('show_payment_terms', True),
            'show_bank_details': appearance_data.get('show_bank_details', True),
            'show_signature_area': appearance_data.get('show_signature_area', True),
            'show_legal_mentions': appearance_data.get('show_legal_mentions', True),
            
            # Styles de tableaux
            'table_border_style': appearance_data.get('table_border_style', 'rounded'),
            'table_border_horizontal': appearance_data.get('table_border_horizontal', True),
            'table_border_vertical': appearance_data.get('table_border_vertical', True),
            'table_border_width': appearance_data.get('table_border_width', 1),
            'table_border_color': appearance_data.get('table_border_color', '#dee2e6'),
            'section_contrast': appearance_data.get('section_contrast', True),
            'show_section_subtotals': appearance_data.get('show_section_subtotals', True),
            'table_row_padding': appearance_data.get('table_row_padding', 8),
            'table_column_spacing': appearance_data.get('table_column_spacing', 12),
            
            # Couleurs
            'table_header_color': appearance_data.get('table_header_color', '#f8f9fa'),
            'table_alternate_color': appearance_data.get('table_alternate_color', '#f2f2f2'),
            'section_contrast_color': appearance_data.get('section_contrast_color', '#f8f9fa'),
            
            # Marges (en mm)
            'margin_top': appearance_data.get('margin_top', 25),
            'margin_right': appearance_data.get('margin_right', 20),
            'margin_bottom': appearance_data.get('margin_bottom', 25),
            'margin_left': appearance_data.get('margin_left', 20),
        }


# Instance globale du service
tenant_appearance_service = TenantAppearanceService()