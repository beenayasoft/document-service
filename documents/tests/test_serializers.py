"""
Tests des serializers et mixins pour le document-service.
"""
from decimal import Decimal
from datetime import date, timedelta
from django.test import TestCase
from rest_framework import serializers
from rest_framework.test import APIRequestFactory
from documents.tests.fixtures import DocumentTestCase, fixtures, data_builder
from documents.serializers import (
    VATRateSerializer, QuoteStatusSerializer, InvoiceStatusSerializer,
    PaymentMethodSerializer, QuoteSerializer, QuoteDetailSerializer,
    QuoteCreateSerializer, InvoiceSerializer, InvoiceDetailSerializer,
    InvoiceCreateSerializer, QuoteItemSerializer, InvoiceItemSerializer,
    PaymentSerializer, QuoteStatsSerializer, InvoiceStatsSerializer
)
from documents.mixins import (
    DocumentValidationMixin, DateValidationMixin, BaseDocumentMixin,
    BaseDocumentItemMixin, DocumentStatsBaseMixin, ClientInfoMixin,
    RelatedDocumentMixin, BulkOperationMixin, CalculationMixin
)


class VATRateSerializerTest(DocumentTestCase):
    """Tests du serializer VATRate."""
    
    def test_vat_rate_serialization(self):
        """Test sérialisation d'un taux de TVA."""
        vat_rate = fixtures.create_vat_rate(rate=19.6, name='TVA Normale')
        serializer = VATRateSerializer(vat_rate)
        
        data = serializer.data
        self.assertEqual(data['name'], 'TVA Normale')
        self.assertEqual(float(data['rate']), 19.6)
        self.assertTrue(data['is_active'])
    
    def test_vat_rate_deserialization(self):
        """Test désérialisation d'un taux de TVA."""
        data = {
            'name': 'TVA Export',
            'rate': '0.00',
            'is_active': True
        }
        
        serializer = VATRateSerializer(data=data)
        self.assertTrue(serializer.is_valid())
        
        vat_rate = serializer.save()
        self.assertEqual(vat_rate.name, 'TVA Export')
        self.assertEqual(vat_rate.rate, Decimal('0.00'))
    
    def test_vat_rate_validation(self):
        """Test validation du taux de TVA."""
        # Taux négatif
        data = {'name': 'Invalid', 'rate': '-5.0', 'is_active': True}
        serializer = VATRateSerializer(data=data)
        self.assertFalse(serializer.is_valid())
        self.assertIn('rate', serializer.errors)
        
        # Taux trop élevé
        data = {'name': 'Invalid', 'rate': '101.0', 'is_active': True}
        serializer = VATRateSerializer(data=data)
        self.assertFalse(serializer.is_valid())


class DocumentValidationMixinTest(DocumentTestCase):
    """Tests du mixin DocumentValidationMixin."""
    
    def setUp(self):
        super().setUp()
        
        # Créer une classe de test utilisant le mixin
        class TestSerializer(DocumentValidationMixin, serializers.Serializer):
            subtotal = serializers.DecimalField(max_digits=10, decimal_places=2)
            vat_amount = serializers.DecimalField(max_digits=10, decimal_places=2)
            total = serializers.DecimalField(max_digits=10, decimal_places=2)
            discount_percentage = serializers.DecimalField(
                max_digits=5, decimal_places=2, required=False
            )
        
        self.TestSerializer = TestSerializer
    
    def test_financial_validation_success(self):
        """Test validation financière réussie."""
        data = {
            'subtotal': '1000.00',
            'vat_amount': '200.00',
            'total': '1200.00'
        }
        
        serializer = self.TestSerializer(data=data)
        self.assertTrue(serializer.is_valid())
    
    def test_financial_validation_mismatch(self):
        """Test validation financière en cas d'incohérence."""
        data = {
            'subtotal': '1000.00',
            'vat_amount': '200.00',
            'total': '1500.00'  # Erreur : 1000 + 200 ≠ 1500
        }
        
        serializer = self.TestSerializer(data=data)
        self.assertFalse(serializer.is_valid())
        self.assertIn('non_field_errors', serializer.errors)
    
    def test_discount_validation(self):
        """Test validation des remises."""
        # Remise négative
        data = {
            'subtotal': '1000.00',
            'vat_amount': '200.00',
            'total': '1200.00',
            'discount_percentage': '-10.00'
        }
        
        serializer = self.TestSerializer(data=data)
        self.assertFalse(serializer.is_valid())
        
        # Remise trop élevée
        data['discount_percentage'] = '101.00'
        serializer = self.TestSerializer(data=data)
        self.assertFalse(serializer.is_valid())


class DateValidationMixinTest(DocumentTestCase):
    """Tests du mixin DateValidationMixin."""
    
    def setUp(self):
        super().setUp()
        
        class TestSerializer(DateValidationMixin, serializers.Serializer):
            created_at = serializers.DateField()
            valid_until = serializers.DateField(required=False)
            due_date = serializers.DateField(required=False)
        
        self.TestSerializer = TestSerializer
    
    def test_date_consistency_validation(self):
        """Test validation de cohérence des dates."""
        today = date.today()
        future_date = today + timedelta(days=30)
        
        # Dates cohérentes
        data = {
            'created_at': today.isoformat(),
            'valid_until': future_date.isoformat()
        }
        
        serializer = self.TestSerializer(data=data)
        self.assertTrue(serializer.is_valid())
        
        # Date de validité dans le passé
        past_date = today - timedelta(days=10)
        data['valid_until'] = past_date.isoformat()
        
        serializer = self.TestSerializer(data=data)
        self.assertFalse(serializer.is_valid())


class QuoteSerializerTest(DocumentTestCase):
    """Tests du serializer Quote."""
    
    def test_quote_serialization(self):
        """Test sérialisation d'un devis."""
        quote = fixtures.create_quote(
            self.user, self.vat_rate, self.quote_status,
            quote_number='DEV-2024-001',
            client_name='Test Client'
        )
        
        serializer = QuoteSerializer(quote)
        data = serializer.data
        
        self.assertEqual(data['quote_number'], 'DEV-2024-001')
        self.assertEqual(data['client_name'], 'Test Client')
        self.assertIn('created_by', data)
        self.assertIn('vat_rate', data)
        self.assertIn('status', data)
    
    def test_quote_creation(self):
        """Test création d'un devis via serializer."""
        data = {
            'quote_number': 'DEV-2024-002',
            'client_name': 'New Client',
            'client_email': 'client@test.com',
            'subtotal': '1500.00',
            'vat_rate': self.vat_rate.id,
            'status': self.quote_status.id,
            'valid_until': (date.today() + timedelta(days=30)).isoformat()
        }
        
        serializer = QuoteCreateSerializer(data=data)
        self.assertTrue(serializer.is_valid(), serializer.errors)
        
        quote = serializer.save(created_by=self.user)
        self.assertEqual(quote.client_name, 'New Client')
        self.assertEqual(quote.subtotal, Decimal('1500.00'))
    
    def test_quote_with_items_serialization(self):
        """Test sérialisation d'un devis avec éléments."""
        quote = data_builder.reset()\
            .with_quote_data(quote_number='DEV-2024-003')\
            .with_multiple_items(2)\
            .build_quote(self.user, self.vat_rate, self.quote_status)
        
        serializer = QuoteDetailSerializer(quote)
        data = serializer.data
        
        self.assertIn('items', data)
        self.assertEqual(len(data['items']), 2)
        self.assertIn('total_items', data)
        self.assertEqual(data['total_items'], 2)


class InvoiceSerializerTest(DocumentTestCase):
    """Tests du serializer Invoice."""
    
    def test_invoice_serialization(self):
        """Test sérialisation d'une facture."""
        invoice = fixtures.create_invoice(
            self.user, self.vat_rate, self.invoice_status,
            invoice_number='FAC-2024-001'
        )
        
        serializer = InvoiceSerializer(invoice)
        data = serializer.data
        
        self.assertEqual(data['invoice_number'], 'FAC-2024-001')
        self.assertIn('created_by', data)
        self.assertIn('payment_status', data)
    
    def test_invoice_payment_tracking(self):
        """Test suivi des paiements dans la sérialisation."""
        invoice = fixtures.create_invoice(
            self.user, self.vat_rate, self.invoice_status,
            total=Decimal('1000.00')
        )
        
        # Créer un paiement partiel
        fixtures.create_payment(
            invoice, self.payment_method,
            amount=Decimal('400.00')
        )
        
        serializer = InvoiceDetailSerializer(invoice)
        data = serializer.data
        
        self.assertIn('payments', data)
        self.assertEqual(len(data['payments']), 1)
        self.assertIn('total_paid', data)
        self.assertEqual(float(data['total_paid']), 400.00)
        self.assertIn('remaining_amount', data)
        self.assertEqual(float(data['remaining_amount']), 600.00)
    
    def test_invoice_from_quote_creation(self):
        """Test création de facture depuis un devis."""
        quote = fixtures.create_quote(
            self.user, self.vat_rate, self.quote_status
        )
        
        data = {
            'invoice_number': 'FAC-2024-002',
            'quote': quote.id,
            'due_date': (date.today() + timedelta(days=30)).isoformat()
        }
        
        serializer = InvoiceCreateSerializer(data=data)
        self.assertTrue(serializer.is_valid(), serializer.errors)
        
        invoice = serializer.save(created_by=self.user)
        self.assertEqual(invoice.quote, quote)
        self.assertEqual(invoice.client_name, quote.client_name)
        self.assertEqual(invoice.subtotal, quote.subtotal)


class QuoteItemSerializerTest(DocumentTestCase):
    """Tests du serializer QuoteItem."""
    
    def test_quote_item_serialization(self):
        """Test sérialisation d'un élément de devis."""
        quote = fixtures.create_quote(
            self.user, self.vat_rate, self.quote_status
        )
        
        item = fixtures.create_quote_item(
            quote,
            name='Service Test',
            quantity=Decimal('2.0'),
            unit_price=Decimal('150.00')
        )
        
        serializer = QuoteItemSerializer(item)
        data = serializer.data
        
        self.assertEqual(data['name'], 'Service Test')
        self.assertEqual(float(data['quantity']), 2.0)
        self.assertEqual(float(data['unit_price']), 150.00)
    
    def test_quote_item_hierarchy_serialization(self):
        """Test sérialisation de la hiérarchie des éléments."""
        quote = fixtures.create_quote(
            self.user, self.vat_rate, self.quote_status
        )
        
        # Créer une hiérarchie
        chapter = fixtures.create_quote_item(
            quote, name='Chapitre 1', item_type='chapter'
        )
        section = fixtures.create_quote_item(
            quote, name='Section 1.1', item_type='section', parent=chapter
        )
        item = fixtures.create_quote_item(
            quote, name='Item 1.1.1', item_type='item', parent=section
        )
        
        serializer = QuoteItemSerializer(chapter)
        data = serializer.data
        
        self.assertEqual(data['item_type'], 'chapter')
        self.assertIn('children', data)
        self.assertEqual(len(data['children']), 1)


class PaymentSerializerTest(DocumentTestCase):
    """Tests du serializer Payment."""
    
    def test_payment_serialization(self):
        """Test sérialisation d'un paiement."""
        invoice = fixtures.create_invoice(
            self.user, self.vat_rate, self.invoice_status
        )
        
        payment = fixtures.create_payment(
            invoice, self.payment_method,
            amount=Decimal('750.00'),
            reference='PAY-001'
        )
        
        serializer = PaymentSerializer(payment)
        data = serializer.data
        
        self.assertEqual(float(data['amount']), 750.00)
        self.assertEqual(data['reference'], 'PAY-001')
        self.assertIn('payment_method', data)
    
    def test_payment_validation(self):
        """Test validation des paiements."""
        invoice = fixtures.create_invoice(
            self.user, self.vat_rate, self.invoice_status,
            total=Decimal('1000.00')
        )
        
        # Paiement valide
        data = {
            'invoice': invoice.id,
            'payment_method': self.payment_method.id,
            'amount': '500.00',
            'payment_date': date.today().isoformat(),
            'reference': 'TEST-001'
        }
        
        serializer = PaymentSerializer(data=data)
        self.assertTrue(serializer.is_valid())
        
        # Paiement trop élevé
        data['amount'] = '1500.00'
        serializer = PaymentSerializer(data=data)
        self.assertFalse(serializer.is_valid())


class StatsSerializerTest(DocumentTestCase):
    """Tests des serializers de statistiques."""
    
    def setUp(self):
        super().setUp()
        
        # Créer des données de test
        self.quote1 = fixtures.create_quote(
            self.user, self.vat_rate, self.quote_status,
            total=Decimal('1000.00')
        )
        self.quote2 = fixtures.create_quote(
            self.user, self.vat_rate, self.quote_status,
            total=Decimal('2000.00')
        )
        
        self.invoice1 = fixtures.create_invoice(
            self.user, self.vat_rate, self.invoice_status,
            total=Decimal('1500.00')
        )
        self.invoice2 = fixtures.create_invoice(
            self.user, self.vat_rate, self.invoice_status,
            total=Decimal('2500.00')
        )
    
    def test_quote_stats_serialization(self):
        """Test sérialisation des stats de devis."""
        from documents.models import Quote
        
        stats = {
            'total_count': Quote.objects.count(),
            'total_amount': sum(q.total for q in Quote.objects.all()),
            'by_status': {}
        }
        
        serializer = QuoteStatsSerializer(stats)
        data = serializer.data
        
        self.assertIn('total_count', data)
        self.assertIn('total_amount', data)
        self.assertIn('by_status', data)
        self.assertEqual(data['total_count'], 2)
    
    def test_invoice_stats_serialization(self):
        """Test sérialisation des stats de factures."""
        from documents.models import Invoice
        
        stats = {
            'total_count': Invoice.objects.count(),
            'total_amount': sum(i.total for i in Invoice.objects.all()),
            'paid_amount': Decimal('0.00'),
            'overdue_count': 0
        }
        
        serializer = InvoiceStatsSerializer(stats)
        data = serializer.data
        
        self.assertIn('total_count', data)
        self.assertIn('total_amount', data)
        self.assertIn('paid_amount', data)
        self.assertIn('overdue_count', data)


class CalculationMixinTest(DocumentTestCase):
    """Tests du mixin CalculationMixin."""
    
    def setUp(self):
        super().setUp()
        
        class TestSerializer(CalculationMixin, serializers.Serializer):
            subtotal = serializers.DecimalField(max_digits=10, decimal_places=2)
            vat_rate = serializers.DecimalField(max_digits=5, decimal_places=2)
            discount_percentage = serializers.DecimalField(
                max_digits=5, decimal_places=2, required=False, default=0
            )
        
        self.TestSerializer = TestSerializer
    
    def test_automatic_calculations(self):
        """Test calculs automatiques."""
        data = {
            'subtotal': '1000.00',
            'vat_rate': '20.00',
            'discount_percentage': '10.00'
        }
        
        serializer = self.TestSerializer(data=data)
        self.assertTrue(serializer.is_valid())
        
        # Vérifier que les calculs sont effectués
        calculated = serializer.perform_calculations(serializer.validated_data)
        
        self.assertEqual(calculated['discount_amount'], Decimal('100.00'))
        self.assertEqual(calculated['subtotal_after_discount'], Decimal('900.00'))
        self.assertEqual(calculated['vat_amount'], Decimal('180.00'))
        self.assertEqual(calculated['total'], Decimal('1080.00'))


class BulkOperationMixinTest(DocumentTestCase):
    """Tests du mixin BulkOperationMixin."""
    
    def setUp(self):
        super().setUp()
        
        class TestSerializer(BulkOperationMixin, serializers.Serializer):
            action = serializers.CharField()
            ids = serializers.ListField(child=serializers.UUIDField())
        
        self.TestSerializer = TestSerializer
    
    def test_bulk_validation(self):
        """Test validation des opérations en lot."""
        # Créer des devis de test
        quote1 = fixtures.create_quote(self.user, self.vat_rate, self.quote_status)
        quote2 = fixtures.create_quote(self.user, self.vat_rate, self.quote_status)
        
        data = {
            'action': 'validate',
            'ids': [str(quote1.id), str(quote2.id)]
        }
        
        serializer = self.TestSerializer(data=data)
        self.assertTrue(serializer.is_valid())
        
        # Test avec IDs invalides
        data['ids'] = ['invalid-uuid']
        serializer = self.TestSerializer(data=data)
        self.assertFalse(serializer.is_valid())


class SerializerIntegrationTest(DocumentTestCase):
    """Tests d'intégration des serializers."""
    
    def test_complete_quote_workflow(self):
        """Test workflow complet d'un devis via serializers."""
        # 1. Créer un devis
        quote_data = {
            'quote_number': 'DEV-INT-001',
            'client_name': 'Integration Test Client',
            'client_email': 'integration@test.com',
            'subtotal': '1000.00',
            'vat_rate': self.vat_rate.id,
            'status': self.quote_status.id,
            'valid_until': (date.today() + timedelta(days=30)).isoformat()
        }
        
        quote_serializer = QuoteCreateSerializer(data=quote_data)
        self.assertTrue(quote_serializer.is_valid())
        quote = quote_serializer.save(created_by=self.user)
        
        # 2. Ajouter des éléments
        item_data = {
            'quote': quote.id,
            'name': 'Service Integration',
            'quantity': '2.0',
            'unit_price': '500.00',
            'order': 1
        }
        
        item_serializer = QuoteItemSerializer(data=item_data)
        self.assertTrue(item_serializer.is_valid())
        item = item_serializer.save()
        
        # 3. Convertir en facture
        invoice_data = {
            'invoice_number': 'FAC-INT-001',
            'quote': quote.id,
            'due_date': (date.today() + timedelta(days=30)).isoformat()
        }
        
        invoice_serializer = InvoiceCreateSerializer(data=invoice_data)
        self.assertTrue(invoice_serializer.is_valid())
        invoice = invoice_serializer.save(created_by=self.user)
        
        # 4. Enregistrer un paiement
        payment_data = {
            'invoice': invoice.id,
            'payment_method': self.payment_method.id,
            'amount': str(invoice.total),
            'payment_date': date.today().isoformat(),
            'reference': 'INT-PAY-001'
        }
        
        payment_serializer = PaymentSerializer(data=payment_data)
        self.assertTrue(payment_serializer.is_valid())
        payment = payment_serializer.save()
        
        # Vérifications finales
        self.assertEqual(invoice.quote, quote)
        self.assertEqual(invoice.items.count(), quote.items.count())
        self.assertTrue(invoice.is_fully_paid())
    
    def test_nested_serialization_performance(self):
        """Test performance de sérialisation imbriquée."""
        # Créer un devis avec beaucoup d'éléments
        quote = fixtures.create_quote(
            self.user, self.vat_rate, self.quote_status
        )
        
        # Créer 50 éléments
        for i in range(50):
            fixtures.create_quote_item(
                quote,
                name=f'Item {i+1}',
                quantity=Decimal('1.0'),
                unit_price=Decimal(f'{i+1}.00')
            )
        
        # Test de sérialisation
        import time
        start_time = time.time()
        
        serializer = QuoteDetailSerializer(quote)
        data = serializer.data
        
        end_time = time.time()
        serialization_time = end_time - start_time
        
        # Vérifier que la sérialisation est rapide (< 1 seconde)
        self.assertLess(serialization_time, 1.0)
        self.assertEqual(len(data['items']), 50) 