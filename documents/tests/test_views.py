"""
Tests des ViewSets et API pour le document-service.
"""
from decimal import Decimal
from datetime import date, timedelta
from django.urls import reverse
from django.contrib.auth.models import User
from django.core.cache import cache
from rest_framework import status
from rest_framework.test import APITestCase
from documents.tests.fixtures import DocumentAPITestCase, fixtures, data_builder
from documents.models import Quote, Invoice, QuoteItem, InvoiceItem, Payment


class QuoteViewSetTest(DocumentAPITestCase):
    """Tests du ViewSet Quote."""
    
    def test_list_quotes(self):
        """Test listage des devis."""
        # Créer des devis de test
        quote1 = fixtures.create_quote(
            self.user, self.vat_rate, self.quote_status,
            quote_number='DEV-001'
        )
        quote2 = fixtures.create_quote(
            self.user, self.vat_rate, self.quote_status,
            quote_number='DEV-002'
        )
        
        url = reverse('quote-list')
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['count'], 2)
        self.assertEqual(len(response.data['results']), 2)
    
    def test_create_quote(self):
        """Test création d'un devis."""
        url = reverse('quote-list')
        data = {
            'quote_number': 'DEV-NEW-001',
            'client_name': 'Test Client',
            'client_email': 'test@client.com',
            'subtotal': '1000.00',
            'vat_rate': self.vat_rate.id,
            'status': self.quote_status.id,
            'valid_until': (date.today() + timedelta(days=30)).isoformat()
        }
        
        response = self.client.post(url, data, format='json')
        
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['quote_number'], 'DEV-NEW-001')
        self.assertEqual(response.data['client_name'], 'Test Client')
        
        # Vérifier que le devis a été créé en base
        quote = Quote.objects.get(quote_number='DEV-NEW-001')
        self.assertEqual(quote.created_by, self.user)
    
    def test_retrieve_quote(self):
        """Test récupération d'un devis."""
        quote = fixtures.create_quote(
            self.user, self.vat_rate, self.quote_status
        )
        
        url = reverse('quote-detail', kwargs={'pk': quote.id})
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['id'], str(quote.id))
        self.assertIn('items', response.data)
    
    def test_update_quote(self):
        """Test mise à jour d'un devis."""
        quote = fixtures.create_quote(
            self.user, self.vat_rate, self.quote_status,
            client_name='Old Client'
        )
        
        url = reverse('quote-detail', kwargs={'pk': quote.id})
        data = {
            'client_name': 'Updated Client',
            'subtotal': '1500.00'
        }
        
        response = self.client.patch(url, data, format='json')
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['client_name'], 'Updated Client')
        
        # Vérifier en base
        quote.refresh_from_db()
        self.assertEqual(quote.client_name, 'Updated Client')
    
    def test_delete_quote(self):
        """Test suppression d'un devis."""
        quote = fixtures.create_quote(
            self.user, self.vat_rate, self.quote_status
        )
        quote_id = quote.id
        
        url = reverse('quote-detail', kwargs={'pk': quote.id})
        response = self.client.delete(url)
        
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        
        # Vérifier que le devis n'existe plus
        self.assertFalse(Quote.objects.filter(id=quote_id).exists())
    
    def test_quote_actions(self):
        """Test actions spécifiques aux devis."""
        quote = fixtures.create_quote(
            self.user, self.vat_rate, self.quote_status
        )
        
        # Test action send
        url = reverse('quote-send', kwargs={'pk': quote.id})
        response = self.client.post(url)
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        # Test action validate
        url = reverse('quote-validate', kwargs={'pk': quote.id})
        response = self.client.post(url)
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        # Test convert to invoice
        url = reverse('quote-convert-to-invoice', kwargs={'pk': quote.id})
        response = self.client.post(url, {'invoice_number': 'FAC-001'}, format='json')
        
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertIn('invoice_id', response.data)
    
    def test_quote_stats(self):
        """Test endpoint des statistiques de devis."""
        # Créer des devis de test
        fixtures.create_quote(self.user, self.vat_rate, self.quote_status)
        fixtures.create_quote(self.user, self.vat_rate, self.quote_status)
        
        url = reverse('quote-stats')
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('total_count', response.data)
        self.assertIn('total_amount', response.data)
        self.assertIn('by_status', response.data)
        self.assertEqual(response.data['total_count'], 2)
    
    def test_quote_filtering(self):
        """Test filtrage des devis."""
        # Créer des devis avec différents statuts
        status1 = fixtures.create_quote_status('draft')
        status2 = fixtures.create_quote_status('sent', is_default=False)
        
        quote1 = fixtures.create_quote(self.user, self.vat_rate, status1)
        quote2 = fixtures.create_quote(self.user, self.vat_rate, status2)
        
        # Filtrer par statut
        url = reverse('quote-list')
        response = self.client.get(url, {'status': status1.id})
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['count'], 1)
        self.assertEqual(response.data['results'][0]['id'], str(quote1.id))
    
    def test_quote_search(self):
        """Test recherche dans les devis."""
        quote = fixtures.create_quote(
            self.user, self.vat_rate, self.quote_status,
            client_name='ACME Corporation'
        )
        
        url = reverse('quote-list')
        response = self.client.get(url, {'search': 'ACME'})
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['count'], 1)
        self.assertEqual(response.data['results'][0]['id'], str(quote.id))


class InvoiceViewSetTest(DocumentAPITestCase):
    """Tests du ViewSet Invoice."""
    
    def test_list_invoices(self):
        """Test listage des factures."""
        invoice1 = fixtures.create_invoice(
            self.user, self.vat_rate, self.invoice_status
        )
        invoice2 = fixtures.create_invoice(
            self.user, self.vat_rate, self.invoice_status
        )
        
        url = reverse('invoice-list')
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['count'], 2)
    
    def test_create_invoice(self):
        """Test création d'une facture."""
        url = reverse('invoice-list')
        data = {
            'invoice_number': 'FAC-NEW-001',
            'client_name': 'Test Client',
            'client_email': 'test@client.com',
            'subtotal': '1500.00',
            'vat_rate': self.vat_rate.id,
            'status': self.invoice_status.id,
            'due_date': (date.today() + timedelta(days=30)).isoformat()
        }
        
        response = self.client.post(url, data, format='json')
        
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['invoice_number'], 'FAC-NEW-001')
    
    def test_invoice_payment_actions(self):
        """Test actions de paiement des factures."""
        invoice = fixtures.create_invoice(
            self.user, self.vat_rate, self.invoice_status,
            total=Decimal('1000.00')
        )
        
        # Test record payment
        url = reverse('invoice-record-payment', kwargs={'pk': invoice.id})
        data = {
            'amount': '500.00',
            'payment_method': self.payment_method.id,
            'payment_date': date.today().isoformat(),
            'reference': 'PAY-001'
        }
        
        response = self.client.post(url, data, format='json')
        
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertIn('payment_id', response.data)
        
        # Vérifier que le paiement a été créé
        payment = Payment.objects.get(id=response.data['payment_id'])
        self.assertEqual(payment.amount, Decimal('500.00'))
        self.assertEqual(payment.invoice, invoice)
    
    def test_invoice_overdue_filtering(self):
        """Test filtrage des factures en retard."""
        # Créer une facture en retard
        past_date = date.today() - timedelta(days=30)
        overdue_invoice = fixtures.create_invoice(
            self.user, self.vat_rate, self.invoice_status,
            due_date=past_date
        )
        
        # Créer une facture normale
        future_date = date.today() + timedelta(days=30)
        normal_invoice = fixtures.create_invoice(
            self.user, self.vat_rate, self.invoice_status,
            due_date=future_date
        )
        
        url = reverse('invoice-list')
        response = self.client.get(url, {'overdue': 'true'})
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['count'], 1)
        self.assertEqual(response.data['results'][0]['id'], str(overdue_invoice.id))
    
    def test_invoice_stats(self):
        """Test endpoint des statistiques de factures."""
        # Créer des factures de test
        fixtures.create_invoice(
            self.user, self.vat_rate, self.invoice_status,
            total=Decimal('1000.00')
        )
        fixtures.create_invoice(
            self.user, self.vat_rate, self.invoice_status,
            total=Decimal('2000.00')
        )
        
        url = reverse('invoice-stats')
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('total_count', response.data)
        self.assertIn('total_amount', response.data)
        self.assertIn('paid_amount', response.data)
        self.assertIn('overdue_count', response.data)


class QuoteItemViewSetTest(DocumentAPITestCase):
    """Tests du ViewSet QuoteItem."""
    
    def test_list_quote_items(self):
        """Test listage des éléments de devis."""
        quote = fixtures.create_quote(
            self.user, self.vat_rate, self.quote_status
        )
        item1 = fixtures.create_quote_item(quote, name='Item 1')
        item2 = fixtures.create_quote_item(quote, name='Item 2')
        
        url = reverse('quoteitem-list')
        response = self.client.get(url, {'quote': quote.id})
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['count'], 2)
    
    def test_create_quote_item(self):
        """Test création d'un élément de devis."""
        quote = fixtures.create_quote(
            self.user, self.vat_rate, self.quote_status
        )
        
        url = reverse('quoteitem-list')
        data = {
            'quote': quote.id,
            'name': 'New Item',
            'description': 'New item description',
            'quantity': '2.0',
            'unit_price': '250.00',
            'order': 1
        }
        
        response = self.client.post(url, data, format='json')
        
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['name'], 'New Item')
        self.assertEqual(float(response.data['quantity']), 2.0)
    
    def test_bulk_operations_quote_items(self):
        """Test opérations en lot sur les éléments."""
        quote = fixtures.create_quote(
            self.user, self.vat_rate, self.quote_status
        )
        item1 = fixtures.create_quote_item(quote)
        item2 = fixtures.create_quote_item(quote)
        
        url = reverse('quoteitem-bulk-delete')
        data = {
            'ids': [str(item1.id), str(item2.id)]
        }
        
        response = self.client.post(url, data, format='json')
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['deleted_count'], 2)


class PaymentViewSetTest(DocumentAPITestCase):
    """Tests du ViewSet Payment."""
    
    def test_list_payments(self):
        """Test listage des paiements."""
        invoice = fixtures.create_invoice(
            self.user, self.vat_rate, self.invoice_status
        )
        payment1 = fixtures.create_payment(invoice, self.payment_method)
        payment2 = fixtures.create_payment(invoice, self.payment_method)
        
        url = reverse('payment-list')
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['count'], 2)
    
    def test_create_payment(self):
        """Test création d'un paiement."""
        invoice = fixtures.create_invoice(
            self.user, self.vat_rate, self.invoice_status,
            total=Decimal('1000.00')
        )
        
        url = reverse('payment-list')
        data = {
            'invoice': invoice.id,
            'payment_method': self.payment_method.id,
            'amount': '750.00',
            'payment_date': date.today().isoformat(),
            'reference': 'TEST-PAY-001'
        }
        
        response = self.client.post(url, data, format='json')
        
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(float(response.data['amount']), 750.00)


class CacheTest(DocumentAPITestCase):
    """Tests du système de cache Redis."""
    
    def setUp(self):
        super().setUp()
        cache.clear()  # Nettoyer le cache avant chaque test
    
    def test_quote_list_caching(self):
        """Test mise en cache de la liste des devis."""
        fixtures.create_quote(self.user, self.vat_rate, self.quote_status)
        
        url = reverse('quote-list')
        
        # Premier appel - doit mettre en cache
        response1 = self.client.get(url)
        self.assertEqual(response1.status_code, status.HTTP_200_OK)
        self.assertNotIn('X-Cache-Status', response1.headers)
        
        # Deuxième appel - doit utiliser le cache
        response2 = self.client.get(url)
        self.assertEqual(response2.status_code, status.HTTP_200_OK)
        self.assertEqual(response2.headers.get('X-Cache-Status'), 'HIT')
    
    def test_cache_invalidation(self):
        """Test invalidation du cache lors de modifications."""
        quote = fixtures.create_quote(self.user, self.vat_rate, self.quote_status)
        
        # Mettre en cache
        url = reverse('quote-list')
        self.client.get(url)
        
        # Modifier un devis - doit invalider le cache
        quote_url = reverse('quote-detail', kwargs={'pk': quote.id})
        self.client.patch(quote_url, {'client_name': 'Modified'}, format='json')
        
        # Nouvel appel - cache invalidé
        response = self.client.get(url)
        self.assertNotIn('X-Cache-Status', response.headers)
    
    def test_stats_caching(self):
        """Test mise en cache des statistiques."""
        fixtures.create_quote(self.user, self.vat_rate, self.quote_status)
        
        url = reverse('quote-stats')
        
        # Premier appel
        response1 = self.client.get(url)
        self.assertEqual(response1.status_code, status.HTTP_200_OK)
        
        # Deuxième appel - utilise le cache
        response2 = self.client.get(url)
        self.assertEqual(response2.headers.get('X-Cache-Status'), 'HIT')


class PermissionTest(DocumentAPITestCase):
    """Tests des permissions et authentification."""
    
    def test_unauthenticated_access(self):
        """Test accès non authentifié."""
        self.client.logout()
        
        url = reverse('quote-list')
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
    
    def test_user_isolation(self):
        """Test isolation des données entre utilisateurs."""
        # Créer un autre utilisateur
        other_user = fixtures.create_user('otheruser', 'other@test.com')
        
        # Créer un devis pour l'utilisateur principal
        quote1 = fixtures.create_quote(self.user, self.vat_rate, self.quote_status)
        
        # Créer un devis pour l'autre utilisateur
        quote2 = fixtures.create_quote(other_user, self.vat_rate, self.quote_status)
        
        # L'utilisateur principal ne doit voir que ses devis
        url = reverse('quote-list')
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['count'], 1)
        self.assertEqual(response.data['results'][0]['id'], str(quote1.id))


class MultiTenantTest(DocumentAPITestCase):
    """Tests du système multi-tenant."""
    
    def test_tenant_isolation(self):
        """Test isolation des données par tenant."""
        # Créer des données pour le tenant actuel
        quote1 = fixtures.create_quote(self.user, self.vat_rate, self.quote_status)
        
        # Changer de tenant
        self.client.defaults['HTTP_X_TENANT_ID'] = 'other_tenant'
        
        # Les données du premier tenant ne doivent pas être visibles
        url = reverse('quote-list')
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['count'], 0)
    
    def test_missing_tenant_header(self):
        """Test comportement sans header tenant."""
        # Supprimer le header tenant
        if 'HTTP_X_TENANT_ID' in self.client.defaults:
            del self.client.defaults['HTTP_X_TENANT_ID']
        
        url = reverse('quote-list')
        response = self.client.get(url)
        
        # Doit retourner une erreur ou utiliser un tenant par défaut
        self.assertIn(response.status_code, [
            status.HTTP_400_BAD_REQUEST,
            status.HTTP_403_FORBIDDEN,
            status.HTTP_200_OK
        ])


class ExportTest(DocumentAPITestCase):
    """Tests des fonctionnalités d'export."""
    
    def test_export_quotes_csv(self):
        """Test export des devis en CSV."""
        fixtures.create_quote(self.user, self.vat_rate, self.quote_status)
        fixtures.create_quote(self.user, self.vat_rate, self.quote_status)
        
        url = reverse('quote-export')
        response = self.client.get(url, {'format': 'csv'})
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response['Content-Type'], 'text/csv')
        self.assertIn('attachment', response['Content-Disposition'])
    
    def test_export_quotes_excel(self):
        """Test export des devis en Excel."""
        fixtures.create_quote(self.user, self.vat_rate, self.quote_status)
        
        url = reverse('quote-export')
        response = self.client.get(url, {'format': 'excel'})
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('excel', response['Content-Type'])
    
    def test_generate_pdf(self):
        """Test génération de PDF."""
        quote = fixtures.create_quote(self.user, self.vat_rate, self.quote_status)
        
        url = reverse('quote-pdf', kwargs={'pk': quote.id})
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response['Content-Type'], 'application/pdf')


class PerformanceTest(DocumentAPITestCase):
    """Tests de performance."""
    
    def test_large_dataset_performance(self):
        """Test performance avec un grand jeu de données."""
        # Créer 100 devis
        for i in range(100):
            fixtures.create_quote(
                self.user, self.vat_rate, self.quote_status,
                quote_number=f'DEV-PERF-{i:03d}'
            )
        
        # Test de performance de la liste
        import time
        start_time = time.time()
        
        url = reverse('quote-list')
        response = self.client.get(url)
        
        end_time = time.time()
        response_time = end_time - start_time
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertLess(response_time, 2.0)  # Moins de 2 secondes
        self.assertEqual(response.data['count'], 100)
    
    def test_pagination_performance(self):
        """Test performance de la pagination."""
        # Créer 50 devis
        for i in range(50):
            fixtures.create_quote(self.user, self.vat_rate, self.quote_status)
        
        url = reverse('quote-list')
        response = self.client.get(url, {'page_size': 10})
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['results']), 10)
        self.assertIn('next', response.data)
        self.assertIn('previous', response.data) 