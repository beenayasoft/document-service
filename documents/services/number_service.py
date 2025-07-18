"""
Service de génération de numéros pour les documents
"""
from typing import Optional
from datetime import datetime
from django.utils import timezone
from django.core.cache import cache
from django.db import transaction


class DocumentNumberService:
    """Service pour générer les numéros de documents"""
    
    # Préfixes par type de document
    PREFIXES = {
        'quote': 'DEV',
        'invoice': 'FAC',
        'credit_note': 'AV'
    }
    
    @classmethod
    def generate_quote_number(cls, year: Optional[int] = None) -> str:
        """
        Génère un numéro de devis
        
        Args:
            year: Année (optionnel, défaut = année courante)
            
        Returns:
            Numéro de devis au format DEV-2024-001
        """
        return cls._generate_number('quote', year)
    
    @classmethod
    def generate_invoice_number(cls, year: Optional[int] = None) -> str:
        """
        Génère un numéro de facture
        
        Args:
            year: Année (optionnel, défaut = année courante)
            
        Returns:
            Numéro de facture au format FAC-2024-001
        """
        return cls._generate_number('invoice', year)
    
    @classmethod
    def generate_credit_note_number(cls, year: Optional[int] = None) -> str:
        """
        Génère un numéro d'avoir
        
        Args:
            year: Année (optionnel, défaut = année courante)
            
        Returns:
            Numéro d'avoir au format AV-2024-001
        """
        return cls._generate_number('credit_note', year)
    
    @classmethod
    def _generate_number(cls, document_type: str, year: Optional[int] = None) -> str:
        """
        Génère un numéro de document
        
        Args:
            document_type: Type de document ('quote', 'invoice', 'credit_note')
            year: Année
            
        Returns:
            Numéro généré
        """
        if year is None:
            year = timezone.now().year
        
        prefix = cls.PREFIXES.get(document_type, 'DOC')
        
        # Clé de cache pour le compteur
        cache_key = f"document_counter_{document_type}_{year}"
        
        # Utiliser une transaction pour garantir l'unicité
        with transaction.atomic():
            # Récupérer le compteur depuis le cache
            counter = cache.get(cache_key, 0)
            
            # Si le compteur n'existe pas en cache, le récupérer depuis la DB
            if counter == 0:
                counter = cls._get_counter_from_db(document_type, year)
            
            # Incrémenter le compteur
            counter += 1
            
            # Vérifier l'unicité dans la DB (au cas où)
            while cls._number_exists(document_type, year, counter):
                counter += 1
            
            # Mettre à jour le cache
            cache.set(cache_key, counter, timeout=86400)  # 24h
            
            # Formater le numéro
            number = f"{prefix}-{year}-{counter:03d}"
            
            return number
    
    @classmethod
    def _get_counter_from_db(cls, document_type: str, year: int) -> int:
        """
        Récupère le compteur le plus élevé depuis la base de données
        
        Args:
            document_type: Type de document
            year: Année
            
        Returns:
            Compteur maximum trouvé
        """
        from ..models import Quote, Invoice
        
        prefix = cls.PREFIXES.get(document_type, 'DOC')
        pattern = f"{prefix}-{year}-"
        
        # Déterminer le modèle à utiliser
        if document_type in ['quote']:
            model = Quote
        elif document_type in ['invoice', 'credit_note']:
            model = Invoice
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
    
    @classmethod
    def _number_exists(cls, document_type: str, year: int, counter: int) -> bool:
        """
        Vérifie si un numéro existe déjà
        
        Args:
            document_type: Type de document
            year: Année
            counter: Compteur
            
        Returns:
            True si le numéro existe
        """
        from ..models import Quote, Invoice
        
        prefix = cls.PREFIXES.get(document_type, 'DOC')
        number = f"{prefix}-{year}-{counter:03d}"
        
        # Vérifier dans les devis
        if document_type == 'quote':
            return Quote.objects.filter(number=number).exists()
        
        # Vérifier dans les factures et avoirs
        elif document_type in ['invoice', 'credit_note']:
            return Invoice.objects.filter(number=number).exists()
        
        return False
    
    @classmethod
    def parse_document_number(cls, number: str) -> dict:
        """
        Parse un numéro de document pour extraire ses composants
        
        Args:
            number: Numéro de document (ex: "DEV-2024-123")
            
        Returns:
            Dict avec prefix, year, counter
        """
        try:
            parts = number.split('-')
            if len(parts) >= 3:
                prefix = parts[0]
                year = int(parts[1])
                counter = int(parts[2])
                
                # Déterminer le type de document
                document_type = None
                for doc_type, doc_prefix in cls.PREFIXES.items():
                    if doc_prefix == prefix:
                        document_type = doc_type
                        break
                
                return {
                    'prefix': prefix,
                    'year': year,
                    'counter': counter,
                    'document_type': document_type,
                    'is_valid': True
                }
        except (ValueError, IndexError):
            pass
        
        return {
            'prefix': None,
            'year': None,
            'counter': None,
            'document_type': None,
            'is_valid': False
        }
    
    @classmethod
    def validate_number_format(cls, number: str, document_type: str) -> bool:
        """
        Valide le format d'un numéro de document
        
        Args:
            number: Numéro à valider
            document_type: Type de document attendu
            
        Returns:
            True si le format est valide
        """
        parsed = cls.parse_document_number(number)
        
        if not parsed['is_valid']:
            return False
        
        expected_prefix = cls.PREFIXES.get(document_type)
        return parsed['prefix'] == expected_prefix
    
    @classmethod
    def get_next_number_preview(cls, document_type: str, year: Optional[int] = None) -> str:
        """
        Retourne un aperçu du prochain numéro qui sera généré
        
        Args:
            document_type: Type de document
            year: Année (optionnel)
            
        Returns:
            Aperçu du prochain numéro
        """
        if year is None:
            year = timezone.now().year
        
        prefix = cls.PREFIXES.get(document_type, 'DOC')
        cache_key = f"document_counter_{document_type}_{year}"
        
        # Récupérer le compteur actuel
        counter = cache.get(cache_key, 0)
        if counter == 0:
            counter = cls._get_counter_from_db(document_type, year)
        
        # Prochain numéro
        next_counter = counter + 1
        return f"{prefix}-{year}-{next_counter:03d}"
    
    @classmethod
    def reset_counter(cls, document_type: str, year: int) -> bool:
        """
        Remet à zéro le compteur pour un type et une année
        
        Args:
            document_type: Type de document
            year: Année
            
        Returns:
            True si le reset a été effectué
        """
        cache_key = f"document_counter_{document_type}_{year}"
        cache.delete(cache_key)
        return True
    
    @classmethod
    def get_statistics(cls, year: Optional[int] = None) -> dict:
        """
        Retourne les statistiques de numérotation
        
        Args:
            year: Année (optionnel)
            
        Returns:
            Dict avec les statistiques
        """
        if year is None:
            year = timezone.now().year
        
        stats = {}
        
        for document_type, prefix in cls.PREFIXES.items():
            cache_key = f"document_counter_{document_type}_{year}"
            counter = cache.get(cache_key, 0)
            
            if counter == 0:
                counter = cls._get_counter_from_db(document_type, year)
            
            stats[document_type] = {
                'prefix': prefix,
                'current_counter': counter,
                'next_number': cls.get_next_number_preview(document_type, year),
                'total_generated': counter
            }
        
        return {
            'year': year,
            'document_types': stats,
            'total_documents': sum(s['current_counter'] for s in stats.values())
        }
    
    @classmethod
    def bulk_generate_numbers(cls, document_type: str, count: int, 
                             year: Optional[int] = None) -> list:
        """
        Génère plusieurs numéros en une fois
        
        Args:
            document_type: Type de document
            count: Nombre de numéros à générer
            year: Année
            
        Returns:
            Liste des numéros générés
        """
        if count <= 0 or count > 1000:  # Limite de sécurité
            raise ValueError("Le nombre doit être entre 1 et 1000")
        
        numbers = []
        for _ in range(count):
            number = cls._generate_number(document_type, year)
            numbers.append(number)
        
        return numbers 