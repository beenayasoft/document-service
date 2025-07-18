"""
Fixtures et utilitaires de test pour le document-service.
"""
import pytest
from decimal import Decimal
from django.contrib.auth.models import User
from django.test import TestCase
from django.db import connection
from rest_framework.test import APITestCase, APIClient
from documents.models import (
    VATRate, QuoteStatus, InvoiceStatus, PaymentMethod,
    Quote, Invoice, QuoteItem, InvoiceItem, Payment
)


class MultiTenantTestMixin:
    """Mixin pour les tests multi-tenant."""
    
    def setUp(self):
        super().setUp()
        self.tenant_id = 'test_tenant_123'
        self.create_tenant_schema()
        
    def create_tenant_schema(self):
        """Crée un schéma de test pour le tenant."""
        with connection.cursor() as cursor:
            cursor.execute(f'CREATE SCHEMA IF NOT EXISTS "{self.tenant_id}"')
            cursor.execute(f'SET search_path TO "{self.tenant_id}", public')
            
    def tearDown(self):
        """Nettoie le schéma de test."""
        with connection.cursor() as cursor:
            cursor.execute(f'DROP SCHEMA IF EXISTS "{self.tenant_id}" CASCADE')
        super().tearDown()
        
    def set_tenant_header(self):
        """Configure le header X-Tenant-ID pour l'API client."""
        if hasattr(self, 'client'):
            self.client.defaults['HTTP_X_TENANT_ID'] = self.tenant_id


class DocumentTestFixtures:
    """Fixtures pour créer des données de test."""
    
    @staticmethod
    def create_user(username='testuser', email='test@example.com'):
        """Crée un utilisateur de test."""
        return User.objects.create_user(
            username=username,
            email=email,
            password='testpass123'
        )
    
    @staticmethod
    def create_vat_rate(rate=20.0, name='TVA Standard'):
        """Crée un taux de TVA de test."""
        return VATRate.objects.create(
            name=name,
            rate=Decimal(str(rate)),
            is_active=True
        )
    
    @staticmethod
    def create_quote_status(name='draft', is_default=True):
        """Crée un statut de devis de test."""
        return QuoteStatus.objects.create(
            name=name,
            label=name.title(),
            is_default=is_default,
            order=1
        )
    
    @staticmethod
    def create_invoice_status(name='draft', is_default=True):
        """Crée un statut de facture de test."""
        return InvoiceStatus.objects.create(
            name=name,
            label=name.title(),
            is_default=is_default,
            order=1
        )
    
    @staticmethod
    def create_payment_method(name='bank_transfer', is_default=True):
        """Crée un mode de paiement de test."""
        return PaymentMethod.objects.create(
            name=name,
            label='Virement bancaire',
            is_default=is_default,
            is_active=True
        )
    
    @staticmethod
    def create_quote(user, vat_rate, status, **kwargs):
        """Crée un devis de test."""
        defaults = {
            'quote_number': 'DEV-2024-001',
            'client_name': 'Client Test',
            'client_email': 'client@test.com',
            'subtotal': Decimal('1000.00'),
            'vat_amount': Decimal('200.00'),
            'total': Decimal('1200.00'),
            'valid_until': '2024-12-31'
        }
        defaults.update(kwargs)
        
        return Quote.objects.create(
            created_by=user,
            vat_rate=vat_rate,
            status=status,
            **defaults
        )
    
    @staticmethod
    def create_invoice(user, vat_rate, status, **kwargs):
        """Crée une facture de test."""
        defaults = {
            'invoice_number': 'FAC-2024-001',
            'client_name': 'Client Test',
            'client_email': 'client@test.com',
            'subtotal': Decimal('1000.00'),
            'vat_amount': Decimal('200.00'),
            'total': Decimal('1200.00'),
            'due_date': '2024-12-31'
        }
        defaults.update(kwargs)
        
        return Invoice.objects.create(
            created_by=user,
            vat_rate=vat_rate,
            status=status,
            **defaults
        )
    
    @staticmethod
    def create_quote_item(quote, **kwargs):
        """Crée un élément de devis de test."""
        defaults = {
            'name': 'Article Test',
            'description': 'Description de test',
            'quantity': Decimal('1.00'),
            'unit_price': Decimal('100.00'),
            'subtotal': Decimal('100.00'),
            'order': 1
        }
        defaults.update(kwargs)
        
        return QuoteItem.objects.create(
            quote=quote,
            **defaults
        )
    
    @staticmethod
    def create_invoice_item(invoice, **kwargs):
        """Crée un élément de facture de test."""
        defaults = {
            'name': 'Article Test',
            'description': 'Description de test',
            'quantity': Decimal('1.00'),
            'unit_price': Decimal('100.00'),
            'subtotal': Decimal('100.00'),
            'order': 1
        }
        defaults.update(kwargs)
        
        return InvoiceItem.objects.create(
            invoice=invoice,
            **defaults
        )
    
    @staticmethod
    def create_payment(invoice, payment_method, **kwargs):
        """Crée un paiement de test."""
        defaults = {
            'amount': Decimal('1200.00'),
            'payment_date': '2024-01-15',
            'reference': 'PAY-001'
        }
        defaults.update(kwargs)
        
        return Payment.objects.create(
            invoice=invoice,
            payment_method=payment_method,
            **defaults
        )


class DocumentTestCase(MultiTenantTestMixin, TestCase):
    """Classe de base pour les tests de modèles."""
    
    def setUp(self):
        super().setUp()
        # Créer les données de base
        self.user = DocumentTestFixtures.create_user()
        self.vat_rate = DocumentTestFixtures.create_vat_rate()
        self.quote_status = DocumentTestFixtures.create_quote_status()
        self.invoice_status = DocumentTestFixtures.create_invoice_status()
        self.payment_method = DocumentTestFixtures.create_payment_method()


class DocumentAPITestCase(MultiTenantTestMixin, APITestCase):
    """Classe de base pour les tests d'API."""
    
    def setUp(self):
        super().setUp()
        # Créer les données de base
        self.user = DocumentTestFixtures.create_user()
        self.vat_rate = DocumentTestFixtures.create_vat_rate()
        self.quote_status = DocumentTestFixtures.create_quote_status()
        self.invoice_status = DocumentTestFixtures.create_invoice_status()
        self.payment_method = DocumentTestFixtures.create_payment_method()
        
        # Configurer l'authentification
        self.client.force_authenticate(user=self.user)
        self.set_tenant_header()


class TestDataBuilder:
    """Builder pattern pour créer des données de test complexes."""
    
    def __init__(self):
        self.reset()
    
    def reset(self):
        """Remet à zéro le builder."""
        self._quote_data = {}
        self._invoice_data = {}
        self._items = []
        return self
    
    def with_quote_data(self, **kwargs):
        """Configure les données de devis."""
        self._quote_data.update(kwargs)
        return self
    
    def with_invoice_data(self, **kwargs):
        """Configure les données de facture."""
        self._invoice_data.update(kwargs)
        return self
    
    def with_item(self, **item_data):
        """Ajoute un élément."""
        self._items.append(item_data)
        return self
    
    def with_multiple_items(self, count=3):
        """Ajoute plusieurs éléments de test."""
        for i in range(count):
            self.with_item(
                name=f'Article {i+1}',
                quantity=Decimal('1.00'),
                unit_price=Decimal(f'{(i+1)*100}.00')
            )
        return self
    
    def build_quote(self, user, vat_rate, status):
        """Construit un devis avec ses éléments."""
        quote = DocumentTestFixtures.create_quote(
            user, vat_rate, status, **self._quote_data
        )
        
        for item_data in self._items:
            DocumentTestFixtures.create_quote_item(quote, **item_data)
        
        return quote
    
    def build_invoice(self, user, vat_rate, status):
        """Construit une facture avec ses éléments."""
        invoice = DocumentTestFixtures.create_invoice(
            user, vat_rate, status, **self._invoice_data
        )
        
        for item_data in self._items:
            DocumentTestFixtures.create_invoice_item(invoice, **item_data)
        
        return invoice


# Instances globales pour simplifier l'utilisation
data_builder = TestDataBuilder()
fixtures = DocumentTestFixtures() 