"""
Tests des modèles Django pour le document-service.
"""
from decimal import Decimal
from django.test import TestCase
from django.core.exceptions import ValidationError
from django.db.utils import IntegrityError
from documents.tests.fixtures import DocumentTestCase, fixtures, data_builder
from documents.models import (
    VATRate, QuoteStatus, InvoiceStatus, PaymentMethod,
    Quote, Invoice, QuoteItem, InvoiceItem, Payment
)


class VATRateModelTest(DocumentTestCase):
    """Tests du modèle VATRate."""
    
    def test_create_vat_rate(self):
        """Test création d'un taux de TVA."""
        vat_rate = VATRate.objects.create(
            name='TVA Réduite',
            rate=Decimal('5.5'),
            is_active=True
        )
        
        self.assertEqual(vat_rate.name, 'TVA Réduite')
        self.assertEqual(vat_rate.rate, Decimal('5.5'))
        self.assertTrue(vat_rate.is_active)
        self.assertIsNotNone(vat_rate.created_at)
    
    def test_vat_rate_string_representation(self):
        """Test représentation string du taux de TVA."""
        vat_rate = fixtures.create_vat_rate(rate=10.0, name='TVA Intermédiaire')
        self.assertEqual(str(vat_rate), 'TVA Intermédiaire (10.00%)')
    
    def test_vat_rate_validation(self):
        """Test validation du taux de TVA."""
        # Taux négatif
        with self.assertRaises(ValidationError):
            vat_rate = VATRate(name='Invalid', rate=Decimal('-5.0'))
            vat_rate.full_clean()
        
        # Taux trop élevé
        with self.assertRaises(ValidationError):
            vat_rate = VATRate(name='Invalid', rate=Decimal('101.0'))
            vat_rate.full_clean()


class QuoteStatusModelTest(DocumentTestCase):
    """Tests du modèle QuoteStatus."""
    
    def test_create_quote_status(self):
        """Test création d'un statut de devis."""
        status = QuoteStatus.objects.create(
            name='validated',
            label='Validé',
            is_default=False,
            can_be_edited=False,
            order=2
        )
        
        self.assertEqual(status.name, 'validated')
        self.assertEqual(status.label, 'Validé')
        self.assertFalse(status.can_be_edited)
    
    def test_quote_status_ordering(self):
        """Test ordering des statuts de devis."""
        status1 = fixtures.create_quote_status('draft', is_default=True)
        status2 = QuoteStatus.objects.create(
            name='validated', label='Validé', order=2
        )
        status3 = QuoteStatus.objects.create(
            name='sent', label='Envoyé', order=1
        )
        
        statuses = list(QuoteStatus.objects.all())
        self.assertEqual(statuses[0].order, 1)
        self.assertEqual(statuses[1].order, 1)  # Default order
        self.assertEqual(statuses[2].order, 2)


class QuoteModelTest(DocumentTestCase):
    """Tests du modèle Quote."""
    
    def test_create_quote(self):
        """Test création d'un devis."""
        quote = fixtures.create_quote(
            self.user, self.vat_rate, self.quote_status,
            quote_number='DEV-2024-001',
            client_name='ACME Corp'
        )
        
        self.assertEqual(quote.quote_number, 'DEV-2024-001')
        self.assertEqual(quote.client_name, 'ACME Corp')
        self.assertEqual(quote.created_by, self.user)
        self.assertEqual(quote.vat_rate, self.vat_rate)
        self.assertIsNotNone(quote.id)  # UUID généré
    
    def test_quote_calculations(self):
        """Test calculs automatiques du devis."""
        quote = fixtures.create_quote(
            self.user, self.vat_rate, self.quote_status,
            subtotal=Decimal('1000.00')
        )
        
        # Test recalcul automatique
        quote.recalculate_totals()
        
        expected_vat = Decimal('1000.00') * self.vat_rate.rate / 100
        expected_total = Decimal('1000.00') + expected_vat
        
        self.assertEqual(quote.vat_amount, expected_vat)
        self.assertEqual(quote.total, expected_total)
    
    def test_quote_workflow_methods(self):
        """Test méthodes de workflow du devis."""
        quote = fixtures.create_quote(
            self.user, self.vat_rate, self.quote_status
        )
        
        # Test can_be_edited
        self.assertTrue(quote.can_be_edited())
        
        # Test send
        quote.send()
        # Vérifier que le statut a changé si applicable
        
        # Test validate
        quote.validate()
        
        # Test convert_to_invoice
        invoice = quote.convert_to_invoice()
        self.assertIsInstance(invoice, Invoice)
        self.assertEqual(invoice.subtotal, quote.subtotal)
        self.assertEqual(invoice.total, quote.total)
    
    def test_quote_with_items(self):
        """Test devis avec éléments."""
        quote = data_builder.reset()\
            .with_quote_data(quote_number='DEV-2024-002')\
            .with_multiple_items(3)\
            .build_quote(self.user, self.vat_rate, self.quote_status)
        
        self.assertEqual(quote.items.count(), 3)
        
        # Test recalcul basé sur les éléments
        quote.recalculate_from_items()
        
        expected_subtotal = sum(item.subtotal for item in quote.items.all())
        self.assertEqual(quote.subtotal, expected_subtotal)
    
    def test_quote_discounts(self):
        """Test gestion des remises."""
        quote = fixtures.create_quote(
            self.user, self.vat_rate, self.quote_status,
            subtotal=Decimal('1000.00'),
            discount_percentage=Decimal('10.0')
        )
        
        quote.apply_discount()
        
        self.assertEqual(quote.discount_amount, Decimal('100.00'))
        self.assertEqual(quote.subtotal_after_discount, Decimal('900.00'))


class InvoiceModelTest(DocumentTestCase):
    """Tests du modèle Invoice."""
    
    def test_create_invoice(self):
        """Test création d'une facture."""
        invoice = fixtures.create_invoice(
            self.user, self.vat_rate, self.invoice_status,
            invoice_number='FAC-2024-001'
        )
        
        self.assertEqual(invoice.invoice_number, 'FAC-2024-001')
        self.assertEqual(invoice.created_by, self.user)
        self.assertIsNotNone(invoice.id)
    
    def test_invoice_payment_tracking(self):
        """Test suivi des paiements."""
        invoice = fixtures.create_invoice(
            self.user, self.vat_rate, self.invoice_status,
            total=Decimal('1200.00')
        )
        
        # Créer des paiements partiels
        payment1 = fixtures.create_payment(
            invoice, self.payment_method,
            amount=Decimal('500.00')
        )
        payment2 = fixtures.create_payment(
            invoice, self.payment_method,
            amount=Decimal('700.00')
        )
        
        # Test calculs de paiement
        self.assertEqual(invoice.get_total_paid(), Decimal('1200.00'))
        self.assertEqual(invoice.get_remaining_amount(), Decimal('0.00'))
        self.assertTrue(invoice.is_fully_paid())
    
    def test_invoice_overdue_calculation(self):
        """Test calcul des retards de paiement."""
        from datetime import date, timedelta
        
        past_due_date = date.today() - timedelta(days=30)
        invoice = fixtures.create_invoice(
            self.user, self.vat_rate, self.invoice_status,
            due_date=past_due_date
        )
        
        self.assertTrue(invoice.is_overdue())
        self.assertEqual(invoice.get_days_overdue(), 30)
    
    def test_invoice_from_quote(self):
        """Test création de facture depuis un devis."""
        quote = fixtures.create_quote(
            self.user, self.vat_rate, self.quote_status
        )
        
        # Ajouter des éléments au devis
        fixtures.create_quote_item(quote, name='Item 1', subtotal=Decimal('500.00'))
        fixtures.create_quote_item(quote, name='Item 2', subtotal=Decimal('300.00'))
        
        # Convertir en facture
        invoice = quote.convert_to_invoice()
        
        self.assertEqual(invoice.items.count(), 2)
        self.assertEqual(invoice.subtotal, quote.subtotal)
        self.assertIsNotNone(invoice.quote)


class QuoteItemModelTest(DocumentTestCase):
    """Tests du modèle QuoteItem."""
    
    def test_create_quote_item(self):
        """Test création d'un élément de devis."""
        quote = fixtures.create_quote(
            self.user, self.vat_rate, self.quote_status
        )
        
        item = fixtures.create_quote_item(
            quote,
            name='Prestation test',
            quantity=Decimal('2.5'),
            unit_price=Decimal('100.00')
        )
        
        self.assertEqual(item.name, 'Prestation test')
        self.assertEqual(item.quantity, Decimal('2.5'))
        self.assertEqual(item.unit_price, Decimal('100.00'))
    
    def test_quote_item_calculations(self):
        """Test calculs automatiques d'un élément."""
        quote = fixtures.create_quote(
            self.user, self.vat_rate, self.quote_status
        )
        
        item = QuoteItem.objects.create(
            quote=quote,
            name='Test Item',
            quantity=Decimal('3.0'),
            unit_price=Decimal('150.00'),
            discount_percentage=Decimal('10.0'),
            order=1
        )
        
        item.calculate_subtotal()
        
        expected_gross = Decimal('3.0') * Decimal('150.00')  # 450.00
        expected_discount = expected_gross * Decimal('10.0') / 100  # 45.00
        expected_subtotal = expected_gross - expected_discount  # 405.00
        
        self.assertEqual(item.subtotal, expected_subtotal)
    
    def test_quote_item_hierarchy(self):
        """Test hiérarchie des éléments (chapitres, sections)."""
        quote = fixtures.create_quote(
            self.user, self.vat_rate, self.quote_status
        )
        
        # Créer un chapitre
        chapter = QuoteItem.objects.create(
            quote=quote,
            name='Chapitre 1',
            item_type='chapter',
            order=1
        )
        
        # Créer une section dans le chapitre
        section = QuoteItem.objects.create(
            quote=quote,
            name='Section 1.1',
            item_type='section',
            parent=chapter,
            order=1
        )
        
        # Créer un élément dans la section
        item = QuoteItem.objects.create(
            quote=quote,
            name='Élément 1.1.1',
            item_type='item',
            parent=section,
            quantity=Decimal('1.0'),
            unit_price=Decimal('100.00'),
            order=1
        )
        
        self.assertEqual(chapter.children.count(), 1)
        self.assertEqual(section.children.count(), 1)
        self.assertEqual(item.parent, section)


class PaymentModelTest(DocumentTestCase):
    """Tests du modèle Payment."""
    
    def test_create_payment(self):
        """Test création d'un paiement."""
        invoice = fixtures.create_invoice(
            self.user, self.vat_rate, self.invoice_status
        )
        
        payment = fixtures.create_payment(
            invoice, self.payment_method,
            amount=Decimal('600.00'),
            reference='VIR-001'
        )
        
        self.assertEqual(payment.amount, Decimal('600.00'))
        self.assertEqual(payment.reference, 'VIR-001')
        self.assertEqual(payment.invoice, invoice)
    
    def test_payment_validation(self):
        """Test validation des paiements."""
        invoice = fixtures.create_invoice(
            self.user, self.vat_rate, self.invoice_status,
            total=Decimal('1000.00')
        )
        
        # Paiement supérieur au montant de la facture
        with self.assertRaises(ValidationError):
            payment = Payment(
                invoice=invoice,
                payment_method=self.payment_method,
                amount=Decimal('1500.00'),
                payment_date='2024-01-15'
            )
            payment.full_clean()
    
    def test_multiple_payments(self):
        """Test gestion de multiples paiements."""
        invoice = fixtures.create_invoice(
            self.user, self.vat_rate, self.invoice_status,
            total=Decimal('1000.00')
        )
        
        # Créer plusieurs paiements
        fixtures.create_payment(invoice, self.payment_method, amount=Decimal('300.00'))
        fixtures.create_payment(invoice, self.payment_method, amount=Decimal('400.00'))
        fixtures.create_payment(invoice, self.payment_method, amount=Decimal('300.00'))
        
        self.assertEqual(invoice.payments.count(), 3)
        self.assertEqual(invoice.get_total_paid(), Decimal('1000.00'))
        self.assertTrue(invoice.is_fully_paid())


class ModelRelationshipsTest(DocumentTestCase):
    """Tests des relations entre modèles."""
    
    def test_quote_to_invoice_relationship(self):
        """Test relation devis vers facture."""
        quote = fixtures.create_quote(
            self.user, self.vat_rate, self.quote_status
        )
        
        invoice = quote.convert_to_invoice()
        
        # Vérifier la relation bidirectionnelle
        self.assertEqual(invoice.quote, quote)
        self.assertIn(invoice, quote.invoices.all())
    
    def test_cascade_deletions(self):
        """Test suppressions en cascade."""
        quote = fixtures.create_quote(
            self.user, self.vat_rate, self.quote_status
        )
        
        # Créer des éléments
        item1 = fixtures.create_quote_item(quote)
        item2 = fixtures.create_quote_item(quote)
        
        quote_id = quote.id
        item_ids = [item1.id, item2.id]
        
        # Supprimer le devis
        quote.delete()
        
        # Vérifier que les éléments ont été supprimés
        self.assertEqual(QuoteItem.objects.filter(id__in=item_ids).count(), 0)
    
    def test_user_relationships(self):
        """Test relations avec l'utilisateur."""
        # Créer plusieurs documents pour l'utilisateur
        quote1 = fixtures.create_quote(self.user, self.vat_rate, self.quote_status)
        quote2 = fixtures.create_quote(self.user, self.vat_rate, self.quote_status)
        invoice1 = fixtures.create_invoice(self.user, self.vat_rate, self.invoice_status)
        
        # Vérifier les relations inverses
        user_quotes = Quote.objects.filter(created_by=self.user)
        user_invoices = Invoice.objects.filter(created_by=self.user)
        
        self.assertEqual(user_quotes.count(), 2)
        self.assertEqual(user_invoices.count(), 1)


class ModelValidationTest(DocumentTestCase):
    """Tests de validation des modèles."""
    
    def test_quote_number_uniqueness(self):
        """Test unicité des numéros de devis."""
        fixtures.create_quote(
            self.user, self.vat_rate, self.quote_status,
            quote_number='DEV-2024-001'
        )
        
        # Tentative de création d'un devis avec le même numéro
        with self.assertRaises(IntegrityError):
            fixtures.create_quote(
                self.user, self.vat_rate, self.quote_status,
                quote_number='DEV-2024-001'
            )
    
    def test_invoice_number_uniqueness(self):
        """Test unicité des numéros de facture."""
        fixtures.create_invoice(
            self.user, self.vat_rate, self.invoice_status,
            invoice_number='FAC-2024-001'
        )
        
        with self.assertRaises(IntegrityError):
            fixtures.create_invoice(
                self.user, self.vat_rate, self.invoice_status,
                invoice_number='FAC-2024-001'
            )
    
    def test_financial_calculations_precision(self):
        """Test précision des calculs financiers."""
        quote = fixtures.create_quote(
            self.user, self.vat_rate, self.quote_status,
            subtotal=Decimal('999.999')  # 3 décimales
        )
        
        quote.recalculate_totals()
        
        # Vérifier que les montants sont arrondis à 2 décimales
        self.assertEqual(quote.subtotal.as_tuple().exponent, -2)
        self.assertEqual(quote.vat_amount.as_tuple().exponent, -2)
        self.assertEqual(quote.total.as_tuple().exponent, -2) 