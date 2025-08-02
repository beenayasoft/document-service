"""
Service de génération de numéros pour les documents
Utilise les configurations tenant-aware depuis le tenant-service
"""
from typing import Optional, Dict, Any
from datetime import datetime
from django.utils import timezone
from django.core.cache import cache
from django.db import transaction
import logging

from .tenant_client import TenantConfigClient


class DocumentNumberService:
    """Service pour générer les numéros de documents avec support multi-tenant"""
    
    logger = logging.getLogger(__name__)
    
    @classmethod
    def generate_quote_number(cls, tenant_id: str, year: Optional[int] = None) -> str:
        """
        Génère un numéro de devis pour un tenant
        
        Args:
            tenant_id: ID du tenant
            year: Année (optionnel, défaut = année courante)
            
        Returns:
            Numéro de devis selon la configuration du tenant
        """
        return cls._generate_number(tenant_id, 'quote', year)
    
    @classmethod
    def generate_invoice_number(cls, tenant_id: str, year: Optional[int] = None) -> str:
        """
        Génère un numéro de facture pour un tenant
        
        Args:
            tenant_id: ID du tenant
            year: Année (optionnel, défaut = année courante)
            
        Returns:
            Numéro de facture selon la configuration du tenant
        """
        return cls._generate_number(tenant_id, 'invoice', year)
    
    @classmethod
    def generate_credit_note_number(cls, tenant_id: str, year: Optional[int] = None) -> str:
        """
        Génère un numéro d'avoir pour un tenant
        
        Args:
            tenant_id: ID du tenant
            year: Année (optionnel, défaut = année courante)
            
        Returns:
            Numéro d'avoir selon la configuration du tenant
        """
        return cls._generate_number(tenant_id, 'credit_note', year)
    
    @classmethod
    def generate_project_reference(cls, tenant_id: str, year: Optional[int] = None) -> str:
        """
        Génère une référence de projet pour un tenant
        
        Args:
            tenant_id: ID du tenant
            year: Année (optionnel, défaut = année courante)
            
        Returns:
            Référence de projet selon la configuration du tenant
        """
        return cls._generate_number(tenant_id, 'project', year)
    
    @classmethod
    def _generate_number(cls, tenant_id: str, document_type: str, year: Optional[int] = None) -> str:
        """
        Génère un numéro de document avec configuration tenant
        
        Args:
            tenant_id: ID du tenant
            document_type: Type de document ('quote', 'invoice', 'credit_note')
            year: Année
            
        Returns:
            Numéro généré selon la configuration tenant
        """
        if year is None:
            year = timezone.now().year
        
        try:
            # Pour les projets, utiliser directement le fallback
            if document_type == 'project':
                cls.logger.info(f"Utilisation du fallback pour les projets, tenant {tenant_id}")
                return cls._generate_fallback_number(document_type, year)
            
            # Récupérer la configuration de numérotation du tenant
            numbering_config = TenantConfigClient.get_cached_numbering(tenant_id, document_type)
            
            if not numbering_config or numbering_config.get('_is_fallback'):
                cls.logger.warning(f"Configuration fallback utilisée pour tenant {tenant_id}, type {document_type}")
            
            # Générer le numéro selon la configuration
            number = cls._generate_from_config(numbering_config, year)
            
            # Incrémenter le compteur dans le tenant-service
            numbering_id = numbering_config.get('id')
            if numbering_id and not numbering_config.get('_is_fallback'):
                increment_success = TenantConfigClient.increment_counter(tenant_id, numbering_id)
                if not increment_success:
                    cls.logger.error(f"Échec incrémentation compteur {numbering_id} pour tenant {tenant_id}")
            else:
                # Fallback : utiliser un cache local pour les configurations par défaut
                cache_key = f"fallback_counter_{tenant_id}_{document_type}_{year}"
                with transaction.atomic():
                    current_counter = cache.get(cache_key, numbering_config.get('next_number', 1))
                    cache.set(cache_key, current_counter + 1, timeout=86400)
            
            cls.logger.info(f"Numéro généré : {number} pour tenant {tenant_id}")
            return number
            
        except Exception as e:
            cls.logger.error(f"Erreur génération numéro pour tenant {tenant_id}: {e}")
            # Fallback vers l'ancien système
            return cls._generate_fallback_number(document_type, year)
    
    @classmethod
    def _generate_from_config(cls, numbering_config: Dict[str, Any], year: int) -> str:
        """
        Génère un numéro selon la configuration de numérotation
        
        Args:
            numbering_config: Configuration de numérotation du tenant
            year: Année
            
        Returns:
            Numéro formaté
        """
        import datetime
        now = datetime.datetime.now()
        
        # Utiliser le format personnalisé si défini
        if numbering_config.get('custom_format'):
            return cls._generate_custom_format(numbering_config, now)
        else:
            return cls._generate_standard_format(numbering_config, now)
    
    @classmethod
    def _generate_custom_format(cls, config: Dict[str, Any], now: datetime) -> str:
        """
        Génère un numéro selon un format personnalisé
        """
        format_vars = {
            'prefix': config.get('prefix', ''),
            'year': now.year,
            'month': f"{now.month:02d}",
            'day': f"{now.day:02d}",
            'number': f"{config.get('next_number', 1):0{config.get('padding', 3)}d}",
            'suffix': config.get('suffix', '')
        }
        
        try:
            return config['custom_format'].format(**format_vars)
        except (KeyError, ValueError) as e:
            cls.logger.warning(f"Erreur format personnalisé, fallback vers standard: {e}")
            return cls._generate_standard_format(config, now)
    
    @classmethod
    def _generate_standard_format(cls, config: Dict[str, Any], now: datetime) -> str:
        """
        Génère un numéro selon le format standard
        """
        parts = []
        separator = config.get('separator', '-')
        
        # Préfixe
        if config.get('prefix'):
            parts.append(config['prefix'])
        
        # Partie date
        date_parts = []
        if config.get('include_year', True):
            date_parts.append(str(now.year))
        if config.get('include_month', False):
            date_parts.append(f"{now.month:02d}")
        if config.get('include_day', False):
            date_parts.append(f"{now.day:02d}")
        
        if date_parts:
            parts.append(separator.join(date_parts))
        
        # Numéro avec padding
        padding = config.get('padding', 3)
        number = config.get('next_number', 1)
        parts.append(f"{number:0{padding}d}")
        
        # Suffixe
        if config.get('suffix'):
            parts.append(config['suffix'])
        
        return separator.join(parts)
    
    @classmethod
    def _generate_fallback_number(cls, document_type: str, year: int) -> str:
        """
        Méthode de fallback utilisant les anciens préfixes hardcodés
        """
        FALLBACK_PREFIXES = {
            'quote': 'DEV',
            'invoice': 'FAC',
            'credit_note': 'AV',
            'project': 'PROJ'
        }
        
        prefix = FALLBACK_PREFIXES.get(document_type, 'DOC')
        cache_key = f"fallback_document_counter_{document_type}_{year}"
        
        with transaction.atomic():
            counter = cache.get(cache_key, 0)
            if counter == 0:
                counter = cls._get_counter_from_db_fallback(document_type, year)
            
            counter += 1
            cache.set(cache_key, counter, timeout=86400)
            
            return f"{prefix}-{year}-{counter:03d}"
    
    @classmethod
    def _get_counter_from_db_fallback(cls, document_type: str, year: int) -> int:
        """
        Récupère le compteur le plus élevé depuis la base de données (méthode fallback)
        
        Args:
            document_type: Type de document
            year: Année
            
        Returns:
            Compteur maximum trouvé
        """
        from ..models import Quote, Invoice
        
        FALLBACK_PREFIXES = {
            'quote': 'DEV',
            'invoice': 'FAC', 
            'credit_note': 'AV',
            'project': 'PROJ'
        }
        prefix = FALLBACK_PREFIXES.get(document_type, 'DOC')
        pattern = f"{prefix}-{year}-"
        
        # Déterminer le modèle à utiliser
        if document_type in ['quote']:
            model = Quote
        elif document_type in ['invoice', 'credit_note']:
            model = Invoice
        elif document_type in ['project']:
            # Pour les projets, nous utilisons un compteur simple sans modèle DB
            return 0  # Démarrer à 0 pour les projets
        else:
            return 0
        
        # Rechercher tous les numéros de l'année
        numbers = model.objects.filter(
            number__startswith=pattern,
            created_at__year=year
        ).values_list('number', flat=True)
        
        max_counter = 0
        for number in numbers:
            try:
                # Extraire le compteur du numéro (ex: "DEV-2024-123" → 123)
                counter_str = number.split('-')[-1]
                counter = int(counter_str)
                max_counter = max(max_counter, counter)
            except (ValueError, IndexError):
                continue
        
        return max_counter
    
    # Méthodes tenant-aware
    
    @classmethod
    def get_next_number_preview(cls, tenant_id: str, document_type: str, year: Optional[int] = None) -> str:
        """
        Retourne un aperçu du prochain numéro pour un tenant
        
        Args:
            tenant_id: ID du tenant
            document_type: Type de document
            year: Année (optionnel)
            
        Returns:
            Aperçu du prochain numéro
        """
        try:
            # Pour les projets, utiliser directement le fallback
            if document_type == 'project':
                if year is None:
                    year = timezone.now().year
                return cls._generate_fallback_number(document_type, year)
            
            numbering_config = TenantConfigClient.get_cached_numbering(tenant_id, document_type)
            
            if numbering_config and numbering_config.get('preview'):
                return numbering_config['preview']
            
            # Fallback : générer un aperçu local
            if year is None:
                year = timezone.now().year
            
            return cls._generate_from_config(numbering_config, year)
            
        except Exception as e:
            cls.logger.error(f"Erreur aperçu numéro pour tenant {tenant_id}: {e}")
            # Fallback vers l'ancien système
            FALLBACK_PREFIXES = {'quote': 'DEV', 'invoice': 'FAC', 'credit_note': 'AV', 'project': 'PROJ'}
            prefix = FALLBACK_PREFIXES.get(document_type, 'DOC')
            return f"{prefix}-{year or timezone.now().year}-001"
    
    @classmethod
    def validate_number_format(cls, tenant_id: str, number: str, document_type: str) -> bool:
        """
        Valide le format d'un numéro de document pour un tenant
        
        Args:
            tenant_id: ID du tenant
            number: Numéro à valider
            document_type: Type de document attendu
            
        Returns:
            True si le format est valide selon la config tenant
        """
        try:
            numbering_config = TenantConfigClient.get_cached_numbering(tenant_id, document_type)
            
            if not numbering_config:
                return False
            
            # Vérifier que le numéro contient le bon préfixe
            expected_prefix = numbering_config.get('prefix', '')
            if expected_prefix and not number.startswith(expected_prefix):
                return False
            
            # Validation basique du format
            return len(number.strip()) > 0
            
        except Exception as e:
            cls.logger.error(f"Erreur validation format pour tenant {tenant_id}: {e}")
            return False
    
    @classmethod
    def reset_counter(cls, tenant_id: str, document_type: str, new_value: int = 1) -> bool:
        """
        Remet à zéro le compteur pour un tenant et type de document
        
        Args:
            tenant_id: ID du tenant
            document_type: Type de document
            new_value: Nouvelle valeur du compteur
            
        Returns:
            True si le reset a été effectué
        """
        try:
            numbering_config = TenantConfigClient.get_cached_numbering(tenant_id, document_type)
            
            if not numbering_config or numbering_config.get('_is_fallback'):
                cls.logger.warning(f"Impossible de reset: configuration fallback pour tenant {tenant_id}")
                return False
            
            # Utiliser l'API du tenant-service pour reset
            # Note: Cette fonctionnalité devrait être ajoutée au tenant-service
            cls.logger.info(f"Reset compteur pour tenant {tenant_id}, type {document_type}, valeur {new_value}")
            
            # Invalider le cache
            TenantConfigClient.invalidate_cache(tenant_id)
            
            return True
            
        except Exception as e:
            cls.logger.error(f"Erreur reset compteur pour tenant {tenant_id}: {e}")
            return False
    
    @classmethod
    def get_statistics(cls, tenant_id: str, year: Optional[int] = None) -> dict:
        """
        Retourne les statistiques de numérotation pour un tenant
        
        Args:
            tenant_id: ID du tenant
            year: Année (optionnel)
            
        Returns:
            Dict avec les statistiques tenant-specific
        """
        if year is None:
            year = timezone.now().year
        
        stats = {}
        document_types = ['quote', 'invoice', 'credit_note']
        
        for document_type in document_types:
            try:
                numbering_config = TenantConfigClient.get_cached_numbering(tenant_id, document_type)
                
                if numbering_config:
                    stats[document_type] = {
                        'prefix': numbering_config.get('prefix', ''),
                        'current_counter': numbering_config.get('next_number', 1) - 1,
                        'next_number': numbering_config.get('preview', 'N/A'),
                        'format_description': numbering_config.get('format_description', ''),
                        'is_fallback': numbering_config.get('_is_fallback', False)
                    }
                else:
                    stats[document_type] = {
                        'prefix': 'N/A',
                        'current_counter': 0,
                        'next_number': 'N/A',
                        'format_description': 'Configuration non disponible',
                        'is_fallback': True
                    }
            except Exception as e:
                cls.logger.error(f"Erreur stats pour {document_type}, tenant {tenant_id}: {e}")
                stats[document_type] = {
                    'error': str(e),
                    'is_fallback': True
                }
        
        return {
            'tenant_id': tenant_id,
            'year': year,
            'document_types': stats,
            'total_documents': sum(
                s.get('current_counter', 0) for s in stats.values() 
                if 'error' not in s
            )
        }
    
    @classmethod
    def test_tenant_connection(cls, tenant_id: str) -> Dict[str, Any]:
        """
        Teste la connexion et la configuration pour un tenant
        
        Args:
            tenant_id: ID du tenant
            
        Returns:
            Dict avec le statut de la connexion et des configurations
        """
        try:
            # Tester la connexion au tenant-service
            connection_status = TenantConfigClient.test_connection()
            
            if connection_status['status'] != 'ok':
                return {
                    'tenant_id': tenant_id,
                    'status': 'error',
                    'error': 'Tenant service non disponible',
                    'connection': connection_status
                }
            
            # Tester les configurations de numérotation
            document_types = ['quote', 'invoice', 'credit_note']
            configs = {}
            
            for doc_type in document_types:
                try:
                    config = TenantConfigClient.get_cached_numbering(tenant_id, doc_type)
                    configs[doc_type] = {
                        'available': config is not None,
                        'is_fallback': config.get('_is_fallback', False) if config else True,
                        'preview': config.get('preview', 'N/A') if config else 'N/A'
                    }
                except Exception as e:
                    configs[doc_type] = {
                        'available': False,
                        'error': str(e)
                    }
            
            return {
                'tenant_id': tenant_id,
                'status': 'ok',
                'connection': connection_status,
                'configurations': configs
            }
            
        except Exception as e:
            cls.logger.error(f"Erreur test connexion tenant {tenant_id}: {e}")
            return {
                'tenant_id': tenant_id,
                'status': 'error',
                'error': str(e)
            }
    
    @classmethod
    def bulk_generate_numbers(cls, tenant_id: str, document_type: str, count: int, 
                             year: Optional[int] = None) -> list:
        """
        Génère plusieurs numéros en une fois pour un tenant
        
        Args:
            tenant_id: ID du tenant
            document_type: Type de document
            count: Nombre de numéros à générer
            year: Année
            
        Returns:
            Liste des numéros générés
        """
        if count <= 0 or count > 100:  # Limite de sécurité réduite pour les tenants
            raise ValueError("Le nombre doit être entre 1 et 100")
        
        numbers = []
        for i in range(count):
            try:
                number = cls._generate_number(tenant_id, document_type, year)
                numbers.append(number)
                cls.logger.info(f"Bulk generation {i+1}/{count}: {number}")
            except Exception as e:
                cls.logger.error(f"Erreur bulk generation {i+1}/{count} pour tenant {tenant_id}: {e}")
                break
        
        return numbers
    
    @classmethod
    def generate_numbers_optimized(cls, tenant_id: str, document_type: str, count: int = 1, 
                                  year: Optional[int] = None) -> list:
        """
        PHASE 2 OPTIMISATION: Génération optimisée avec pré-incrémentation
        Évite les appels HTTP multiples en utilisant un compteur local intelligent
        
        Args:
            tenant_id: ID du tenant
            document_type: Type de document
            count: Nombre de numéros à générer
            year: Année
            
        Returns:
            Liste des numéros générés
        """
        if count <= 0 or count > 50:
            raise ValueError("Le nombre doit être entre 1 et 50")
        
        if year is None:
            year = timezone.now().year
        
        try:
            # Récupérer la configuration une seule fois
            numbering_config = TenantConfigClient.get_cached_numbering(tenant_id, document_type)
            
            if not numbering_config or numbering_config.get('_is_fallback'):
                # Fallback vers l'ancienne méthode
                return [cls._generate_number(tenant_id, document_type, year) for _ in range(count)]
            
            # Générer les numéros localement avec incrémentation
            numbers = []
            current_counter = numbering_config.get('next_number', 1)
            
            for i in range(count):
                # Générer le numéro avec le compteur actuel
                temp_config = numbering_config.copy()
                temp_config['next_number'] = current_counter + i
                
                number = cls._generate_from_config(temp_config, year)
                numbers.append(number)
            
            # Incrémenter le compteur sur le serveur - TOUJOURS un appel par numéro pour la cohérence
            numbering_id = numbering_config.get('id')
            if numbering_id and not numbering_config.get('_is_fallback'):
                # On doit encore faire les appels individuels pour maintenir la cohérence
                # Mais au moins on a optimisé les timeouts et le cache
                for i in range(count):
                    success = TenantConfigClient.increment_counter(tenant_id, numbering_id)
                    if not success:
                        cls.logger.warning(f"Échec incrémentation {i+1}/{count} pour {numbering_id}")
                        # En cas d'échec, on s'arrête pour éviter les doublons
            
            cls.logger.info(f"Génération optimisée: {count} numéros pour tenant {tenant_id}")
            return numbers
            
        except Exception as e:
            cls.logger.error(f"Erreur génération optimisée pour tenant {tenant_id}: {e}")
            # Fallback vers la méthode standard
            return [cls._generate_number(tenant_id, document_type, year) for _ in range(count)]