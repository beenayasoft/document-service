"""
Service de résolution des variables pour les templates de documents
Résout les variables dynamiques depuis les données des documents et tenant
"""
import re
import logging
from typing import Dict, Any, Optional, List, Union
from decimal import Decimal
from datetime import datetime, date
from django.utils import timezone

from ..schemas.document_template_schema import VariableContext, DocumentTemplate
from .tenant_client import TenantConfigClient
from .company_info_service import CompanyInfoService

logger = logging.getLogger(__name__)


class VariableResolver:
    """
    Service de résolution des variables dans les templates
    Convertit les variables comme 'tenant.name' en valeurs réelles
    """
    
    def __init__(self, tenant_id: str):
        self.tenant_id = tenant_id
        self.tenant_client = TenantConfigClient()
        self.company_service = CompanyInfoService()
        
        # Cache pour éviter les appels multiples
        self._cached_data = {}
        self._tenant_config = None
        self._company_info = None
    
    def resolve_template_variables(self, template: DocumentTemplate, document_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Résout toutes les variables d'un template avec les données d'un document
        
        Args:
            template: Template avec définitions des variables
            document_data: Données du document (quote, invoice, etc.)
            
        Returns:
            Dict avec toutes les variables résolues
        """
        resolved_vars = {}
        
        # Préparer les contextes de données
        self._load_tenant_data()
        self._load_company_data()
        self._prepare_document_context(document_data)
        
        # Résoudre chaque variable déclarée dans le template
        for variable in template.variables:
            try:
                value = self._resolve_variable(variable.context, variable.key, variable.default_value)
                resolved_vars[variable.full_path] = self._format_value(value, variable.data_type)
                
            except Exception as e:
                logger.warning(f"Impossible de résoudre la variable {variable.full_path}: {e}")
                resolved_vars[variable.full_path] = variable.default_value or ""
        
        # Ajouter les variables système
        resolved_vars.update(self._get_system_variables())
        
        logger.info(f"Résolu {len(resolved_vars)} variables pour template {template.name}")
        return resolved_vars
    
    def resolve_variable_string(self, text: str, variables: Dict[str, Any]) -> str:
        """
        Résout les variables dans une chaîne de texte
        
        Args:
            text: Texte contenant des variables (ex: "Bonjour {tenant.name}")
            variables: Dict des variables résolues
            
        Returns:
            Texte avec variables remplacées
        """
        if not text or not isinstance(text, str):
            return str(text) if text is not None else ""
        
        # Modèle pour capturer les variables {variable.path}
        pattern = r'\{([a-zA-Z_][a-zA-Z0-9_.]*)\}'
        
        def replace_var(match):
            var_path = match.group(1)
            return str(variables.get(var_path, f"[{var_path}]"))
        
        return re.sub(pattern, replace_var, text)
    
    def resolve_component_props(self, props: Dict[str, Any], variables: Dict[str, Any]) -> Dict[str, Any]:
        """
        Résout les variables dans les propriétés d'un composant
        
        Args:
            props: Propriétés du composant
            variables: Variables résolues
            
        Returns:
            Propriétés avec variables résolues
        """
        resolved_props = {}
        
        for key, value in props.items():
            resolved_props[key] = self._resolve_prop_value(value, variables)
        
        return resolved_props
    
    def _resolve_prop_value(self, value: Any, variables: Dict[str, Any]) -> Any:
        """Résout récursivement les variables dans une valeur"""
        if isinstance(value, str):
            # Si c'est une référence directe à une variable
            if value in variables:
                return variables[value]
            # Si c'est du texte avec des variables intégrées
            return self.resolve_variable_string(value, variables)
            
        elif isinstance(value, list):
            return [self._resolve_prop_value(item, variables) for item in value]
            
        elif isinstance(value, dict):
            return {k: self._resolve_prop_value(v, variables) for k, v in value.items()}
            
        else:
            return value
    
    def _load_tenant_data(self):
        """Charge les données du tenant"""
        if not self._tenant_config:
            self._tenant_config = self.tenant_client.get_cached_config(self.tenant_id)
            logger.debug(f"Données tenant chargées pour {self.tenant_id}")
    
    def _load_company_data(self):
        """Charge les informations d'entreprise"""
        if not self._company_info:
            self._company_info = self.company_service.get_company_info(self.tenant_id)
            logger.debug(f"Informations entreprise chargées pour {self.tenant_id}")
    
    def _prepare_document_context(self, document_data: Dict[str, Any]):
        """Prépare le contexte document avec données formatées"""
        self._cached_data['document'] = document_data.copy()
        
        # Ajouter des champs dérivés
        if 'items' in document_data:
            items = document_data['items']
            self._cached_data['items'] = {
                'count': len(items),
                'list': items,
                'has_items': len(items) > 0
            }
            
            # Calculer les totaux si pas déjà présents
            if 'totals' not in document_data:
                self._cached_data['totals'] = self._calculate_totals_from_items(items)
        
        # Ajouter les informations client/projet formatées
        self._add_formatted_client_info(document_data)
        self._add_formatted_project_info(document_data)
    
    def _resolve_variable(self, context: VariableContext, key: str, default_value: Any = None) -> Any:
        """Résout une variable spécifique selon son contexte"""
        try:
            if context == VariableContext.TENANT:
                return self._resolve_tenant_variable(key, default_value)
            elif context == VariableContext.CLIENT:
                return self._resolve_client_variable(key, default_value)
            elif context == VariableContext.PROJECT:
                return self._resolve_project_variable(key, default_value)
            elif context == VariableContext.DOCUMENT:
                return self._resolve_document_variable(key, default_value)
            elif context == VariableContext.ITEMS:
                return self._resolve_items_variable(key, default_value)
            elif context == VariableContext.TOTALS:
                return self._resolve_totals_variable(key, default_value)
            elif context == VariableContext.SYSTEM:
                return self._resolve_system_variable(key, default_value)
            else:
                logger.warning(f"Contexte de variable inconnu: {context}")
                return default_value
                
        except Exception as e:
            logger.error(f"Erreur résolution variable {context.value}.{key}: {e}")
            return default_value
    
    def _resolve_tenant_variable(self, key: str, default_value: Any) -> Any:
        """Résout une variable tenant/entreprise"""
        # D'abord essayer depuis company_info (plus riche)
        if self._company_info and key in self._company_info:
            return self._company_info[key]
        
        # Ensuite depuis tenant_config
        if self._tenant_config and key in self._tenant_config:
            return self._tenant_config[key]
        
        # Mapping spéciaux pour compatibilité
        mapping = {
            'logo_base64': lambda: self._company_info.get('logo_base64', ''),
            'logo_url': lambda: self._company_info.get('logo_url', ''),
            'full_address': lambda: self._company_info.get('full_address', ''),
            'legal_info': lambda: self._build_legal_info(),
        }
        
        if key in mapping:
            return mapping[key]()
        
        return default_value
    
    def _resolve_client_variable(self, key: str, default_value: Any) -> Any:
        """Résout une variable client"""
        client_data = self._cached_data.get('client', {})
        
        if key in client_data:
            return client_data[key]
        
        # Variables spéciales client
        if key == 'full_address':
            return self._build_client_address()
        elif key == 'display_name':
            return client_data.get('name', client_data.get('client_name', ''))
        
        # Fallback vers document.client_*
        document = self._cached_data.get('document', {})
        client_key = f'client_{key}'
        if client_key in document:
            return document[client_key]
        
        return default_value
    
    def _resolve_project_variable(self, key: str, default_value: Any) -> Any:
        """Résout une variable projet"""
        project_data = self._cached_data.get('project', {})
        
        if key in project_data:
            return project_data[key]
        
        # Fallback vers document.project_*
        document = self._cached_data.get('document', {})
        project_key = f'project_{key}'
        if project_key in document:
            return document[project_key]
        
        return default_value
    
    def _resolve_document_variable(self, key: str, default_value: Any) -> Any:
        """Résout une variable document"""
        document = self._cached_data.get('document', {})
        
        if key in document:
            return document[key]
        
        # Variables calculées
        if key == 'status_display':
            return self._get_status_display(document.get('status'))
        elif key == 'type_display':
            return self._get_document_type_display(document.get('document_type'))
        
        return default_value
    
    def _resolve_items_variable(self, key: str, default_value: Any) -> Any:
        """Résout une variable liée aux articles"""
        items_data = self._cached_data.get('items', {})
        return items_data.get(key, default_value)
    
    def _resolve_totals_variable(self, key: str, default_value: Any) -> Any:
        """Résout une variable de totaux"""
        totals_data = self._cached_data.get('totals', {})
        
        if key in totals_data:
            return totals_data[key]
        
        # Fallback vers document
        document = self._cached_data.get('document', {})
        total_key = f'total_{key}' if not key.startswith('total_') else key
        
        if total_key in document:
            return document[total_key]
        
        return default_value
    
    def _resolve_system_variable(self, key: str, default_value: Any) -> Any:
        """Résout une variable système"""
        system_vars = self._get_system_variables()
        full_key = f'system.{key}'
        return system_vars.get(full_key, default_value)
    
    def _get_system_variables(self) -> Dict[str, Any]:
        """Génère les variables système"""
        now = timezone.now()
        
        return {
            'system.current_date': now.date(),
            'system.current_datetime': now,
            'system.current_year': now.year,
            'system.current_month': now.month,
            'system.current_day': now.day,
            'system.page_number': 1,  # Sera remplacé lors du rendu PDF
            'system.total_pages': 1,  # Sera remplacé lors du rendu PDF
            'system.generator': 'Beenaya Document Service v1.0',
            'system.generated_at': now.isoformat(),
        }
    
    def _format_value(self, value: Any, data_type: str) -> Any:
        """Formate une valeur selon son type de données"""
        if value is None:
            return ""
        
        try:
            if data_type == "string":
                return str(value)
            elif data_type == "number":
                if isinstance(value, (int, float, Decimal)):
                    return value
                return float(value) if value else 0
            elif data_type == "date":
                if isinstance(value, str):
                    # Essayer de parser la date
                    try:
                        return datetime.fromisoformat(value.replace('Z', '+00:00')).date()
                    except:
                        return value
                elif isinstance(value, datetime):
                    return value.date()
                elif isinstance(value, date):
                    return value
                return value
            elif data_type == "boolean":
                return bool(value)
            else:
                return value
                
        except Exception as e:
            logger.warning(f"Erreur formatage valeur {value} en {data_type}: {e}")
            return value
    
    def _calculate_totals_from_items(self, items: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Calcule les totaux depuis la liste des articles"""
        total_ht = Decimal('0')
        total_vat = Decimal('0')
        
        for item in items:
            if item.get('type') not in ['chapter', 'section']:
                item_total_ht = Decimal(str(item.get('total_ht', 0)))
                item_total_ttc = Decimal(str(item.get('total_ttc', 0)))
                
                total_ht += item_total_ht
                total_vat += (item_total_ttc - item_total_ht)
        
        total_ttc = total_ht + total_vat
        
        return {
            'total_ht': float(total_ht),
            'total_vat': float(total_vat),
            'total_ttc': float(total_ttc),
            'currency': '€',  # TODO: récupérer depuis la config tenant
            'items_count': len([i for i in items if i.get('type') not in ['chapter', 'section']])
        }
    
    def _build_legal_info(self) -> str:
        """Construit les informations légales de l'entreprise"""
        parts = []
        
        if self._company_info:
            siret = self._company_info.get('siret')
            if siret:
                parts.append(f"SIRET: {siret}")
            
            ice = self._company_info.get('ice')
            if ice:
                parts.append(f"ICE: {ice}")
            
            legal_form = self._company_info.get('legal_form')
            if legal_form:
                parts.append(legal_form)
        
        return " - ".join(parts)
    
    def _build_client_address(self) -> str:
        """Construit l'adresse complète du client"""
        client_data = self._cached_data.get('client', {})
        
        if 'full_address' in client_data:
            return client_data['full_address']
        
        # Construire depuis les champs individuels
        parts = []
        for field in ['address_line_1', 'address_line_2', 'address']:
            value = client_data.get(field)
            if value:
                parts.append(value)
                break  # Prendre le premier trouvé
        
        city_parts = []
        postal_code = client_data.get('postal_code')
        city = client_data.get('city')
        
        if postal_code:
            city_parts.append(postal_code)
        if city:
            city_parts.append(city)
        
        if city_parts:
            parts.append(" ".join(city_parts))
        
        country = client_data.get('country')
        if country:
            parts.append(country)
        
        return ", ".join(parts)
    
    def _add_formatted_client_info(self, document_data: Dict[str, Any]):
        """Ajoute les informations client formatées"""
        client_info = {
            'name': document_data.get('client_name', ''),
            'address': document_data.get('client_address', ''),
            'email': document_data.get('client_email', ''),
            'phone': document_data.get('client_phone', ''),
        }
        
        self._cached_data['client'] = client_info
    
    def _add_formatted_project_info(self, document_data: Dict[str, Any]):
        """Ajoute les informations projet formatées"""
        project_info = {
            'name': document_data.get('project_name', ''),
            'address': document_data.get('project_address', ''),
            'reference': document_data.get('project_reference', ''),
        }
        
        self._cached_data['project'] = project_info
    
    def _get_status_display(self, status: str) -> str:
        """Retourne l'affichage lisible du statut"""
        status_mapping = {
            # Devis
            'draft': 'Brouillon',
            'sent': 'Envoyé',
            'accepted': 'Accepté',
            'rejected': 'Refusé',
            'expired': 'Expiré',
            'cancelled': 'Annulé',
            
            # Factures
            'paid': 'Payée',
            'partially_paid': 'Partiellement payée',
            'overdue': 'En retard',
        }
        
        return status_mapping.get(status, status.capitalize() if status else '')
    
    def _get_document_type_display(self, doc_type: str) -> str:
        """Retourne l'affichage lisible du type de document"""
        type_mapping = {
            'quote': 'Devis',
            'invoice': 'Facture',
            'credit_note': 'Avoir',
            'delivery_note': 'Bon de livraison',
        }
        
        return type_mapping.get(doc_type, doc_type.capitalize() if doc_type else '')


# Fonctions utilitaires

def create_variable_resolver(tenant_id: str) -> VariableResolver:
    """Crée un resolver de variables pour un tenant"""
    return VariableResolver(tenant_id)


def resolve_template_with_document(template: DocumentTemplate, document_data: Dict[str, Any], tenant_id: str) -> Dict[str, Any]:
    """
    Fonction utilitaire pour résoudre un template avec des données de document
    
    Args:
        template: Template à résoudre
        document_data: Données du document
        tenant_id: ID du tenant
        
    Returns:
        Dict avec le template résolu (variables remplacées)
    """
    resolver = create_variable_resolver(tenant_id)
    variables = resolver.resolve_template_variables(template, document_data)
    
    # Résoudre les composants du template
    resolved_template_data = template.to_dict()
    
    def resolve_region_components(components_data):
        """Résout récursivement les composants d'une région"""
        for component in components_data:
            if 'props' in component:
                component['props'] = resolver.resolve_component_props(component['props'], variables)
            
            if 'children' in component:
                resolve_region_components(component['children'])
    
    # Résoudre toutes les régions
    for region_name, region_data in resolved_template_data.get('regions', {}).items():
        if 'components' in region_data:
            resolve_region_components(region_data['components'])
    
    return {
        'template': resolved_template_data,
        'variables': variables,
        'metadata': {
            'tenant_id': tenant_id,
            'resolved_at': timezone.now().isoformat(),
            'variables_count': len(variables)
        }
    }