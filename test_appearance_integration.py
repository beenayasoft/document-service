#!/usr/bin/env python3
"""
Script de test pour vérifier l'intégration des paramètres d'apparence des documents
"""
import os
import sys
import django
import requests
import json
import uuid
from django.conf import settings

# Configuration de Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'document_service.settings')
django.setup()

from documents.models import Quote, QuoteItem
from documents.services.tenant_appearance_service import tenant_appearance_service
from documents.services.pdf_service import DocumentPDFService
from decimal import Decimal


def test_appearance_service():
    """
    Test du service d'apparence tenant
    """
    print("🧪 Test du service d'apparence tenant...")
    
    # Test avec un tenant fictif
    test_tenant_id = "12345678-1234-5678-9012-123456789012"
    
    try:
        # Test de récupération des paramètres par défaut
        print("   ├─ Test des paramètres par défaut...")
        default_settings = tenant_appearance_service._get_default_appearance_settings()
        print(f"   ├─ Paramètres par défaut récupérés: {len(default_settings)} clés")
        
        # Vérifier quelques clés importantes
        required_keys = ['primary_color', 'font_family', 'show_logo', 'show_client_address']
        missing_keys = [key for key in required_keys if key not in default_settings]
        if missing_keys:
            print(f"   ├─ ⚠️  Clés manquantes: {missing_keys}")
        else:
            print("   ├─ ✅ Toutes les clés requises sont présentes")
        
        # Test de conversion pour PDF
        print("   ├─ Test de conversion pour PDF...")
        pdf_settings = tenant_appearance_service.convert_to_pdf_appearance(default_settings)
        print(f"   ├─ Paramètres PDF générés: {len(pdf_settings)} clés")
        
        # Test avec un tenant inexistant (doit retourner les paramètres par défaut)
        print("   ├─ Test avec tenant inexistant...")
        appearance_data = tenant_appearance_service.get_document_appearance("non-existent-tenant")
        print(f"   └─ ✅ Paramètres récupérés pour tenant inexistant: {len(appearance_data)} clés")
        
    except Exception as e:
        print(f"   └─ ❌ Erreur dans le test d'apparence: {str(e)}")
        return False
    
    return True


def create_test_quote():
    """
    Crée un devis de test
    """
    print("📝 Création d'un devis de test...")
    
    try:
        # Créer un devis
        quote = Quote.objects.create(
            number="TEST-2025-001",
            client_name="Client Test",
            client_address="123 Rue de Test\n12345 Ville Test",
            project_name="Projet Test",
            project_address="456 Avenue du Projet\n67890 Chantier",
            issue_date="2025-01-15",
            expiry_date="2025-02-15",
            notes="Ceci est un devis de test pour l'intégration d'apparence.",
            terms_and_conditions="Conditions de test - Acompte 30%, solde à la fin.",
            total_ht=Decimal('1000.00'),
            total_vat=Decimal('200.00'),
            total_ttc=Decimal('1200.00')
        )
        
        # Ajouter quelques éléments
        QuoteItem.objects.create(
            quote=quote,
            type='chapter',
            position=1,
            designation='Chapitre Test',
            quantity=1,
            unit_price=Decimal('0.00'),
            vat_rate=Decimal('20.00'),
            total_ht=Decimal('0.00'),
            total_ttc=Decimal('0.00')
        )
        
        QuoteItem.objects.create(
            quote=quote,
            type='work',
            position=1,
            designation='Travail de test',
            description='Description détaillée du travail de test',
            unit='forfait',
            quantity=1,
            unit_price=Decimal('1000.00'),
            vat_rate=Decimal('20.00'),
            total_ht=Decimal('1000.00'),
            total_ttc=Decimal('1200.00')
        )
        
        print(f"   └─ ✅ Devis créé: {quote.number} (ID: {quote.id})")
        return quote
        
    except Exception as e:
        print(f"   └─ ❌ Erreur lors de la création du devis: {str(e)}")
        return None


def test_pdf_generation(quote, tenant_id="12345678-1234-5678-9012-123456789012"):
    """
    Test de génération PDF avec paramètres d'apparence
    """
    print("📄 Test de génération PDF...")
    
    try:
        # Créer le générateur PDF
        pdf_generator = DocumentPDFService(
            document=quote,
            document_type='quote',
            options={
                'show_vat': True,
                'include_details': True,
            },
            tenant_id=tenant_id
        )
        
        print(f"   ├─ Générateur créé pour tenant: {tenant_id}")
        print(f"   ├─ Paramètres d'apparence chargés: {len(pdf_generator.appearance_settings)} clés")
        print(f"   ├─ Couleur primaire: {pdf_generator.appearance_settings.get('primary_color', 'N/A')}")
        print(f"   ├─ Police: {pdf_generator.appearance_settings.get('font_family', 'N/A')}")
        print(f"   ├─ Taille police: {pdf_generator.appearance_settings.get('font_size', 'N/A')}")
        
        # Générer le PDF
        print("   ├─ Génération du PDF en cours...")
        pdf_buffer = pdf_generator.generate_pdf()
        
        if pdf_buffer and len(pdf_buffer.getvalue()) > 0:
            pdf_size = len(pdf_buffer.getvalue())
            print(f"   └─ ✅ PDF généré avec succès ({pdf_size} bytes)")
            
            # Sauvegarder le PDF de test
            test_pdf_path = "test_quote_with_appearance.pdf"
            with open(test_pdf_path, 'wb') as f:
                f.write(pdf_buffer.getvalue())
            print(f"   └─ 💾 PDF sauvegardé: {test_pdf_path}")
            
            return True
        else:
            print("   └─ ❌ PDF vide généré")
            return False
            
    except Exception as e:
        print(f"   └─ ❌ Erreur lors de la génération PDF: {str(e)}")
        import traceback
        traceback.print_exc()
        return False


def test_api_integration():
    """
    Test de l'intégration API (si les services sont en marche)
    """
    print("🌐 Test de l'intégration API...")
    
    # URLs de test
    tenant_service_url = "http://localhost:8002/api/tenants/document-appearance/"
    document_service_url = "http://localhost:8003"
    
    test_tenant_id = "12345678-1234-5678-9012-123456789012"
    
    try:
        # Test du tenant-service
        print("   ├─ Test du tenant-service...")
        headers = {'X-Tenant-ID': test_tenant_id}
        
        response = requests.get(tenant_service_url, headers=headers, timeout=5)
        if response.status_code in [200, 404]:  # 404 est OK (tenant pas encore configuré)
            print(f"   ├─ ✅ Tenant-service accessible (Status: {response.status_code})")
        else:
            print(f"   ├─ ⚠️  Tenant-service status inattendu: {response.status_code}")
        
        print("   └─ ✅ Tests API terminés")
        return True
        
    except requests.exceptions.RequestException as e:
        print(f"   └─ ⚠️  Services non accessibles (normal si pas démarrés): {str(e)}")
        return False


def cleanup_test_data():
    """
    Nettoie les données de test
    """
    print("🧹 Nettoyage des données de test...")
    
    try:
        # Supprimer les devis de test
        deleted_count = Quote.objects.filter(number__startswith="TEST-").delete()[0]
        print(f"   └─ ✅ {deleted_count} devis de test supprimés")
        
        # Supprimer le fichier PDF de test
        test_pdf_path = "test_quote_with_appearance.pdf"
        if os.path.exists(test_pdf_path):
            os.remove(test_pdf_path)
            print(f"   └─ ✅ Fichier PDF de test supprimé")
        
    except Exception as e:
        print(f"   └─ ⚠️  Erreur lors du nettoyage: {str(e)}")


def main():
    """
    Fonction principale de test
    """
    print("🚀 Test d'intégration des paramètres d'apparence des documents")
    print("=" * 70)
    
    success_count = 0
    total_tests = 4
    
    # Test 1: Service d'apparence
    if test_appearance_service():
        success_count += 1
    
    # Test 2: Création de devis de test
    test_quote = create_test_quote()
    if test_quote:
        success_count += 1
        
        # Test 3: Génération PDF
        if test_pdf_generation(test_quote):
            success_count += 1
    else:
        print("⏭️  Génération PDF ignorée (pas de devis de test)")
    
    # Test 4: Intégration API
    if test_api_integration():
        success_count += 1
    
    # Nettoyage
    cleanup_test_data()
    
    # Résultats
    print("=" * 70)
    print(f"📊 Résultats: {success_count}/{total_tests} tests réussis")
    
    if success_count == total_tests:
        print("🎉 Tous les tests sont passés! L'intégration est fonctionnelle.")
    elif success_count >= total_tests - 1:
        print("✅ L'intégration est largement fonctionnelle.")
    else:
        print("⚠️  Plusieurs tests ont échoué, vérification nécessaire.")
    
    return success_count == total_tests


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)