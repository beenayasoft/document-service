"""
Service d'envoi d'emails pour les devis et factures
Utilise Brevo (Sendinblue) comme service SMTP
"""

import os
import logging
from typing import Optional, Dict, Any, List
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.conf import settings
from django.utils.html import strip_tags
from io import BytesIO

logger = logging.getLogger(__name__)


class EmailService:
    """Service centralisé pour l'envoi d'emails"""
    
    @staticmethod
    def send_quote_email(
        quote,
        recipient_email: str,
        sender_email: Optional[str] = None,
        message: Optional[str] = None,
        tenant_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Envoie un devis par email
        
        Args:
            quote: Instance du modèle Quote
            recipient_email: Email du destinataire
            sender_email: Email de l'expéditeur (optionnel)
            message: Message personnalisé (optionnel)
            tenant_id: ID du tenant pour la personnalisation
            
        Returns:
            Dict avec le statut de l'envoi et les détails
        """
        try:
            # Validation des paramètres
            if not recipient_email:
                raise ValueError("L'email du destinataire est requis")
            
            if not quote:
                raise ValueError("Le devis est requis")
            
            # Configuration de l'expéditeur
            from_email = sender_email or settings.DEFAULT_FROM_EMAIL
            if not from_email:
                raise ValueError("Aucun email expéditeur configuré")
            
            # Génération du contenu de l'email
            context = {
                'quote': quote,
                'custom_message': message,
                'tenant_id': tenant_id,
            }
            
            # Template HTML
            html_content = render_to_string('emails/quote_send.html', context)
            
            # Version texte (fallback)
            text_content = strip_tags(html_content)
            
            # Création de l'email
            subject = f"Devis {quote.number} - {quote.client_name}"
            
            email = EmailMultiAlternatives(
                subject=subject,
                body=text_content,
                from_email=from_email,
                to=[recipient_email],
                reply_to=[from_email]
            )
            
            # Attacher le contenu HTML
            email.attach_alternative(html_content, "text/html")
            
            # TODO: Générer et attacher le PDF du devis
            # pdf_content = EmailService._generate_quote_pdf(quote, tenant_id)
            # email.attach(f"devis_{quote.number}.pdf", pdf_content, "application/pdf")
            
            # Envoi de l'email
            email.send()
            
            logger.info(f"Email envoyé avec succès pour le devis {quote.number} à {recipient_email}")
            
            return {
                'success': True,
                'message': f'Devis {quote.number} envoyé avec succès à {recipient_email}',
                'recipient': recipient_email,
                'subject': subject
            }
            
        except Exception as e:
            error_msg = f"Erreur lors de l'envoi de l'email: {str(e)}"
            logger.error(error_msg)
            return {
                'success': False,
                'message': error_msg,
                'error': str(e)
            }
    
    @staticmethod
    def send_invoice_email(
        invoice,
        recipient_email: str,
        sender_email: Optional[str] = None,
        message: Optional[str] = None,
        tenant_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Envoie une facture par email
        
        Args:
            invoice: Instance du modèle Invoice
            recipient_email: Email du destinataire
            sender_email: Email de l'expéditeur (optionnel)
            message: Message personnalisé (optionnel)
            tenant_id: ID du tenant pour la personnalisation
            
        Returns:
            Dict avec le statut de l'envoi et les détails
        """
        try:
            # Validation des paramètres
            if not recipient_email:
                raise ValueError("L'email du destinataire est requis")
            
            if not invoice:
                raise ValueError("La facture est requise")
            
            # Configuration de l'expéditeur
            from_email = sender_email or settings.DEFAULT_FROM_EMAIL
            if not from_email:
                raise ValueError("Aucun email expéditeur configuré")
            
            # Génération du contenu de l'email
            context = {
                'invoice': invoice,
                'custom_message': message,
                'tenant_id': tenant_id,
            }
            
            # Template HTML
            html_content = render_to_string('emails/invoice_send.html', context)
            
            # Version texte (fallback)
            text_content = strip_tags(html_content)
            
            # Création de l'email
            subject = f"Facture {invoice.number} - {invoice.client_name}"
            
            email = EmailMultiAlternatives(
                subject=subject,
                body=text_content,
                from_email=from_email,
                to=[recipient_email],
                reply_to=[from_email]
            )
            
            # Attacher le contenu HTML
            email.attach_alternative(html_content, "text/html")
            
            # TODO: Générer et attacher le PDF de la facture
            # pdf_content = EmailService._generate_invoice_pdf(invoice, tenant_id)
            # email.attach(f"facture_{invoice.number}.pdf", pdf_content, "application/pdf")
            
            # Envoi de l'email
            email.send()
            
            logger.info(f"Email envoyé avec succès pour la facture {invoice.number} à {recipient_email}")
            
            return {
                'success': True,
                'message': f'Facture {invoice.number} envoyée avec succès à {recipient_email}',
                'recipient': recipient_email,
                'subject': subject
            }
            
        except Exception as e:
            error_msg = f"Erreur lors de l'envoi de l'email: {str(e)}"
            logger.error(error_msg)
            return {
                'success': False,
                'message': error_msg,
                'error': str(e)
            }
    
    @staticmethod
    def _generate_quote_pdf(quote, tenant_id: Optional[str] = None) -> bytes:
        """
        Génère le PDF d'un devis
        TODO: À implémenter avec WeasyPrint ou ReportLab
        """
        # Placeholder pour la génération PDF
        return b"PDF Content Placeholder"
    
    @staticmethod
    def _generate_invoice_pdf(invoice, tenant_id: Optional[str] = None) -> bytes:
        """
        Génère le PDF d'une facture
        TODO: À implémenter avec WeasyPrint ou ReportLab
        """
        # Placeholder pour la génération PDF
        return b"PDF Content Placeholder"
    
    @staticmethod
    def test_email_configuration() -> Dict[str, Any]:
        """
        Test la configuration email
        
        Returns:
            Dict avec le résultat du test
        """
        try:
            from django.core.mail import get_connection
            
            connection = get_connection()
            connection.open()
            connection.close()
            
            return {
                'success': True,
                'message': 'Configuration email valide',
                'backend': settings.EMAIL_BACKEND,
                'host': getattr(settings, 'EMAIL_HOST', 'Non configuré'),
                'port': getattr(settings, 'EMAIL_PORT', 'Non configuré')
            }
            
        except Exception as e:
            return {
                'success': False,
                'message': f'Erreur de configuration email: {str(e)}',
                'error': str(e)
            }