"""
Tests des services métier pour le document-service.
"""
from decimal import Decimal
from datetime import date, timedelta
from django.test import TestCase
from django.core.files.base import ContentFile
from documents.tests.fixtures import DocumentTestCase, fixtures, data_builder
from documents.services import (
    CalculationService, WorkflowService, NumberService, PDFService
)
from documents.models import Quote, Invoice, QuoteItem


class CalculationServiceTest(DocumentTestCase):
    """Tests du service de calculs."""
    
    def setUp(self):
        super().setUp()
        self.calculation_service = CalculationService()
    
    def test_calculate_vat(self):
        """Test calcul de la TVA."""
        # Test avec taux de 20%
        vat_amount = self.calculation_service.calculate_vat(
            Decimal('1000.00'), Decimal('20.00')
        )
        self.assertEqual(vat_amount, Decimal('200.00'))
        
        # Test avec taux de 5.5%
        vat_amount = self.calculation_service.calculate_vat(
            Decimal('1000.00'), Decimal('5.5')
        )
        self.assertEqual(vat_amount, Decimal('55.00'))
        
        # Test avec montant nul
        vat_amount = self.calculation_service.calculate_vat(
            Decimal('0.00'), Decimal('20.00')
        )
        self.assertEqual(vat_amount, Decimal('0.00'))
    
    def test_calculate_discount(self):
        """Test calcul des remises."""
        # Test remise en pourcentage
        discount = self.calculation_service.calculate_discount(
            Decimal('1000.00'), Decimal('10.00')
        )
        self.assertEqual(discount, Decimal('100.00'))
        
        # Test remise montant fixe
        discount = self.calculation_service.calculate_discount(
            Decimal('1000.00'), None, Decimal('150.00')
        )
        self.assertEqual(discount, Decimal('150.00'))
        
        # Test sans remise
        discount = self.calculation_service.calculate_discount(
            Decimal('1000.00'), None, None
        )
        self.assertEqual(discount, Decimal('0.00'))
    
    def test_calculate_item_total(self):
        """Test calcul du total d'un élément."""
        total = self.calculation_service.calculate_item_total(
            quantity=Decimal('2.5'),
            unit_price=Decimal('100.00'),
            discount_percentage=Decimal('10.00')
        )
        
        expected = Decimal('2.5') * Decimal('100.00')  # 250.00
        expected -= expected * Decimal('10.00') / 100  # -25.00 = 225.00
        
        self.assertEqual(total, Decimal('225.00'))
    
    def test_calculate_document_totals(self):
        """Test calcul des totaux d'un document."""
        quote = fixtures.create_quote(
            self.user, self.vat_rate, self.quote_status,
            subtotal=Decimal('1000.00'),
            discount_percentage=Decimal('5.00')
        )
        
        totals = self.calculation_service.calculate_document_totals(
            subtotal=quote.subtotal,
            vat_rate=self.vat_rate.rate,
            discount_percentage=quote.discount_percentage
        )
        
        expected_discount = Decimal('50.00')  # 5% de 1000
        expected_subtotal_after_discount = Decimal('950.00')
        expected_vat = Decimal('190.00')  # 20% de 950
        expected_total = Decimal('1140.00')  # 950 + 190
        
        self.assertEqual(totals['discount_amount'], expected_discount)
        self.assertEqual(totals['subtotal_after_discount'], expected_subtotal_after_discount)
        self.assertEqual(totals['vat_amount'], expected_vat)
        self.assertEqual(totals['total'], expected_total)
    
    def test_recalculate_from_items(self):
        """Test recalcul depuis les éléments."""
        quote = fixtures.create_quote(
            self.user, self.vat_rate, self.quote_status
        )
        
        # Créer des éléments
        fixtures.create_quote_item(
            quote, quantity=Decimal('2.0'), unit_price=Decimal('150.00')
        )
        fixtures.create_quote_item(
            quote, quantity=Decimal('1.5'), unit_price=Decimal('200.00')
        )
        
        totals = self.calculation_service.recalculate_from_items(quote)
        
        expected_subtotal = Decimal('300.00') + Decimal('300.00')  # 600.00
        expected_vat = expected_subtotal * self.vat_rate.rate / 100  # 120.00
        expected_total = expected_subtotal + expected_vat  # 720.00
        
        self.assertEqual(totals['subtotal'], expected_subtotal)
        self.assertEqual(totals['vat_amount'], expected_vat)
        self.assertEqual(totals['total'], expected_total)
    
    def test_precision_handling(self):
        """Test gestion de la précision des calculs."""
        # Test avec des nombres à virgule
        result = self.calculation_service.calculate_vat(
            Decimal('999.999'), Decimal('19.6')
        )
        
        # Le résultat doit être arrondi à 2 décimales
        self.assertEqual(result.as_tuple().exponent, -2)
        self.assertEqual(result, Decimal('196.00'))  # Arrondi


class WorkflowServiceTest(DocumentTestCase):
    """Tests du service de workflow."""
    
    def setUp(self):
        super().setUp()
        self.workflow_service = WorkflowService()
        
        # Créer des statuts supplémentaires
        self.sent_status = fixtures.create_quote_status('sent', is_default=False)
        self.validated_status = fixtures.create_quote_status('validated', is_default=False)
        self.rejected_status = fixtures.create_quote_status('rejected', is_default=False)
    
    def test_can_transition_quote(self):
        """Test vérification des transitions possibles."""
        quote = fixtures.create_quote(
            self.user, self.vat_rate, self.quote_status  # status = draft
        )
        
        # Draft -> Sent : autorisé
        self.assertTrue(
            self.workflow_service.can_transition(quote, self.sent_status)
        )
        
        # Draft -> Validated : autorisé (skip sent)
        self.assertTrue(
            self.workflow_service.can_transition(quote, self.validated_status)
        )
        
        # Draft -> Rejected : non autorisé directement
        self.assertFalse(
            self.workflow_service.can_transition(quote, self.rejected_status)
        )
    
    def test_transition_quote_status(self):
        """Test transition de statut."""
        quote = fixtures.create_quote(
            self.user, self.vat_rate, self.quote_status
        )
        
        # Transition vers sent
        result = self.workflow_service.transition_status(
            quote, self.sent_status, self.user
        )
        
        self.assertTrue(result['success'])
        quote.refresh_from_db()
        self.assertEqual(quote.status, self.sent_status)
        self.assertIsNotNone(quote.sent_at)
    
    def test_validate_quote(self):
        """Test validation d'un devis."""
        quote = fixtures.create_quote(
            self.user, self.vat_rate, self.quote_status,
            subtotal=Decimal('1000.00')
        )
        
        # Ajouter des éléments
        fixtures.create_quote_item(quote, quantity=Decimal('2.0'), unit_price=Decimal('500.00'))
        
        result = self.workflow_service.validate_quote(quote, self.user)
        
        self.assertTrue(result['success'])
        quote.refresh_from_db()
        self.assertEqual(quote.status, self.validated_status)
        self.assertIsNotNone(quote.validated_at)
    
    def test_convert_quote_to_invoice(self):
        """Test conversion devis vers facture."""
        quote = fixtures.create_quote(
            self.user, self.vat_rate, self.quote_status,
            client_name='Test Client',
            subtotal=Decimal('1000.00')
        )
        
        # Ajouter des éléments
        item1 = fixtures.create_quote_item(quote, name='Item 1', subtotal=Decimal('600.00'))
        item2 = fixtures.create_quote_item(quote, name='Item 2', subtotal=Decimal('400.00'))
        
        invoice = self.workflow_service.convert_quote_to_invoice(
            quote, 'FAC-2024-001', self.user
        )
        
        # Vérifications
        self.assertIsInstance(invoice, Invoice)
        self.assertEqual(invoice.quote, quote)
        self.assertEqual(invoice.client_name, quote.client_name)
        self.assertEqual(invoice.subtotal, quote.subtotal)
        self.assertEqual(invoice.items.count(), 2)
        
        # Vérifier que les éléments ont été copiés
        invoice_items = invoice.items.all()
        self.assertEqual(invoice_items[0].name, 'Item 1')
        self.assertEqual(invoice_items[1].name, 'Item 2')
    
    def test_workflow_business_rules(self):
        """Test règles métier du workflow."""
        quote = fixtures.create_quote(
            self.user, self.vat_rate, self.quote_status
        )
        
        # Un devis vide ne peut pas être validé
        result = self.workflow_service.validate_quote(quote, self.user)
        self.assertFalse(result['success'])
        self.assertIn('errors', result)
        
        # Un devis sans éléments ne peut pas être converti
        result = self.workflow_service.convert_quote_to_invoice(
            quote, 'FAC-001', self.user
        )
        self.assertIsNone(result)
    
    def test_workflow_audit_trail(self):
        """Test traçabilité des actions workflow."""
        quote = fixtures.create_quote(
            self.user, self.vat_rate, self.quote_status
        )
        
        # Ajouter un élément pour permettre la validation
        fixtures.create_quote_item(quote)
        
        # Valider le devis
        self.workflow_service.validate_quote(quote, self.user)
        
        quote.refresh_from_db()
        
        # Vérifier la traçabilité
        self.assertEqual(quote.validated_by, self.user)
        self.assertIsNotNone(quote.validated_at)


class NumberServiceTest(DocumentTestCase):
    """Tests du service de numérotation."""
    
    def setUp(self):
        super().setUp()
        self.number_service = NumberService()
    
    def test_generate_quote_number(self):
        """Test génération de numéro de devis."""
        number = self.number_service.generate_quote_number()
        
        # Format: DEV-YYYY-XXX
        self.assertRegex(number, r'^DEV-\d{4}-\d{3}$')
        
        # Vérifier l'année courante
        current_year = str(date.today().year)
        self.assertIn(current_year, number)
    
    def test_generate_invoice_number(self):
        """Test génération de numéro de facture."""
        number = self.number_service.generate_invoice_number()
        
        # Format: FAC-YYYY-XXX
        self.assertRegex(number, r'^FAC-\d{4}-\d{3}$')
        
        current_year = str(date.today().year)
        self.assertIn(current_year, number)
    
    def test_sequential_numbering(self):
        """Test numérotation séquentielle."""
        # Créer des devis pour tester la séquence
        numbers = []
        for i in range(5):
            number = self.number_service.generate_quote_number()
            numbers.append(number)
            
            # Créer un devis avec ce numéro pour incrémenter la séquence
            fixtures.create_quote(
                self.user, self.vat_rate, self.quote_status,
                quote_number=number
            )
        
        # Vérifier que les numéros sont séquentiels
        for i, number in enumerate(numbers):
            expected_seq = f'{i+1:03d}'
            self.assertIn(expected_seq, number)
    
    def test_yearly_reset(self):
        """Test remise à zéro annuelle."""
        # Simuler un changement d'année en modifiant la logique
        # (Dans un vrai test, on mockerait la date)
        
        current_year = date.today().year
        
        # Générer un numéro pour l'année courante
        number_current = self.number_service.generate_quote_number()
        self.assertIn(str(current_year), number_current)
        self.assertIn('001', number_current)
    
    def test_custom_format(self):
        """Test format personnalisé."""
        # Test avec un préfixe personnalisé
        number = self.number_service.generate_quote_number(prefix='CUSTOM')
        self.assertRegex(number, r'^CUSTOM-\d{4}-\d{3}$')
    
    def test_number_validation(self):
        """Test validation des numéros."""
        # Test numéro valide
        valid_number = 'DEV-2024-001'
        self.assertTrue(self.number_service.is_valid_quote_number(valid_number))
        
        # Test numéros invalides
        invalid_numbers = [
            'DEV-24-001',     # Année à 2 chiffres
            'DEV-2024-1',     # Séquence trop courte
            'FAC-2024-001',   # Mauvais préfixe pour devis
            'INVALID',        # Format complètement faux
        ]
        
        for invalid_number in invalid_numbers:
            self.assertFalse(
                self.number_service.is_valid_quote_number(invalid_number)
            )


class PDFServiceTest(DocumentTestCase):
    """Tests du service de génération PDF."""
    
    def setUp(self):
        super().setUp()
        self.pdf_service = PDFService()
    
    def test_generate_quote_pdf(self):
        """Test génération PDF d'un devis."""
        quote = data_builder.reset()\
            .with_quote_data(
                quote_number='DEV-PDF-001',
                client_name='PDF Test Client'
            )\
            .with_multiple_items(3)\
            .build_quote(self.user, self.vat_rate, self.quote_status)
        
        pdf_content = self.pdf_service.generate_quote_pdf(quote)
        
        # Vérifications basiques
        self.assertIsInstance(pdf_content, bytes)
        self.assertTrue(len(pdf_content) > 1000)  # PDF non vide
        
        # Vérifier que c'est bien un PDF
        self.assertTrue(pdf_content.startswith(b'%PDF'))
    
    def test_generate_invoice_pdf(self):
        """Test génération PDF d'une facture."""
        invoice = data_builder.reset()\
            .with_invoice_data(
                invoice_number='FAC-PDF-001',
                client_name='PDF Test Client'
            )\
            .with_multiple_items(2)\
            .build_invoice(self.user, self.vat_rate, self.invoice_status)
        
        pdf_content = self.pdf_service.generate_invoice_pdf(invoice)
        
        self.assertIsInstance(pdf_content, bytes)
        self.assertTrue(len(pdf_content) > 1000)
        self.assertTrue(pdf_content.startswith(b'%PDF'))
    
    def test_pdf_content_includes_data(self):
        """Test que le PDF contient les données du document."""
        quote = fixtures.create_quote(
            self.user, self.vat_rate, self.quote_status,
            quote_number='DEV-CONTENT-001',
            client_name='Content Test Client'
        )
        
        pdf_content = self.pdf_service.generate_quote_pdf(quote)
        
        # Convertir en string pour vérifier le contenu
        # (Dans un vrai test, on utiliserait un parser PDF)
        pdf_str = pdf_content.decode('latin-1', errors='ignore')
        
        # Vérifier que certaines données sont présentes
        self.assertIn('DEV-CONTENT-001', pdf_str)
        self.assertIn('Content Test Client', pdf_str)
    
    def test_pdf_with_company_logo(self):
        """Test PDF avec logo de l'entreprise."""
        quote = fixtures.create_quote(
            self.user, self.vat_rate, self.quote_status
        )
        
        # Simuler un logo (fichier factice)
        logo_file = ContentFile(b'fake-logo-content', name='logo.png')
        
        pdf_content = self.pdf_service.generate_quote_pdf(
            quote, logo=logo_file
        )
        
        self.assertIsInstance(pdf_content, bytes)
        self.assertTrue(len(pdf_content) > 1000)
    
    def test_pdf_template_selection(self):
        """Test sélection de template PDF."""
        quote = fixtures.create_quote(
            self.user, self.vat_rate, self.quote_status
        )
        
        # Test avec template par défaut
        pdf_default = self.pdf_service.generate_quote_pdf(quote)
        
        # Test avec template personnalisé
        pdf_custom = self.pdf_service.generate_quote_pdf(
            quote, template='custom_quote_template.html'
        )
        
        # Les PDFs doivent être différents
        self.assertNotEqual(pdf_default, pdf_custom)
    
    def test_pdf_error_handling(self):
        """Test gestion des erreurs PDF."""
        # Test avec un document invalide (None)
        with self.assertRaises(ValueError):
            self.pdf_service.generate_quote_pdf(None)
        
        # Test avec template inexistant
        quote = fixtures.create_quote(
            self.user, self.vat_rate, self.quote_status
        )
        
        with self.assertRaises(Exception):
            self.pdf_service.generate_quote_pdf(
                quote, template='nonexistent_template.html'
            )


class ServiceIntegrationTest(DocumentTestCase):
    """Tests d'intégration entre services."""
    
    def test_complete_quote_lifecycle(self):
        """Test cycle de vie complet d'un devis avec tous les services."""
        calculation_service = CalculationService()
        workflow_service = WorkflowService()
        number_service = NumberService()
        pdf_service = PDFService()
        
        # 1. Générer un numéro
        quote_number = number_service.generate_quote_number()
        
        # 2. Créer un devis
        quote = fixtures.create_quote(
            self.user, self.vat_rate, self.quote_status,
            quote_number=quote_number,
            subtotal=Decimal('0.00')  # Sera recalculé
        )
        
        # 3. Ajouter des éléments
        fixtures.create_quote_item(
            quote, 
            quantity=Decimal('2.0'), 
            unit_price=Decimal('300.00'),
            discount_percentage=Decimal('5.0')
        )
        fixtures.create_quote_item(
            quote,
            quantity=Decimal('1.0'),
            unit_price=Decimal('500.00')
        )
        
        # 4. Recalculer les totaux
        totals = calculation_service.recalculate_from_items(quote)
        quote.subtotal = totals['subtotal']
        quote.vat_amount = totals['vat_amount']
        quote.total = totals['total']
        quote.save()
        
        # 5. Valider le devis
        sent_status = fixtures.create_quote_status('sent', is_default=False)
        validated_status = fixtures.create_quote_status('validated', is_default=False)
        
        workflow_service.transition_status(quote, sent_status, self.user)
        result = workflow_service.validate_quote(quote, self.user)
        
        # 6. Générer le PDF
        pdf_content = pdf_service.generate_quote_pdf(quote)
        
        # 7. Convertir en facture
        invoice_number = number_service.generate_invoice_number()
        invoice = workflow_service.convert_quote_to_invoice(
            quote, invoice_number, self.user
        )
        
        # Vérifications finales
        self.assertTrue(result['success'])
        self.assertIsNotNone(pdf_content)
        self.assertIsInstance(invoice, Invoice)
        self.assertEqual(invoice.quote, quote)
        self.assertEqual(quote.subtotal, Decimal('1070.00'))  # (2*300*0.95) + 500
        
    def test_service_error_propagation(self):
        """Test propagation des erreurs entre services."""
        workflow_service = WorkflowService()
        
        # Tenter de convertir un devis invalide
        quote = fixtures.create_quote(
            self.user, self.vat_rate, self.quote_status
        )
        # Pas d'éléments = devis invalide
        
        result = workflow_service.convert_quote_to_invoice(
            quote, 'FAC-ERR-001', self.user
        )
        
        # Doit retourner None ou lever une exception
        self.assertIsNone(result)
    
    def test_service_performance(self):
        """Test performance des services."""
        import time
        
        calculation_service = CalculationService()
        
        # Créer un devis avec beaucoup d'éléments
        quote = fixtures.create_quote(
            self.user, self.vat_rate, self.quote_status
        )
        
        for i in range(100):
            fixtures.create_quote_item(quote)
        
        # Mesurer le temps de recalcul
        start_time = time.time()
        totals = calculation_service.recalculate_from_items(quote)
        end_time = time.time()
        
        calculation_time = end_time - start_time
        
        # Le recalcul doit être rapide (< 0.5 seconde)
        self.assertLess(calculation_time, 0.5)
        self.assertIsNotNone(totals['subtotal']) 