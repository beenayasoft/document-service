#!/usr/bin/env python
"""
Test direct du schéma tenant
"""
import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'document_service.settings')
django.setup()

from django.db import connection
from documents.models import Quote

def test_schema():
    print("TEST DIRECT SCHEMA TENANT")
    print("=" * 30)
    
    # UUID du tenant avec les devis
    tenant_uuid = "31f96c39-bd7f-453e-a7f1-88495e70272b"
    schema_name = f"tenant_{tenant_uuid.replace('-', '_')}"
    
    print(f"Tenant UUID: {tenant_uuid}")
    print(f"Schema name: {schema_name}")
    
    # 1. Test manuel avec SQL
    print("\n1. TEST SQL DIRECT")
    try:
        with connection.cursor() as cursor:
            cursor.execute(f"SET search_path TO {schema_name}, public")
            cursor.execute("SELECT id, number, client_name, status FROM documents_quote")
            results = cursor.fetchall()
            
            print(f"SQL direct: {len(results)} devis")
            for row in results:
                print(f"  - ID: {row[0]}")
                print(f"    Number: {row[1]}")
                print(f"    Client: {row[2]}")
                print(f"    Status: {row[3]}")
                
    except Exception as e:
        print(f"Erreur SQL: {e}")
    
    # 2. Test avec ORM Django
    print("\n2. TEST ORM DJANGO")
    try:
        # Simuler le middleware - configurer le schéma
        with connection.cursor() as cursor:
            cursor.execute(f"SET search_path TO {schema_name}, public")
        
        # Maintenant tester l'ORM
        quotes = Quote.objects.all()
        print(f"ORM Django: {quotes.count()} devis")
        
        for quote in quotes:
            print(f"  - ID: {quote.id}")
            print(f"    Number: {quote.number}")
            print(f"    Client: {quote.client_name}")
            print(f"    Status: {quote.status}")
            
    except Exception as e:
        print(f"Erreur ORM: {e}")
    
    # 3. Test du ViewSet (simulation)
    print("\n3. TEST SIMULATION VIEWSET")
    try:
        from documents.views import QuoteViewSet
        from django.test import RequestFactory
        
        # Créer une requête simulée
        factory = RequestFactory()
        request = factory.get('/api/quotes/')
        request.tenant_id = tenant_uuid
        request.schema_name = schema_name
        
        # Simuler le middleware - configurer le schéma
        with connection.cursor() as cursor:
            cursor.execute(f"SET search_path TO {schema_name}, public")
        
        # Tester le ViewSet
        viewset = QuoteViewSet()
        viewset.request = request
        queryset = viewset.get_queryset()
        
        print(f"ViewSet queryset: {queryset.count()} devis")
        
        # Test de la méthode list optimisée
        from documents.utils_optimized import OptimizedDocumentUtils
        optimized_queryset = OptimizedDocumentUtils.optimize_queryset_for_list(queryset)
        
        print(f"Queryset optimisé: {optimized_queryset.count()} devis")
        
    except Exception as e:
        print(f"Erreur ViewSet: {e}")
    
    # Reset schema
    with connection.cursor() as cursor:
        cursor.execute("SET search_path TO public")

if __name__ == "__main__":
    test_schema()