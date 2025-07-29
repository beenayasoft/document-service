"""
Service de génération PDF unifié pour tous les documents
"""
from io import BytesIO
import os
import logging
from typing import Dict, Any, Optional
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm, mm
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak
from reportlab.platypus.flowables import KeepTogether
from reportlab.pdfgen import canvas
from django.conf import settings
from decimal import Decimal

from .calculation_service import CalculationService
from .company_info_service import company_info_service

logger = logging.getLogger(__name__)


class DocumentPDFService:
    """Service unifié pour générer des PDF de documents"""
    
    def __init__(self, document, document_type: str, options: Dict[str, Any] = None, tenant_id: str = None):
        """
        Initialise le générateur PDF
        
        Args:
            document: Instance du document (Quote ou Invoice)
            document_type: 'quote' ou 'invoice'
            options: Options de génération (show_costs, include_details, etc.)
            tenant_id: ID du tenant (récupéré automatiquement si non fourni)
        """
        self.document = document
        self.document_type = document_type
        self.options = options or {}
        self.buffer = BytesIO()
        self.width, self.height = A4
        
        # Récupérer le tenant_id depuis le document si non fourni
        self.tenant_id = tenant_id or getattr(document, 'tenant_id', None)
        
        # Configuration des styles
        self._setup_styles()
        
        # Configuration spécifique par type - maintenant dynamique
        self.company_info = self._get_company_info()
    
    def _setup_styles(self):
        """Configure les styles de document"""
        self.styles = getSampleStyleSheet()
        
        # Style titre principal
        self.title_style = ParagraphStyle(
            'TitleStyle',
            parent=self.styles['Heading1'],
            fontSize=16,
            leading=20,
            alignment=1,  # Centré
            spaceAfter=20,
            fontName='Helvetica-Bold'
        )
        
        # Style sous-titre
        self.subtitle_style = ParagraphStyle(
            'SubtitleStyle',
            parent=self.styles['Heading2'],
            fontSize=14,
            leading=16,
            spaceAfter=12,
            fontName='Helvetica-Bold'
        )
        
        # Style section
        self.section_style = ParagraphStyle(
            'SectionStyle',
            parent=self.styles['Heading3'],
            fontSize=12,
            leading=14,
            spaceAfter=8,
            spaceBefore=16,
            fontName='Helvetica-Bold'
        )
        
        # Style normal
        self.normal_style = ParagraphStyle(
            'NormalStyle',
            parent=self.styles['Normal'],
            fontSize=10,
            leading=12
        )
        
        # Style pour les totaux
        self.total_style = ParagraphStyle(
            'TotalStyle',
            parent=self.styles['Normal'],
            fontSize=11,
            leading=13,
            fontName='Helvetica-Bold'
        )
        
        # Style pour les informations client
        self.client_style = ParagraphStyle(
            'ClientStyle',
            parent=self.styles['Normal'],
            fontSize=10,
            leading=12
        )
    
    def _get_company_info(self) -> Dict[str, str]:
        """
        Récupère les informations de l'entreprise depuis le tenant-service
        
        Returns:
            Dict contenant les informations de l'entreprise pour ce tenant
        """
        if not self.tenant_id:
            logger.warning("Aucun tenant_id disponible pour récupérer les informations entreprise")
            return self._get_fallback_company_info()
        
        try:
            # Utiliser le service dédié avec cache
            company_info = company_info_service.get_company_info(self.tenant_id)
            
            # Adapter le format pour la compatibilité avec l'ancien code
            return {
                'name': company_info.get('name', 'Votre Entreprise'),
                'address': company_info.get('address_line_1', ''),
                'address2': company_info.get('address_line_2', ''),
                'city': f"{company_info.get('postal_code', '')} {company_info.get('city', '')}".strip(),
                'full_address': company_info.get('full_address', ''),
                'phone': company_info.get('phone', ''),
                'email': company_info.get('email', ''),
                'website': company_info.get('website', ''),
                'siret': company_info.get('siret', ''),
                'ice': company_info.get('ice', ''),
                'legal_form': company_info.get('legal_form', ''),
                'logo_url': company_info.get('logo_url', ''),
                'logo_base64': company_info.get('logo_base64', ''),
                'primary_color': company_info.get('primary_color', '#007bff'),
                'secondary_color': company_info.get('secondary_color', '#6c757d'),
                'accent_color': company_info.get('accent_color', '#28a745'),
            }
            
        except Exception as e:
            logger.error(f"Erreur lors de la récupération des informations entreprise: {str(e)}")
            return self._get_fallback_company_info()
    
    def _get_fallback_company_info(self) -> Dict[str, str]:
        """
        Informations entreprise par défaut en cas d'erreur
        
        Returns:
            Dict avec des valeurs par défaut
        """
        return {
            'name': 'Votre Entreprise',
            'address': 'Adresse à configurer',
            'address2': '',
            'city': 'Ville 00000',
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
    
    def generate_pdf(self) -> BytesIO:
        """
        Génère le PDF complet
        
        Returns:
            Buffer contenant le PDF
        """
        # Créer le document PDF
        doc = SimpleDocTemplate(
            self.buffer,
            pagesize=A4,
            rightMargin=2*cm,
            leftMargin=2*cm,
            topMargin=3*cm,
            bottomMargin=2*cm
        )
        
        # Construire le contenu
        elements = []
        
        # En-tête avec informations document
        self._add_document_header(elements)
        
        # Informations client
        self._add_client_info(elements)
        
        # Informations projet (si applicable)
        if hasattr(self.document, 'project_name') and self.document.project_name:
            self._add_project_info(elements)
        
        # Tableau des éléments
        self._add_items_table(elements)
        
        # Totaux
        self._add_totals_section(elements)
        
        # Notes et conditions
        self._add_notes_and_conditions(elements)
        
        # Informations spécifiques (paiements pour factures, etc.)
        if self.document_type == 'invoice':
            self._add_payment_info(elements)
        
        # Pied de page avec mentions légales
        self._add_footer_info(elements)
        
        # Construire le PDF avec en-têtes et pieds de page
        doc.build(elements, 
                 onFirstPage=self._draw_header_footer,
                 onLaterPages=self._draw_header_footer)
        
        self.buffer.seek(0)
        return self.buffer
    
    def _draw_header_footer(self, canvas_obj, doc):
        """Dessine l'en-tête et le pied de page"""
        canvas_obj.saveState()
        
        # En-tête avec logo et infos entreprise
        self._draw_header(canvas_obj, doc)
        
        # Pied de page avec mentions légales et numéro de page
        self._draw_footer(canvas_obj, doc)
        
        canvas_obj.restoreState()
    
    def _draw_header(self, canvas_obj, doc):
        """Dessine l'en-tête de page"""
        # Logo (si disponible)
        # logo_path = os.path.join(settings.MEDIA_ROOT, 'logo.png')
        # if os.path.exists(logo_path):
        #     canvas_obj.drawImage(logo_path, 1*cm, self.height - 2.5*cm, 
        #                         width=4*cm, height=1.5*cm)
        
        # Informations entreprise
        canvas_obj.setFont('Helvetica-Bold', 12)
        canvas_obj.drawString(1*cm, self.height - 1.5*cm, self.company_info['name'])
        
        canvas_obj.setFont('Helvetica', 9)
        y_pos = self.height - 1.8*cm
        for info in [self.company_info['address'], self.company_info['city'], 
                    f"Tél: {self.company_info['phone']}", 
                    f"Email: {self.company_info['email']}"]:
            canvas_obj.drawString(1*cm, y_pos, info)
            y_pos -= 0.3*cm
        
        # Informations document (côté droit)
        document_title = "DEVIS" if self.document_type == 'quote' else "FACTURE"
        if hasattr(self.document, 'is_credit_note') and self.document.is_credit_note:
            document_title = "AVOIR"
        
        canvas_obj.setFont('Helvetica-Bold', 14)
        canvas_obj.drawString(self.width - 5*cm, self.height - 1.5*cm, 
                             f"{document_title} N° {self.document.number}")
        
        canvas_obj.setFont('Helvetica', 10)
        canvas_obj.drawString(self.width - 5*cm, self.height - 1.8*cm, 
                             f"Date: {self.document.issue_date.strftime('%d/%m/%Y')}")
        
        # Date d'échéance pour factures ou expiration pour devis
        if self.document_type == 'invoice' and hasattr(self.document, 'due_date') and self.document.due_date:
            canvas_obj.drawString(self.width - 5*cm, self.height - 2.1*cm, 
                                 f"Échéance: {self.document.due_date.strftime('%d/%m/%Y')}")
        elif self.document_type == 'quote' and hasattr(self.document, 'expiry_date') and self.document.expiry_date:
            canvas_obj.drawString(self.width - 5*cm, self.height - 2.1*cm, 
                                 f"Validité: {self.document.expiry_date.strftime('%d/%m/%Y')}")
    
    def _draw_footer(self, canvas_obj, doc):
        """Dessine le pied de page"""
        # Mentions légales
        canvas_obj.setFont('Helvetica', 8)
        canvas_obj.drawString(1*cm, 1.5*cm, 
                             f"SIRET: {self.company_info['siret']} - ICE: {self.company_info['ice']}")
        
        # Conditions de paiement
        payment_terms = getattr(self.document, 'terms_and_conditions', '') or "Voir conditions générales"
        canvas_obj.drawString(1*cm, 1.2*cm, f"Conditions: {payment_terms}")
        
        # Numéro de page
        canvas_obj.setFont('Helvetica', 9)
        page_text = f"Page {doc.page}"
        canvas_obj.drawString(self.width - 2*cm, 0.8*cm, page_text)
    
    def _add_document_header(self, elements):
        """Ajoute l'en-tête du document"""
        elements.append(Spacer(1, 2*cm))  # Espace pour l'en-tête de page
    
    def _add_client_info(self, elements):
        """Ajoute les informations client"""
        elements.append(Paragraph("CLIENT", self.section_style))
        
        client_data = [
            [Paragraph(f"<b>{self.document.client_name}</b>", self.client_style)]
        ]
        
        if self.document.client_address:
            for line in self.document.client_address.strip().split('\n'):
                if line.strip():
                    client_data.append([Paragraph(line.strip(), self.client_style)])
        
        client_table = Table(client_data, colWidths=[8*cm])
        client_table.setStyle(TableStyle([
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('LEFTPADDING', (0, 0), (-1, -1), 0),
            ('RIGHTPADDING', (0, 0), (-1, -1), 0),
            ('TOPPADDING', (0, 0), (-1, -1), 2),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
        ]))
        
        elements.append(client_table)
        elements.append(Spacer(1, 0.5*cm))
    
    def _add_project_info(self, elements):
        """Ajoute les informations projet"""
        elements.append(Paragraph("PROJET", self.section_style))
        
        project_data = [
            [Paragraph(f"<b>{self.document.project_name}</b>", self.client_style)]
        ]
        
        if hasattr(self.document, 'project_address') and self.document.project_address:
            for line in self.document.project_address.strip().split('\n'):
                if line.strip():
                    project_data.append([Paragraph(line.strip(), self.client_style)])
        
        if hasattr(self.document, 'project_reference') and self.document.project_reference:
            project_data.append([Paragraph(f"Référence: {self.document.project_reference}", self.client_style)])
        
        project_table = Table(project_data, colWidths=[8*cm])
        project_table.setStyle(TableStyle([
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('LEFTPADDING', (0, 0), (-1, -1), 0),
            ('RIGHTPADDING', (0, 0), (-1, -1), 0),
            ('TOPPADDING', (0, 0), (-1, -1), 2),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
        ]))
        
        elements.append(project_table)
        elements.append(Spacer(1, 0.5*cm))
    
    def _add_items_table(self, elements):
        """Ajoute le tableau des éléments"""
        elements.append(Paragraph("DÉTAIL", self.section_style))
        
        # En-têtes du tableau
        headers = ['Désignation', 'Qté', 'Unité', 'P.U. HT', 'Total HT']
        if self.options.get('show_vat', True):
            headers.append('TVA')
            headers.append('Total TTC')
        
        # Largeurs des colonnes
        if self.options.get('show_vat', True):
            col_widths = [7*cm, 1.5*cm, 1.5*cm, 2*cm, 2*cm, 1*cm, 2*cm]
        else:
            col_widths = [8*cm, 2*cm, 2*cm, 2.5*cm, 2.5*cm]
        
        table_data = [headers]
        
        # Récupérer les éléments
        items = self.document.items.all().order_by('position')
        
        for item in items:
            # Ignorer les chapitres et sections pour l'instant (logique simplifiée)
            if item.type in ['chapter', 'section']:
                # Ajouter une ligne de section
                section_row = [f"• {item.designation}"] + [''] * (len(headers) - 1)
                table_data.append(section_row)
                continue
            
            row = [
                item.designation,
                str(item.quantity),
                item.unit or '',
                CalculationService.format_currency(item.unit_price),
                CalculationService.format_currency(item.total_ht)
            ]
            
            if self.options.get('show_vat', True):
                row.append(f"{item.vat_rate}%")
                row.append(CalculationService.format_currency(item.total_ttc))
            
            table_data.append(row)
        
        # Créer le tableau
        items_table = Table(table_data, colWidths=col_widths, repeatRows=1)
        
        # Style du tableau
        style_list = [
            # En-tête
            ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, 0), 'CENTER'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 10),
            
            # Corps du tableau
            ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
            ('FONTSIZE', (0, 1), (-1, -1), 9),
            ('ALIGN', (1, 1), (-1, -1), 'CENTER'),  # Centrer sauf première colonne
            ('ALIGN', (0, 1), (0, -1), 'LEFT'),     # Première colonne à gauche
            
            # Bordures
            ('GRID', (0, 0), (-1, -1), 1, colors.black),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            
            # Espacement
            ('TOPPADDING', (0, 0), (-1, -1), 6),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
            ('LEFTPADDING', (0, 0), (-1, -1), 6),
            ('RIGHTPADDING', (0, 0), (-1, -1), 6),
        ]
        
        items_table.setStyle(TableStyle(style_list))
        elements.append(items_table)
        elements.append(Spacer(1, 0.5*cm))
    
    def _add_totals_section(self, elements):
        """Ajoute la section des totaux"""
        # Calculer les totaux avec le service
        totals = CalculationService.calculate_document_totals(self.document.items.all())
        
        # Tableau des totaux
        totals_data = [
            ['Total HT:', CalculationService.format_currency(totals['total_ht'])],
            ['Total TVA:', CalculationService.format_currency(totals['total_vat'])],
            ['Total TTC:', CalculationService.format_currency(totals['total_ttc'])],
        ]
        
        # Pour les factures, ajouter les informations de paiement
        if self.document_type == 'invoice':
            if hasattr(self.document, 'paid_amount') and self.document.paid_amount > 0:
                totals_data.append(['Montant payé:', CalculationService.format_currency(self.document.paid_amount)])
                totals_data.append(['Restant dû:', CalculationService.format_currency(self.document.remaining_amount)])
        
        totals_table = Table(totals_data, colWidths=[4*cm, 3*cm])
        totals_table.setStyle(TableStyle([
            ('ALIGN', (0, 0), (-1, -1), 'RIGHT'),
            ('FONTNAME', (0, 0), (-1, -1), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 11),
            ('TOPPADDING', (0, 0), (-1, -1), 4),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
            # Ligne de séparation avant le total TTC
            ('LINEABOVE', (0, -1), (-1, -1), 2, colors.black),
            ('BACKGROUND', (0, -1), (-1, -1), colors.lightgrey),
        ]))
        
        # Aligner le tableau à droite
        totals_wrapper = Table([[totals_table]], colWidths=[17*cm])
        totals_wrapper.setStyle(TableStyle([
            ('ALIGN', (0, 0), (-1, -1), 'RIGHT'),
        ]))
        
        elements.append(totals_wrapper)
        elements.append(Spacer(1, 1*cm))
    
    def _add_notes_and_conditions(self, elements):
        """Ajoute les notes et conditions"""
        if self.document.notes:
            elements.append(Paragraph("NOTES", self.section_style))
            elements.append(Paragraph(self.document.notes, self.normal_style))
            elements.append(Spacer(1, 0.5*cm))
        
        if self.document.terms_and_conditions:
            elements.append(Paragraph("CONDITIONS GÉNÉRALES", self.section_style))
            elements.append(Paragraph(self.document.terms_and_conditions, self.normal_style))
            elements.append(Spacer(1, 0.5*cm))
    
    def _add_payment_info(self, elements):
        """Ajoute les informations de paiement (pour factures)"""
        if hasattr(self.document, 'payments'):
            payments = self.document.payments.all().order_by('-date')
            
            if payments.exists():
                elements.append(Paragraph("HISTORIQUE DES PAIEMENTS", self.section_style))
                
                payment_data = [['Date', 'Montant', 'Méthode', 'Référence']]
                
                for payment in payments:
                    payment_data.append([
                        payment.date.strftime('%d/%m/%Y'),
                        CalculationService.format_currency(payment.amount),
                        payment.get_method_display(),
                        payment.reference or '-'
                    ])
                
                payment_table = Table(payment_data, colWidths=[3*cm, 3*cm, 3*cm, 4*cm])
                payment_table.setStyle(TableStyle([
                    # En-tête
                    ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
                    ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                    ('ALIGN', (0, 0), (-1, 0), 'CENTER'),
                    ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                    ('FONTSIZE', (0, 0), (-1, 0), 10),
                    
                    # Corps
                    ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
                    ('FONTSIZE', (0, 1), (-1, -1), 9),
                    ('ALIGN', (0, 1), (-1, -1), 'CENTER'),
                    
                    # Bordures
                    ('GRID', (0, 0), (-1, -1), 1, colors.black),
                    ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                    
                    # Espacement
                    ('TOPPADDING', (0, 0), (-1, -1), 4),
                    ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
                ]))
                
                elements.append(payment_table)
                elements.append(Spacer(1, 0.5*cm))
    
    def _add_footer_info(self, elements):
        """Ajoute les informations de pied de page dans le contenu"""
        # Les mentions légales sont déjà dans le pied de page
        # On peut ajouter d'autres informations ici si nécessaire
        pass
    
    @classmethod
    def generate_quote_pdf(cls, quote, options: Dict[str, Any] = None) -> BytesIO:
        """
        Génère un PDF de devis
        
        Args:
            quote: Instance de Quote
            options: Options de génération
            
        Returns:
            Buffer contenant le PDF
        """
        generator = cls(quote, 'quote', options)
        return generator.generate_pdf()
    
    @classmethod
    def generate_invoice_pdf(cls, invoice, options: Dict[str, Any] = None) -> BytesIO:
        """
        Génère un PDF de facture
        
        Args:
            invoice: Instance d'Invoice
            options: Options de génération
            
        Returns:
            Buffer contenant le PDF
        """
        generator = cls(invoice, 'invoice', options)
        return generator.generate_pdf()
    
    @classmethod
    def get_default_options(cls, document_type: str) -> Dict[str, Any]:
        """
        Retourne les options par défaut pour un type de document
        
        Args:
            document_type: Type de document
            
        Returns:
            Dict avec les options par défaut
        """
        base_options = {
            'show_vat': True,
            'include_details': True,
            'show_payments': True,
        }
        
        if document_type == 'quote':
            base_options.update({
                'show_costs': False,  # Ne pas montrer les coûts au client
                'show_margins': False,
            })
        
        return base_options


class PDFService:
    """
    Wrapper pour la compatibilité avec l'ancien code
    Utilise DocumentPDFService en interne avec support tenant
    """
    
    def __init__(self, tenant_id: str = None):
        """
        Initialise le service PDF avec tenant_id optionnel
        
        Args:
            tenant_id: ID du tenant (peut être fourni ou récupéré depuis la requête)
        """
        self.tenant_id = tenant_id
    
    def generate_document_pdf(self, instance, include_details=True, **options):
        """
        Génère un PDF pour un document (méthode de compatibilité)
        
        Args:
            instance: Instance de document (Quote ou Invoice)
            include_details: Inclure les détails
            **options: Options supplémentaires
            
        Returns:
            BytesIO contenant le PDF
        """
        # Déterminer le type de document
        document_type = 'quote' if hasattr(instance, 'validity_period') else 'invoice'
        
        # Préparer les options
        pdf_options = {
            'include_details': include_details,
            **options
        }
        
        # Utiliser DocumentPDFService
        generator = DocumentPDFService(
            document=instance,
            document_type=document_type,
            options=pdf_options,
            tenant_id=self.tenant_id
        )
        
        return generator.generate_pdf()
    
    @classmethod 
    def from_request(cls, request):
        """
        Factory method pour créer une instance depuis une requête Django
        
        Args:
            request: Requête Django avec tenant_id injecté par le middleware
            
        Returns:
            Instance de PDFService avec le bon tenant_id
        """
        tenant_id = getattr(request, 'tenant_id', None)
        return cls(tenant_id=tenant_id) 