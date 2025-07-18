"""
Tests d'intégration multi-tenant et scénarios complexes pour le document-service.
"""
from decimal import Decimal
from datetime import date, timedelta
from django.test import TestCase, TransactionTestCase
from django.db import connection, transaction
from django.core.cache import cache
from rest_framework.test import APITestCase
from documents.tests.fixtures import DocumentAPITestCase, fixtures, data_builder
from documents.models import Quote, Invoice, QuoteItem, InvoiceItem, Payment
from documents.services import CalculationService, WorkflowService


class MultiTenantIntegrationTest(TransactionTestCase):
    """Tests d'intégration du système multi-tenant."""
    
    def setUp(self):
        self.tenant1_id = 'tenant_1'
        self.tenant2_id = 'tenant_2'
        
        # Créer les schémas de test
        self.create_tenant_schema(self.tenant1_id)
        self.create_tenant_schema(self.tenant2_id)
        
        # Créer les utilisateurs pour chaque tenant
        self.setup_tenant_data()
    
    def create_tenant_schema(self, tenant_id):
        """Crée un schéma de tenant."""
        with connection.cursor() as cursor:
            cursor.execute(f'CREATE SCHEMA IF NOT EXISTS "{tenant_id}"')
            cursor.execute(f'SET search_path TO "{tenant_id}", public')
    
    def setup_tenant_data(self):
        """Configure les données de base pour chaque tenant."""
        # Tenant 1
        with self.switch_tenant(self.tenant1_id):
            self.user1 = fixtures.create_user('user1', 'user1@tenant1.com')
            self.vat_rate1 = fixtures.create_vat_rate(20.0, 'TVA FR')
            self.quote_status1 = fixtures.create_quote_status('draft')
            self.invoice_status1 = fixtures.create_invoice_status('draft')
            self.payment_method1 = fixtures.create_payment_method('bank_transfer')
        
        # Tenant 2
        with self.switch_tenant(self.tenant2_id):
            self.user2 = fixtures.create_user('user2', 'user2@tenant2.com')
            self.vat_rate2 = fixtures.create_vat_rate(19.0, 'TVA DE')
            self.quote_status2 = fixtures.create_quote_status('draft')
            self.invoice_status2 = fixtures.create_invoice_status('draft')
            self.payment_method2 = fixtures.create_payment_method('credit_card')
    
    def switch_tenant(self, tenant_id):
        """Context manager pour changer de tenant."""
        return TenantContext(tenant_id)
    
    def tearDown(self):
        """Nettoie les schémas de test."""
        with connection.cursor() as cursor:
            cursor.execute(f'DROP SCHEMA IF EXISTS "{self.tenant1_id}" CASCADE')
            cursor.execute(f'DROP SCHEMA IF EXISTS "{self.tenant2_id}" CASCADE')
    
    def test_data_isolation_between_tenants(self):
        """Test isolation des données entre tenants."""
        # Créer des données dans le tenant 1
        with self.switch_tenant(self.tenant1_id):
            quote1 = fixtures.create_quote(
                self.user1, self.vat_rate1, self.quote_status1,
                quote_number='T1-DEV-001'
            )
            invoice1 = fixtures.create_invoice(
                self.user1, self.vat_rate1, self.invoice_status1,
                invoice_number='T1-FAC-001'
            )
            
            # Vérifier que les données existent
            self.assertEqual(Quote.objects.count(), 1)
            self.assertEqual(Invoice.objects.count(), 1)
        
        # Créer des données dans le tenant 2
        with self.switch_tenant(self.tenant2_id):
            quote2 = fixtures.create_quote(
                self.user2, self.vat_rate2, self.quote_status2,
                quote_number='T2-DEV-001'
            )
            
            # Vérifier l'isolation : pas de données du tenant 1
            self.assertEqual(Quote.objects.count(), 1)
            self.assertEqual(Invoice.objects.count(), 0)
            
            # Vérifier les bonnes données
            retrieved_quote = Quote.objects.first()
            self.assertEqual(retrieved_quote.quote_number, 'T2-DEV-001')
        
        # Retour au tenant 1 - les données doivent toujours exister
        with self.switch_tenant(self.tenant1_id):
            self.assertEqual(Quote.objects.count(), 1)
            self.assertEqual(Invoice.objects.count(), 1)
            
            retrieved_quote = Quote.objects.first()
            self.assertEqual(retrieved_quote.quote_number, 'T1-DEV-001')
    
    def test_concurrent_operations_different_tenants(self):
        """Test opérations simultanées sur différents tenants."""
        import threading
        import time
        
        results = {}
        errors = []
        
        def create_quotes_tenant1():
            try:
                with self.switch_tenant(self.tenant1_id):
                    for i in range(10):
                        fixtures.create_quote(
                            self.user1, self.vat_rate1, self.quote_status1,
                            quote_number=f'T1-CONC-{i:03d}'
                        )
                        time.sleep(0.01)  # Simuler du temps de traitement
                    results['tenant1'] = Quote.objects.count()
            except Exception as e:
                errors.append(f'Tenant1: {e}')
        
        def create_quotes_tenant2():
            try:
                with self.switch_tenant(self.tenant2_id):
                    for i in range(15):
                        fixtures.create_quote(
                            self.user2, self.vat_rate2, self.quote_status2,
                            quote_number=f'T2-CONC-{i:03d}'
                        )
                        time.sleep(0.01)
                    results['tenant2'] = Quote.objects.count()
            except Exception as e:
                errors.append(f'Tenant2: {e}')
        
        # Lancer les threads
        thread1 = threading.Thread(target=create_quotes_tenant1)
        thread2 = threading.Thread(target=create_quotes_tenant2)
        
        thread1.start()
        thread2.start()
        
        thread1.join()
        thread2.join()
        
        # Vérifier les résultats
        self.assertEqual(len(errors), 0, f'Erreurs: {errors}')
        self.assertEqual(results['tenant1'], 10)
        self.assertEqual(results['tenant2'], 15)
    
    def test_tenant_specific_configurations(self):
        """Test configurations spécifiques par tenant."""
        # Configuration différente par tenant
        with self.switch_tenant(self.tenant1_id):
            # Tenant 1 : TVA française 20%
            quote1 = fixtures.create_quote(
                self.user1, self.vat_rate1, self.quote_status1,
                subtotal=Decimal('1000.00')
            )
            quote1.recalculate_totals()
            
            expected_vat1 = Decimal('200.00')  # 20%
            self.assertEqual(quote1.vat_amount, expected_vat1)
        
        with self.switch_tenant(self.tenant2_id):
            # Tenant 2 : TVA allemande 19%
            quote2 = fixtures.create_quote(
                self.user2, self.vat_rate2, self.quote_status2,
                subtotal=Decimal('1000.00')
            )
            quote2.recalculate_totals()
            
            expected_vat2 = Decimal('190.00')  # 19%
            self.assertEqual(quote2.vat_amount, expected_vat2)
    
    def test_cross_tenant_reference_prevention(self):
        """Test prévention des références cross-tenant."""
        # Créer des données dans chaque tenant
        with self.switch_tenant(self.tenant1_id):
            quote1 = fixtures.create_quote(
                self.user1, self.vat_rate1, self.quote_status1
            )
            quote1_id = quote1.id
        
        # Tenter d'accéder aux données d'un autre tenant
        with self.switch_tenant(self.tenant2_id):
            # Cette requête ne doit pas retourner le devis du tenant 1
            quotes = Quote.objects.filter(id=quote1_id)
            self.assertEqual(quotes.count(), 0)
            
            # Tentative de création d'une référence cross-tenant
            # (devrait être impossible avec l'isolation des schémas)
            with self.assertRaises(Exception):
                # Tenter de créer un élément avec une référence invalide
                QuoteItem.objects.create(
                    quote_id=quote1_id,  # ID du tenant 1
                    name='Cross-tenant item',
                    quantity=Decimal('1.0'),
                    unit_price=Decimal('100.00'),
                    order=1
                )


class TenantContext:
    """Context manager pour changer de tenant."""
    
    def __init__(self, tenant_id):
        self.tenant_id = tenant_id
        self.original_search_path = None
    
    def __enter__(self):
        with connection.cursor() as cursor:
            cursor.execute('SHOW search_path')
            self.original_search_path = cursor.fetchone()[0]
            cursor.execute(f'SET search_path TO "{self.tenant_id}", public')
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        with connection.cursor() as cursor:
            cursor.execute(f'SET search_path TO {self.original_search_path}')


class ComplexBusinessScenarioTest(DocumentAPITestCase):
    """Tests de scénarios métier complexes."""
    
    def test_complete_sales_cycle(self):
        """Test cycle de vente complet."""
        # 1. Créer un devis complexe avec hiérarchie
        quote = fixtures.create_quote(
            self.user, self.vat_rate, self.quote_status,
            quote_number='CYCLE-001',
            client_name='Client Complet'
        )
        
        # Ajouter une structure hiérarchique
        chapter1 = fixtures.create_quote_item(
            quote, name='Chapitre 1: Infrastructure', item_type='chapter'
        )
        section1_1 = fixtures.create_quote_item(
            quote, name='Section 1.1: Serveurs', item_type='section', parent=chapter1
        )
        item1_1_1 = fixtures.create_quote_item(
            quote, name='Serveur principal', item_type='item', parent=section1_1,
            quantity=Decimal('2.0'), unit_price=Decimal('5000.00')
        )
        item1_1_2 = fixtures.create_quote_item(
            quote, name='Serveur backup', item_type='item', parent=section1_1,
            quantity=Decimal('1.0'), unit_price=Decimal('3000.00')
        )
        
        chapter2 = fixtures.create_quote_item(
            quote, name='Chapitre 2: Logiciels', item_type='chapter'
        )
        item2_1 = fixtures.create_quote_item(
            quote, name='Licences système', item_type='item', parent=chapter2,
            quantity=Decimal('5.0'), unit_price=Decimal('500.00')
        )
        
        # 2. Recalculer et valider
        quote.recalculate_from_items()
        
        # 3. Envoyer et valider le devis
        sent_status = fixtures.create_quote_status('sent', is_default=False)
        validated_status = fixtures.create_quote_status('validated', is_default=False)
        
        workflow_service = WorkflowService()
        workflow_service.transition_status(quote, sent_status, self.user)
        workflow_service.validate_quote(quote, self.user)
        
        # 4. Convertir en facture
        invoice = workflow_service.convert_quote_to_invoice(
            quote, 'CYCLE-FAC-001', self.user
        )
        
        # 5. Effectuer des paiements partiels
        payment1 = fixtures.create_payment(
            invoice, self.payment_method,
            amount=Decimal('5000.00'),
            reference='PAY-001'
        )
        payment2 = fixtures.create_payment(
            invoice, self.payment_method,
            amount=Decimal('10000.00'),
            reference='PAY-002'
        )
        
        # Vérifications finales
        self.assertEqual(invoice.items.count(), 5)  # Tous les éléments non-hiérarchiques
        self.assertEqual(quote.subtotal, Decimal('15500.00'))  # 2*5000 + 3000 + 5*500
        self.assertTrue(invoice.is_fully_paid())
        self.assertEqual(invoice.payments.count(), 2)
    
    def test_complex_discount_scenarios(self):
        """Test scénarios complexes de remises."""
        quote = fixtures.create_quote(
            self.user, self.vat_rate, self.quote_status
        )
        
        # Éléments avec remises différentes
        item1 = fixtures.create_quote_item(
            quote,
            name='Item sans remise',
            quantity=Decimal('1.0'),
            unit_price=Decimal('1000.00'),
            discount_percentage=Decimal('0.0')
        )
        
        item2 = fixtures.create_quote_item(
            quote,
            name='Item remise 10%',
            quantity=Decimal('2.0'),
            unit_price=Decimal('500.00'),
            discount_percentage=Decimal('10.0')
        )
        
        item3 = fixtures.create_quote_item(
            quote,
            name='Item remise fixe',
            quantity=Decimal('1.0'),
            unit_price=Decimal('800.00'),
            discount_amount=Decimal('50.00')
        )
        
        # Remise globale sur le devis
        quote.discount_percentage = Decimal('5.0')
        quote.save()
        
        # Recalculer
        calculation_service = CalculationService()
        totals = calculation_service.recalculate_from_items(quote)
        
        # Vérifications des calculs complexes
        expected_item1_total = Decimal('1000.00')  # Pas de remise
        expected_item2_total = Decimal('900.00')   # 2*500 - 10% = 900
        expected_item3_total = Decimal('750.00')   # 800 - 50 = 750
        expected_subtotal = expected_item1_total + expected_item2_total + expected_item3_total
        
        self.assertEqual(totals['subtotal'], expected_subtotal)
        
        # Avec remise globale de 5%
        expected_discount = expected_subtotal * Decimal('0.05')
        expected_final_subtotal = expected_subtotal - expected_discount
        
        self.assertEqual(totals['discount_amount'], expected_discount)
        self.assertEqual(totals['subtotal_after_discount'], expected_final_subtotal)
    
    def test_invoice_partial_payments_complex(self):
        """Test paiements partiels complexes."""
        invoice = fixtures.create_invoice(
            self.user, self.vat_rate, self.invoice_status,
            total=Decimal('10000.00'),
            due_date=date.today() + timedelta(days=30)
        )
        
        # Série de paiements partiels
        payments_data = [
            {'amount': Decimal('2000.00'), 'date': date.today() - timedelta(days=5)},
            {'amount': Decimal('3000.00'), 'date': date.today()},
            {'amount': Decimal('2500.00'), 'date': date.today() + timedelta(days=2)},
            {'amount': Decimal('2500.00'), 'date': date.today() + timedelta(days=5)},
        ]
        
        for i, payment_data in enumerate(payments_data):
            fixtures.create_payment(
                invoice, self.payment_method,
                amount=payment_data['amount'],
                payment_date=payment_data['date'],
                reference=f'PAY-{i+1:03d}'
            )
        
        # Vérifications
        self.assertEqual(invoice.get_total_paid(), Decimal('10000.00'))
        self.assertTrue(invoice.is_fully_paid())
        self.assertEqual(invoice.get_remaining_amount(), Decimal('0.00'))
        self.assertEqual(invoice.payments.count(), 4)
        
        # Test statut de paiement à différentes étapes
        invoice.payments.filter(reference='PAY-004').delete()
        invoice.refresh_from_db()
        
        self.assertEqual(invoice.get_total_paid(), Decimal('7500.00'))
        self.assertFalse(invoice.is_fully_paid())
        self.assertEqual(invoice.get_remaining_amount(), Decimal('2500.00'))
    
    def test_bulk_operations_performance(self):
        """Test performance des opérations en lot."""
        import time
        
        # Créer un grand nombre de devis
        quotes = []
        start_time = time.time()
        
        for i in range(50):
            quote = fixtures.create_quote(
                self.user, self.vat_rate, self.quote_status,
                quote_number=f'BULK-{i:03d}'
            )
            quotes.append(quote)
        
        creation_time = time.time() - start_time
        
        # Opération en lot : validation de tous les devis
        quote_ids = [str(q.id) for q in quotes]
        
        start_time = time.time()
        
        # Simuler une validation en lot via l'API
        url = '/api/quotes/bulk-validate/'
        response = self.client.post(url, {
            'ids': quote_ids[:25]  # Valider 25 devis
        }, format='json')
        
        bulk_operation_time = time.time() - start_time
        
        # Vérifications de performance
        self.assertLess(creation_time, 5.0)  # Création < 5 secondes
        self.assertLess(bulk_operation_time, 2.0)  # Opération en lot < 2 secondes
        
        # Vérifier que l'opération a fonctionné
        if response.status_code == 200:
            validated_count = Quote.objects.filter(
                id__in=[q.id for q in quotes[:25]],
                status__name='validated'
            ).count()
            self.assertGreater(validated_count, 0)


class CacheIntegrationTest(DocumentAPITestCase):
    """Tests d'intégration du système de cache."""
    
    def setUp(self):
        super().setUp()
        cache.clear()
    
    def test_cache_coherence_across_operations(self):
        """Test cohérence du cache lors d'opérations complexes."""
        # Créer des données
        quote1 = fixtures.create_quote(
            self.user, self.vat_rate, self.quote_status,
            quote_number='CACHE-001'
        )
        quote2 = fixtures.create_quote(
            self.user, self.vat_rate, self.quote_status,
            quote_number='CACHE-002'
        )
        
        # Charger en cache via l'API
        list_url = '/api/quotes/'
        stats_url = '/api/quotes/stats/'
        
        # Premier chargement - mise en cache
        response1 = self.client.get(list_url)
        self.assertEqual(response1.status_code, 200)
        
        response2 = self.client.get(stats_url)
        self.assertEqual(response2.status_code, 200)
        
        # Vérifier cache HIT
        response3 = self.client.get(list_url)
        self.assertEqual(response3.headers.get('X-Cache-Status'), 'HIT')
        
        # Modifier une donnée - doit invalider le cache
        detail_url = f'/api/quotes/{quote1.id}/'
        self.client.patch(detail_url, {'client_name': 'Modified Client'})
        
        # Cache doit être invalidé
        response4 = self.client.get(list_url)
        self.assertNotEqual(response4.headers.get('X-Cache-Status'), 'HIT')
        
        response5 = self.client.get(stats_url)
        self.assertNotEqual(response5.headers.get('X-Cache-Status'), 'HIT')
    
    def test_cache_tenant_isolation(self):
        """Test isolation du cache par tenant."""
        # Créer des données pour le tenant actuel
        fixtures.create_quote(self.user, self.vat_rate, self.quote_status)
        
        # Charger en cache
        response1 = self.client.get('/api/quotes/')
        self.assertEqual(response1.data['count'], 1)
        
        # Changer de tenant
        original_tenant = self.client.defaults.get('HTTP_X_TENANT_ID')
        self.client.defaults['HTTP_X_TENANT_ID'] = 'other_tenant'
        
        # Les données en cache ne doivent pas être partagées
        response2 = self.client.get('/api/quotes/')
        self.assertEqual(response2.data['count'], 0)
        
        # Remettre le tenant original
        self.client.defaults['HTTP_X_TENANT_ID'] = original_tenant
        
        # Cache du tenant original doit être intact
        response3 = self.client.get('/api/quotes/')
        self.assertEqual(response3.headers.get('X-Cache-Status'), 'HIT')
        self.assertEqual(response3.data['count'], 1)


class ErrorHandlingIntegrationTest(DocumentAPITestCase):
    """Tests de gestion d'erreurs dans des scénarios complexes."""
    
    def test_transaction_rollback_on_error(self):
        """Test rollback de transaction en cas d'erreur."""
        quote = fixtures.create_quote(
            self.user, self.vat_rate, self.quote_status
        )
        
        # Ajouter des éléments
        for i in range(3):
            fixtures.create_quote_item(quote, name=f'Item {i+1}')
        
        initial_count = QuoteItem.objects.count()
        
        # Opération qui doit échouer (numéro de facture dupliqué)
        fixtures.create_invoice(
            self.user, self.vat_rate, self.invoice_status,
            invoice_number='DUPLICATE-001'
        )
        
        # Tenter de convertir avec le même numéro
        workflow_service = WorkflowService()
        
        try:
            with transaction.atomic():
                workflow_service.convert_quote_to_invoice(
                    quote, 'DUPLICATE-001', self.user
                )
        except Exception:
            pass  # Erreur attendue
        
        # Vérifier que les données n'ont pas été corrompues
        self.assertEqual(QuoteItem.objects.count(), initial_count)
        quote.refresh_from_db()
        self.assertIsNone(quote.converted_at)
    
    def test_concurrent_modification_handling(self):
        """Test gestion des modifications concurrentes."""
        quote = fixtures.create_quote(
            self.user, self.vat_rate, self.quote_status,
            subtotal=Decimal('1000.00')
        )
        
        # Simuler deux modifications simultanées
        quote_1 = Quote.objects.get(id=quote.id)
        quote_2 = Quote.objects.get(id=quote.id)
        
        # Modification 1
        quote_1.client_name = 'Client Modified 1'
        quote_1.save()
        
        # Modification 2 (potentiel conflit)
        quote_2.client_name = 'Client Modified 2'
        quote_2.subtotal = Decimal('2000.00')
        quote_2.save()
        
        # Vérifier l'état final
        quote.refresh_from_db()
        # La dernière modification gagne (comportement par défaut de Django)
        self.assertEqual(quote.client_name, 'Client Modified 2')
        self.assertEqual(quote.subtotal, Decimal('2000.00')) 