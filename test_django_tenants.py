#!/usr/bin/env python
"""
Test django-tenants configuration - Document Service
Vérifie si les 3 devis peuvent être récupérés avec la nouvelle configuration
"""
import os
import sys
import django
from pathlib import Path

# Ajouter le projet au path
sys.path.append(str(Path(__file__).parent))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'document_service.settings')

django.setup()

from django.db import connection
from tenant_schema.models import Client
from documents.models import Quote

def test_django_tenants_setup():
    """Test si django-tenants fonctionne correctement"""
    print("=== Test Django-Tenants Configuration ===")
    
    # Test 1: Vérifier que les tenants sont configurés
    print("\n1. Vérification des tenants configurés:")
    tenants = Client.objects.all()
    for tenant in tenants:
        print(f"   - Tenant: {tenant.name} (UUID: {tenant.tenant_uuid})")
        print(f"     Schema: {tenant.schema_name}")
    
    if not tenants:
        print("   Aucun tenant trouvé!")
        return
    
    # Test 2: Test avec le tenant spécifique des 3 devis
    target_tenant_uuid = "31f96c39-bd7f-453e-a7f1-88495e70272b"
    print(f"\n2. Test avec le tenant cible: {target_tenant_uuid}")
    
    target_tenant = tenants.filter(tenant_uuid=target_tenant_uuid).first()
    if not target_tenant:
        print(f"   Tenant {target_tenant_uuid} non trouvé dans les tenants locaux!")
        print("   Tenants disponibles:")
        for t in tenants:
            print(f"     - {t.tenant_uuid}")
        return
    
    print(f"   Tenant trouvé: {target_tenant.name} (schema: {target_tenant.schema_name})")
    
    # Test 3: Utiliser django-tenants correctement
    print("\n3. Test django-tenants avec connection.set_tenant():")
    try:
        # DJANGO-TENANTS CORRECT: Utiliser connection.set_tenant()
        connection.set_tenant(target_tenant)
        print(f"   Schema activé: {target_tenant.schema_name}")
        
        # Vérifier les quotes
        quotes = Quote.objects.all()
        print(f"   Nombre de devis trouvés: {quotes.count()}")
        
        for quote in quotes:
            print(f"     - Devis #{quote.quote_number}: {quote.client_name}")
            print(f"       Créé le: {quote.created_at}")
            print(f"       Total: {quote.total_amount} €")
        
        # Réinitialiser le schéma
        connection.set_schema_to_public()
        print("   Schema réinitialisé à public")
        
    except Exception as e:
        print(f"   Erreur lors du test django-tenants: {str(e)}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_django_tenants_setup()