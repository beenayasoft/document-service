"""
Service de workflow unifié pour les documents
"""
from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta
from django.utils import timezone
from ..models import QuoteStatus, InvoiceStatus


class WorkflowService:
    """Service pour gérer les workflows et transitions d'état des documents"""
    
    # Définition des transitions autorisées
    QUOTE_TRANSITIONS = {
        QuoteStatus.DRAFT: [QuoteStatus.SENT, QuoteStatus.CANCELLED],
        QuoteStatus.SENT: [QuoteStatus.ACCEPTED, QuoteStatus.REJECTED, QuoteStatus.EXPIRED, QuoteStatus.CANCELLED],
        QuoteStatus.ACCEPTED: [QuoteStatus.CANCELLED],  # Un devis accepté peut être annulé exceptionnellement
        QuoteStatus.REJECTED: [],  # État final
        QuoteStatus.EXPIRED: [QuoteStatus.SENT],  # Peut être renvoyé avec nouvelle date
        QuoteStatus.CANCELLED: []  # État final
    }
    
    INVOICE_TRANSITIONS = {
        InvoiceStatus.DRAFT: [InvoiceStatus.SENT, InvoiceStatus.CANCELLED],
        InvoiceStatus.SENT: [InvoiceStatus.PAID, InvoiceStatus.PARTIALLY_PAID, InvoiceStatus.OVERDUE, InvoiceStatus.CANCELLED],
        InvoiceStatus.OVERDUE: [InvoiceStatus.PAID, InvoiceStatus.PARTIALLY_PAID, InvoiceStatus.CANCELLED],
        InvoiceStatus.PARTIALLY_PAID: [InvoiceStatus.PAID, InvoiceStatus.OVERDUE, InvoiceStatus.CANCELLED],
        InvoiceStatus.PAID: [InvoiceStatus.CANCELLED_BY_CREDIT_NOTE],  # Seulement si avoir
        InvoiceStatus.CANCELLED: [],  # État final
        InvoiceStatus.CANCELLED_BY_CREDIT_NOTE: []  # État final
    }
    
    @classmethod
    def can_transition(cls, document_type: str, current_status: str, target_status: str) -> bool:
        """
        Vérifie si une transition d'état est autorisée
        
        Args:
            document_type: 'quote' ou 'invoice'
            current_status: Statut actuel
            target_status: Statut cible
            
        Returns:
            True si la transition est autorisée
        """
        if document_type == 'quote':
            transitions = cls.QUOTE_TRANSITIONS
        elif document_type == 'invoice':
            transitions = cls.INVOICE_TRANSITIONS
        else:
            return False
        
        allowed_transitions = transitions.get(current_status, [])
        return target_status in allowed_transitions
    
    @classmethod
    def get_allowed_transitions(cls, document_type: str, current_status: str) -> List[str]:
        """
        Retourne la liste des transitions autorisées depuis le statut actuel
        
        Args:
            document_type: 'quote' ou 'invoice'
            current_status: Statut actuel
            
        Returns:
            Liste des statuts autorisés
        """
        if document_type == 'quote':
            transitions = cls.QUOTE_TRANSITIONS
        elif document_type == 'invoice':
            transitions = cls.INVOICE_TRANSITIONS
        else:
            return []
        
        return transitions.get(current_status, [])
    
    @classmethod
    def transition_document(cls, document, target_status: str, user_info: str = None, 
                           note: str = None) -> Dict[str, Any]:
        """
        Effectue une transition d'état sur un document
        
        Args:
            document: Instance du document (Quote ou Invoice)
            target_status: Statut cible
            user_info: Informations sur l'utilisateur
            note: Note optionnelle
            
        Returns:
            Dict avec le résultat de la transition
        """
        # Déterminer le type de document
        document_type = 'quote' if hasattr(document, 'validity_period') else 'invoice'
        current_status = document.status
        
        # Vérifier si la transition est autorisée
        if not cls.can_transition(document_type, current_status, target_status):
            return {
                'success': False,
                'error': f'Transition de {current_status} vers {target_status} non autorisée',
                'allowed_transitions': cls.get_allowed_transitions(document_type, current_status)
            }
        
        # Effectuer les actions spécifiques selon la transition
        try:
            result = cls._execute_transition(document, document_type, target_status, user_info, note)
            
            # Sauvegarder le document
            document.updated_by = user_info
            document.save()
            
            return {
                'success': True,
                'previous_status': current_status,
                'new_status': document.status,
                'message': result.get('message', f'Document transitionné vers {target_status}'),
                'metadata': result.get('metadata', {})
            }
            
        except Exception as e:
            return {
                'success': False,
                'error': f'Erreur lors de la transition : {str(e)}',
                'current_status': current_status
            }
    
    @classmethod
    def _execute_transition(cls, document, document_type: str, target_status: str, 
                           user_info: str = None, note: str = None) -> Dict[str, Any]:
        """
        Exécute les actions spécifiques d'une transition
        
        Args:
            document: Instance du document
            document_type: Type de document
            target_status: Statut cible
            user_info: Utilisateur
            note: Note
            
        Returns:
            Dict avec les métadonnées de l'action
        """
        metadata = {}
        
        if document_type == 'quote':
            return cls._execute_quote_transition(document, target_status, user_info, note, metadata)
        elif document_type == 'invoice':
            return cls._execute_invoice_transition(document, target_status, user_info, note, metadata)
        
        return {'message': 'Transition effectuée', 'metadata': metadata}
    
    @classmethod
    def _execute_quote_transition(cls, quote, target_status: str, user_info: str, 
                                 note: str, metadata: Dict) -> Dict[str, Any]:
        """Exécute les transitions spécifiques aux devis"""
        
        if target_status == QuoteStatus.SENT:
            quote.status = QuoteStatus.SENT
            metadata['sent_date'] = timezone.now()
            message = "Devis envoyé au client"
            
        elif target_status == QuoteStatus.ACCEPTED:
            quote.status = QuoteStatus.ACCEPTED
            metadata['accepted_date'] = timezone.now()
            message = "Devis accepté par le client"
            
            # TODO: Déclencher la création automatique d'un projet si configuré
            # TODO: Déclencher la conversion prospect -> client si nécessaire
            
        elif target_status == QuoteStatus.REJECTED:
            quote.status = QuoteStatus.REJECTED
            metadata['rejected_date'] = timezone.now()
            metadata['rejection_reason'] = note
            message = "Devis rejeté par le client"
            
        elif target_status == QuoteStatus.EXPIRED:
            quote.status = QuoteStatus.EXPIRED
            metadata['expired_date'] = timezone.now()
            message = "Devis expiré"
            
        elif target_status == QuoteStatus.CANCELLED:
            quote.status = QuoteStatus.CANCELLED
            metadata['cancelled_date'] = timezone.now()
            metadata['cancellation_reason'] = note
            message = "Devis annulé"
            
        else:
            quote.status = target_status
            message = f"Devis transitionné vers {target_status}"
        
        return {'message': message, 'metadata': metadata}
    
    @classmethod
    def _execute_invoice_transition(cls, invoice, target_status: str, user_info: str, 
                                   note: str, metadata: Dict) -> Dict[str, Any]:
        """Exécute les transitions spécifiques aux factures"""
        
        if target_status == InvoiceStatus.SENT:
            invoice.status = InvoiceStatus.SENT
            metadata['sent_date'] = timezone.now()
            
            # Générer le numéro définitif si c'était un brouillon
            if invoice.number == "Brouillon":
                from .number_service import DocumentNumberService
                invoice.number = DocumentNumberService.generate_invoice_number()
            
            message = "Facture validée et envoyée"
            
        elif target_status == InvoiceStatus.PAID:
            invoice.status = InvoiceStatus.PAID
            metadata['paid_date'] = timezone.now()
            message = "Facture marquée comme payée"
            
        elif target_status == InvoiceStatus.PARTIALLY_PAID:
            invoice.status = InvoiceStatus.PARTIALLY_PAID
            metadata['partial_payment_date'] = timezone.now()
            message = "Paiement partiel enregistré"
            
        elif target_status == InvoiceStatus.OVERDUE:
            invoice.status = InvoiceStatus.OVERDUE
            metadata['overdue_date'] = timezone.now()
            message = "Facture marquée en retard"
            
        elif target_status == InvoiceStatus.CANCELLED:
            invoice.status = InvoiceStatus.CANCELLED
            metadata['cancelled_date'] = timezone.now()
            metadata['cancellation_reason'] = note
            message = "Facture annulée"
            
        elif target_status == InvoiceStatus.CANCELLED_BY_CREDIT_NOTE:
            invoice.status = InvoiceStatus.CANCELLED_BY_CREDIT_NOTE
            metadata['credit_note_date'] = timezone.now()
            message = "Facture annulée par avoir"
            
        else:
            invoice.status = target_status
            message = f"Facture transitionnée vers {target_status}"
        
        return {'message': message, 'metadata': metadata}
    
    @classmethod
    def check_automatic_transitions(cls, document) -> Optional[str]:
        """
        Vérifie si des transitions automatiques doivent être appliquées
        
        Args:
            document: Instance du document
            
        Returns:
            Nouveau statut si transition automatique nécessaire, None sinon
        """
        document_type = 'quote' if hasattr(document, 'validity_period') else 'invoice'
        current_status = document.status
        now = timezone.now()
        
        if document_type == 'quote':
            # Vérifier expiration automatique des devis
            if (current_status == QuoteStatus.SENT and 
                document.expiry_date and 
                document.expiry_date < now.date()):
                return QuoteStatus.EXPIRED
                
        elif document_type == 'invoice':
            # Vérifier les factures en retard
            if (current_status == InvoiceStatus.SENT and 
                document.due_date and 
                document.due_date < now.date() and
                document.remaining_amount > 0):
                return InvoiceStatus.OVERDUE
            
            # Vérifier les paiements complets
            if (current_status in [InvoiceStatus.SENT, InvoiceStatus.PARTIALLY_PAID, InvoiceStatus.OVERDUE] and
                document.remaining_amount <= 0):
                return InvoiceStatus.PAID
        
        return None
    
    @classmethod
    def get_workflow_status(cls, document) -> Dict[str, Any]:
        """
        Retourne le statut workflow complet d'un document
        
        Args:
            document: Instance du document
            
        Returns:
            Dict avec toutes les informations de workflow
        """
        document_type = 'quote' if hasattr(document, 'validity_period') else 'invoice'
        current_status = document.status
        
        # Transitions automatiques possibles
        auto_transition = cls.check_automatic_transitions(document)
        
        # Transitions manuelles autorisées
        allowed_transitions = cls.get_allowed_transitions(document_type, current_status)
        
        # Calculs de dates et délais
        workflow_data = {
            'document_type': document_type,
            'current_status': current_status,
            'allowed_transitions': allowed_transitions,
            'auto_transition_suggested': auto_transition,
            'is_final_status': len(allowed_transitions) == 0,
            'created_date': document.created_at,
            'last_updated': document.updated_at
        }
        
        if document_type == 'quote':
            workflow_data.update({
                'issue_date': document.issue_date,
                'expiry_date': document.expiry_date,
                'is_expired': (document.expiry_date and 
                              document.expiry_date < timezone.now().date()),
                'days_until_expiry': cls._calculate_days_until(document.expiry_date) if document.expiry_date else None
            })
            
        elif document_type == 'invoice':
            workflow_data.update({
                'issue_date': document.issue_date,
                'due_date': document.due_date,
                'is_overdue': (document.due_date and 
                              document.due_date < timezone.now().date() and
                              document.remaining_amount > 0),
                'days_until_due': cls._calculate_days_until(document.due_date) if document.due_date else None,
                'days_overdue': cls._calculate_days_since(document.due_date) if (
                    document.due_date and document.due_date < timezone.now().date()
                ) else 0,
                'payment_status': {
                    'total_amount': document.total_ttc,
                    'paid_amount': document.paid_amount,
                    'remaining_amount': document.remaining_amount,
                    'is_fully_paid': document.remaining_amount <= 0,
                    'is_partially_paid': 0 < document.paid_amount < document.total_ttc
                }
            })
        
        return workflow_data
    
    @staticmethod
    def _calculate_days_until(target_date) -> int:
        """Calcule le nombre de jours jusqu'à une date"""
        if not target_date:
            return 0
        
        today = timezone.now().date()
        if target_date > today:
            return (target_date - today).days
        return 0
    
    @staticmethod
    def _calculate_days_since(target_date) -> int:
        """Calcule le nombre de jours depuis une date"""
        if not target_date:
            return 0
        
        today = timezone.now().date()
        if target_date < today:
            return (today - target_date).days
        return 0
    
    @classmethod
    def bulk_transition(cls, documents: List, target_status: str, 
                       user_info: str = None, note: str = None) -> Dict[str, Any]:
        """
        Effectue une transition en lot sur plusieurs documents
        
        Args:
            documents: Liste des documents
            target_status: Statut cible
            user_info: Utilisateur
            note: Note
            
        Returns:
            Dict avec le résumé des transitions
        """
        successful = []
        failed = []
        
        for document in documents:
            result = cls.transition_document(document, target_status, user_info, note)
            
            if result['success']:
                successful.append({
                    'document_id': str(document.id),
                    'document_number': document.number,
                    'previous_status': result['previous_status'],
                    'new_status': result['new_status']
                })
            else:
                failed.append({
                    'document_id': str(document.id),
                    'document_number': document.number,
                    'error': result['error']
                })
        
        return {
            'total_processed': len(documents),
            'successful_count': len(successful),
            'failed_count': len(failed),
            'successful_transitions': successful,
            'failed_transitions': failed
        } 