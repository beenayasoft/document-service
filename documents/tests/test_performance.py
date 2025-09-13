"""
Tests de performance pour le document-service.
"""
import time
from decimal import Decimal
from datetime import date, timedelta
from django.test import TestCase, override_settings
from django.core.cache import cache
from django.db import connection
from rest_framework.test import APITestCase
from documents.tests.fixtures import DocumentAPITestCase, fixtures, data_builder
from documents.models import Quote, Invoice, QuoteItem, InvoiceItem
from documents.services import CalculationService  # PDFService supprimé
# from documents.services import PDFService  # SUPPRIMÉ


@override_settings(DEBUG=False)  # Désactiver le debug pour des mesures précises
class PerformanceTestCase(DocumentAPITestCase):
    """Classe de base pour les tests de performance."""
    
    def setUp(self):
        super().setUp()
        cache.clear()
        
    def measure_time(self, func, *args, **kwargs):
        """Mesure le temps d'exécution d'une fonction."""
        start_time = time.time()
        result = func(*args, **kwargs)
        end_time = time.time()
        return result, end_time - start_time
    
    def measure_queries(self, func, *args, **kwargs):
        """Mesure le nombre de requêtes SQL."""
        initial_queries = len(connection.queries)
        result = func(*args, **kwargs)
        final_queries = len(connection.queries)
        return result, final_queries - initial_queries


class QuoteListPerformanceTest(PerformanceTestCase):
    """Tests de performance pour la liste des devis."""
    
    def test_list_performance_with_large_dataset(self):
        """Test performance de la liste avec beaucoup de données."""
        # Créer un grand nombre de devis
        quotes = []
        for i in range(1000):
            quote = fixtures.create_quote(
                self.user, self.vat_rate, self.quote_status,
                quote_number=f'PERF-{i:04d}',
                client_name=f'Client {i}',
                subtotal=Decimal(f'{i+1000}.00')
            )
            quotes.append(quote)
        
        # Test de performance de la liste
        url = '/api/quotes/'
        response, response_time = self.measure_time(
            self.client.get, url
        )
        
        # Vérifications
        self.assertEqual(response.status_code, 200)
        self.assertLess(response_time, 2.0)  # < 2 secondes
        self.assertIn('results', response.data)
        
        # Test avec pagination
        response, response_time = self.measure_time(
            self.client.get, url, {'page_size': 50}
        )
        
        self.assertEqual(response.status_code, 200)
        self.assertLess(response_time, 1.0)  # < 1 seconde avec pagination
        self.assertEqual(len(response.data['results']), 50)
    
    def test_filtering_performance(self):
        """Test performance du filtrage."""
        # Créer des devis avec différents statuts
        status_sent = fixtures.create_quote_status('sent', is_default=False)
        status_validated = fixtures.create_quote_status('validated', is_default=False)
        
        for i in range(500):
            status = [self.quote_status, status_sent, status_validated][i % 3]
            fixtures.create_quote(
                self.user, self.vat_rate, status,
                quote_number=f'FILTER-{i:03d}'
            )
        
        # Test filtrage par statut
        url = '/api/quotes/'
        response, response_time = self.measure_time(
            self.client.get, url, {'status': self.quote_status.id}
        )
        
        self.assertEqual(response.status_code, 200)
        self.assertLess(response_time, 1.5)  # < 1.5 secondes
        
        # Test recherche textuelle
        response, response_time = self.measure_time(
            self.client.get, url, {'search': 'FILTER-1'}
        )
        
        self.assertEqual(response.status_code, 200)
        self.assertLess(response_time, 1.0)  # < 1 seconde
    
    def test_stats_performance(self):
        """Test performance des statistiques."""
        # Créer des données variées
        for i in range(200):
            fixtures.create_quote(
                self.user, self.vat_rate, self.quote_status,
                subtotal=Decimal(f'{(i+1)*100}.00')
            )
        
        # Test performance des stats
        url = '/api/quotes/stats/'
        response, response_time = self.measure_time(self.client.get, url)
        
        self.assertEqual(response.status_code, 200)
        self.assertLess(response_time, 1.0)  # < 1 seconde
        self.assertIn('total_count', response.data)
        self.assertIn('total_amount', response.data)
        
        # Test avec cache
        response, response_time = self.measure_time(self.client.get, url)
        
        self.assertEqual(response.headers.get('X-Cache-Status'), 'HIT')
        self.assertLess(response_time, 0.1)  # < 0.1 seconde avec cache


class QuoteDetailPerformanceTest(PerformanceTestCase):
    """Tests de performance pour les détails de devis."""
    
    def test_detail_with_many_items(self):
        """Test performance avec beaucoup d'éléments."""
        quote = fixtures.create_quote(
            self.user, self.vat_rate, self.quote_status
        )
        
        # Créer une hiérarchie complexe
        for chapter_i in range(5):
            chapter = fixtures.create_quote_item(
                quote,
                name=f'Chapitre {chapter_i+1}',
                item_type='chapter'
            )
            
            for section_i in range(10):
                section = fixtures.create_quote_item(
                    quote,
                    name=f'Section {chapter_i+1}.{section_i+1}',
                    item_type='section',
                    parent=chapter
                )
                
                for item_i in range(20):
                    fixtures.create_quote_item(
                        quote,
                        name=f'Item {chapter_i+1}.{section_i+1}.{item_i+1}',
                        item_type='item',
                        parent=section,
                        quantity=Decimal('1.0'),
                        unit_price=Decimal(f'{item_i+1}.00')
                    )
        
        # Total : 5 + 50 + 1000 = 1055 éléments
        self.assertEqual(quote.items.count(), 1055)
        
        # Test performance du détail
        url = f'/api/quotes/{quote.id}/'
        response, response_time = self.measure_time(self.client.get, url)
        
        self.assertEqual(response.status_code, 200)
        self.assertLess(response_time, 3.0)  # < 3 secondes
        self.assertIn('items', response.data)
    
    def test_n_plus_one_queries_prevention(self):
        """Test prévention du problème N+1 queries."""
        quote = fixtures.create_quote(
            self.user, self.vat_rate, self.quote_status
        )
        
        # Créer 100 éléments
        for i in range(100):
            fixtures.create_quote_item(
                quote,
                name=f'Item {i+1}',
                quantity=Decimal('1.0'),
                unit_price=Decimal(f'{i+1}.00')
            )
        
        # Mesurer les requêtes
        url = f'/api/quotes/{quote.id}/'
        response, query_count = self.measure_queries(self.client.get, url)
        
        self.assertEqual(response.status_code, 200)
        # Doit utiliser select_related/prefetch_related pour éviter N+1
        self.assertLess(query_count, 10)  # < 10 requêtes même avec 100 éléments


class CalculationPerformanceTest(PerformanceTestCase):
    """Tests de performance des calculs."""
    
    def test_recalculation_performance(self):
        """Test performance du recalcul."""
        calculation_service = CalculationService()
        
        quote = fixtures.create_quote(
            self.user, self.vat_rate, self.quote_status
        )
        
        # Créer beaucoup d'éléments avec remises variées
        for i in range(500):
            fixtures.create_quote_item(
                quote,
                name=f'Item {i+1}',
                quantity=Decimal(f'{(i % 10) + 1}.0'),
                unit_price=Decimal(f'{(i % 100) + 50}.00'),
                discount_percentage=Decimal(f'{i % 20}.00')
            )
        
        # Test performance du recalcul
        result, calc_time = self.measure_time(
            calculation_service.recalculate_from_items, quote
        )
        
        self.assertLess(calc_time, 1.0)  # < 1 seconde
        self.assertIsNotNone(result['subtotal'])
        self.assertIsNotNone(result['total'])
    
    def test_bulk_calculations(self):
        """Test performance des calculs en lot."""
        calculation_service = CalculationService()
        
        # Créer plusieurs devis
        quotes = []
        for i in range(50):
            quote = fixtures.create_quote(
                self.user, self.vat_rate, self.quote_status
            )
            
            # Ajouter des éléments
            for j in range(20):
                fixtures.create_quote_item(
                    quote,
                    quantity=Decimal('1.0'),
                    unit_price=Decimal(f'{j+1}0.00')
                )
            
            quotes.append(quote)
        
        # Test recalcul en lot
        start_time = time.time()
        
        for quote in quotes:
            calculation_service.recalculate_from_items(quote)
        
        bulk_calc_time = time.time() - start_time
        
        self.assertLess(bulk_calc_time, 5.0)  # < 5 secondes pour 50 devis


# class PDFGenerationPerformanceTest(PerformanceTestCase):  # SUPPRIMÉ - Service PDF supprimé
#     """Tests de performance de génération PDF."""
#     
#     def test_pdf_generation_performance(self):
#         """Test performance de génération PDF."""
#         pdf_service = PDFService()
#         
#         quote = data_builder.reset()\
#             .with_quote_data(quote_number='PDF-PERF-001')\
#             .with_multiple_items(50)\
#             .build_quote(self.user, self.vat_rate, self.quote_status)
#         
#         # Test génération PDF
#         pdf_content, generation_time = self.measure_time(
#             pdf_service.generate_quote_pdf, quote
#         )
#         
#         self.assertIsInstance(pdf_content, bytes)
#         self.assertLess(generation_time, 5.0)  # < 5 secondes
#         self.assertTrue(len(pdf_content) > 1000)
    
#     def test_concurrent_pdf_generation(self):  # SUPPRIMÉ
#         """Test génération PDF concurrente."""
#         import threading
#         import concurrent.futures
#         
#         pdf_service = PDFService()
#         
#         # Créer plusieurs devis
#         quotes = []
#         for i in range(10):
#             quote = data_builder.reset()\
#                 .with_quote_data(quote_number=f'CONC-PDF-{i:02d}')\
#                 .with_multiple_items(20)\
#                 .build_quote(self.user, self.vat_rate, self.quote_status)
#             quotes.append(quote)
#         
#         # Génération concurrente
#         start_time = time.time()
#         
#         with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
#             futures = [
#                 executor.submit(pdf_service.generate_quote_pdf, quote)
#                 for quote in quotes
#             ]
#             
#             results = [future.result() for future in futures]
#         
#         concurrent_time = time.time() - start_time
#         
#         # Vérifications
#         self.assertEqual(len(results), 10)
#         self.assertLess(concurrent_time, 15.0)  # < 15 secondes pour 10 PDFs
#         
#         for result in results:
#             self.assertIsInstance(result, bytes)
#             self.assertTrue(len(result) > 1000)


class DatabasePerformanceTest(PerformanceTestCase):
    """Tests de performance de la base de données."""
    
    def test_bulk_insert_performance(self):
        """Test performance d'insertion en lot."""
        # Préparer les données
        quotes_data = []
        for i in range(100):
            quotes_data.append({
                'created_by': self.user,
                'vat_rate': self.vat_rate,
                'status': self.quote_status,
                'quote_number': f'BULK-{i:03d}',
                'client_name': f'Client {i}',
                'subtotal': Decimal(f'{i+1000}.00'),
                'vat_amount': Decimal(f'{(i+1000)*0.2}.00'),
                'total': Decimal(f'{(i+1000)*1.2}.00')
            })
        
        # Test insertion en lot
        start_time = time.time()
        
        quotes = [Quote(**data) for data in quotes_data]
        Quote.objects.bulk_create(quotes)
        
        bulk_insert_time = time.time() - start_time
        
        self.assertLess(bulk_insert_time, 2.0)  # < 2 secondes
        self.assertEqual(Quote.objects.count(), 100)
    
    def test_complex_query_performance(self):
        """Test performance de requêtes complexes."""
        # Créer des données avec relations
        for i in range(100):
            quote = fixtures.create_quote(
                self.user, self.vat_rate, self.quote_status,
                quote_number=f'COMPLEX-{i:03d}'
            )
            
            # Ajouter des éléments
            for j in range(10):
                fixtures.create_quote_item(quote)
        
        # Requête complexe avec jointures
        start_time = time.time()
        
        quotes = Quote.objects.select_related(
            'created_by', 'vat_rate', 'status'
        ).prefetch_related(
            'items'
        ).filter(
            status=self.quote_status,
            created_by=self.user
        ).order_by('-created_at')[:50]
        
        # Forcer l'évaluation de la QuerySet
        list(quotes)
        
        query_time = time.time() - start_time
        
        self.assertLess(query_time, 1.0)  # < 1 seconde


class CachePerformanceTest(PerformanceTestCase):
    """Tests de performance du cache."""
    
    def test_cache_vs_database_performance(self):
        """Test comparaison performance cache vs base de données."""
        # Créer des données
        for i in range(100):
            fixtures.create_quote(
                self.user, self.vat_rate, self.quote_status
            )
        
        url = '/api/quotes/stats/'
        
        # Premier appel (sans cache)
        cache.clear()
        response1, time_without_cache = self.measure_time(
            self.client.get, url
        )
        
        # Deuxième appel (avec cache)
        response2, time_with_cache = self.measure_time(
            self.client.get, url
        )
        
        # Vérifications
        self.assertEqual(response1.status_code, 200)
        self.assertEqual(response2.status_code, 200)
        self.assertEqual(response2.headers.get('X-Cache-Status'), 'HIT')
        
        # Le cache doit être significativement plus rapide
        improvement_ratio = time_without_cache / time_with_cache
        self.assertGreater(improvement_ratio, 5.0)  # Au moins 5x plus rapide
    
    def test_cache_memory_usage(self):
        """Test utilisation mémoire du cache."""
        import psutil
        import os
        
        process = psutil.Process(os.getpid())
        initial_memory = process.memory_info().rss
        
        # Créer beaucoup de données et les mettre en cache
        for i in range(500):
            fixtures.create_quote(
                self.user, self.vat_rate, self.quote_status
            )
        
        # Charger en cache
        for page in range(10):
            self.client.get('/api/quotes/', {'page': page + 1})
        
        final_memory = process.memory_info().rss
        memory_increase = final_memory - initial_memory
        
        # L'augmentation de mémoire doit rester raisonnable (< 100MB)
        self.assertLess(memory_increase, 100 * 1024 * 1024)


class LoadTestCase(PerformanceTestCase):
    """Tests de charge simulée."""
    
    def test_simulated_load(self):
        """Test charge simulée sur l'API."""
        import threading
        import random
        
        # Créer des données de base
        for i in range(50):
            fixtures.create_quote(
                self.user, self.vat_rate, self.quote_status
            )
        
        results = []
        errors = []
        
        def simulate_user_session():
            """Simule une session utilisateur."""
            try:
                # Consultation de la liste
                response = self.client.get('/api/quotes/')
                results.append(('list', response.status_code))
                
                # Consultation des stats
                response = self.client.get('/api/quotes/stats/')
                results.append(('stats', response.status_code))
                
                # Création d'un devis
                quote_data = {
                    'quote_number': f'LOAD-{random.randint(1000, 9999)}',
                    'client_name': 'Load Test Client',
                    'subtotal': '1000.00',
                    'vat_rate': self.vat_rate.id,
                    'status': self.quote_status.id
                }
                response = self.client.post('/api/quotes/', quote_data)
                results.append(('create', response.status_code))
                
            except Exception as e:
                errors.append(str(e))
        
        # Lancer 20 sessions simultanées
        threads = []
        start_time = time.time()
        
        for _ in range(20):
            thread = threading.Thread(target=simulate_user_session)
            threads.append(thread)
            thread.start()
        
        for thread in threads:
            thread.join()
        
        load_test_time = time.time() - start_time
        
        # Vérifications
        self.assertEqual(len(errors), 0, f'Erreurs: {errors}')
        self.assertLess(load_test_time, 10.0)  # < 10 secondes
        
        # Vérifier que la plupart des requêtes ont réussi
        successful_requests = sum(1 for _, status in results if status == 200)
        total_requests = len(results)
        success_rate = successful_requests / total_requests if total_requests > 0 else 0
        
        self.assertGreater(success_rate, 0.95)  # > 95% de succès 