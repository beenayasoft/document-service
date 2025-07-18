#!/usr/bin/env python
"""
Script d'initialisation des données de base pour le document-service.

Ce script crée :
- Les taux de TVA standard
- Les statuts de devis et factures
- Les méthodes de paiement par défaut
"""

import os
import sys
from pathlib import Path
from decimal import Decimal

# Ajouter le répertoire du projet au Python path
project_dir = Path(__file__).parent
sys.path.insert(0, str(project_dir))

# Configuration Django AVANT tous les imports Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'document_service.settings')

import django
django.setup()

# Maintenant on peut importer les modèles Django
from documents.models import VATRate, QuoteStatus, InvoiceStatus, PaymentMethod


def create_vat_rates():
    """Crée les taux de TVA standard."""
    print("📊 Création des taux de TVA...")
    
    vat_rates = [
        {'name': 'TVA Standard', 'rate': Decimal('20.00'), 'is_active': True},
        {'name': 'TVA Réduite', 'rate': Decimal('10.00'), 'is_active': True},
        {'name': 'TVA Super Réduite', 'rate': Decimal('5.50'), 'is_active': True},
        {'name': 'TVA Zéro', 'rate': Decimal('0.00'), 'is_active': True},
    ]
    
    for vat_data in vat_rates:
        vat_rate, created = VATRate.objects.get_or_create(
            name=vat_data['name'],
            defaults=vat_data
        )
        if created:
            print(f"  ✓ {vat_rate.name} ({vat_rate.rate}%)")
        else:
            print(f"  → {vat_rate.name} (existe déjà)")


def create_quote_statuses():
    """Crée les statuts de devis."""
    print("\n📝 Création des statuts de devis...")
    
    quote_statuses = [
        {'name': 'draft', 'label': 'Brouillon', 'is_default': True, 'can_be_edited': True, 'order': 1},
        {'name': 'sent', 'label': 'Envoyé', 'is_default': False, 'can_be_edited': False, 'order': 2},
        {'name': 'validated', 'label': 'Validé', 'is_default': False, 'can_be_edited': False, 'order': 3},
        {'name': 'accepted', 'label': 'Accepté', 'is_default': False, 'can_be_edited': False, 'order': 4},
        {'name': 'rejected', 'label': 'Refusé', 'is_default': False, 'can_be_edited': False, 'order': 5},
        {'name': 'expired', 'label': 'Expiré', 'is_default': False, 'can_be_edited': False, 'order': 6},
    ]
    
    for status_data in quote_statuses:
        status, created = QuoteStatus.objects.get_or_create(
            name=status_data['name'],
            defaults=status_data
        )
        if created:
            print(f"  ✓ {status.label} ({status.name})")
        else:
            print(f"  → {status.label} (existe déjà)")


def create_invoice_statuses():
    """Crée les statuts de factures."""
    print("\n🧾 Création des statuts de factures...")
    
    invoice_statuses = [
        {'name': 'draft', 'label': 'Brouillon', 'is_default': True, 'can_be_edited': True, 'order': 1},
        {'name': 'sent', 'label': 'Envoyée', 'is_default': False, 'can_be_edited': False, 'order': 2},
        {'name': 'paid', 'label': 'Payée', 'is_default': False, 'can_be_edited': False, 'order': 3},
        {'name': 'partially_paid', 'label': 'Partiellement payée', 'is_default': False, 'can_be_edited': False, 'order': 4},
        {'name': 'overdue', 'label': 'En retard', 'is_default': False, 'can_be_edited': False, 'order': 5},
        {'name': 'cancelled', 'label': 'Annulée', 'is_default': False, 'can_be_edited': False, 'order': 6},
    ]
    
    for status_data in invoice_statuses:
        status, created = InvoiceStatus.objects.get_or_create(
            name=status_data['name'],
            defaults=status_data
        )
        if created:
            print(f"  ✓ {status.label} ({status.name})")
        else:
            print(f"  → {status.label} (existe déjà)")


def create_payment_methods():
    """Crée les méthodes de paiement."""
    print("\n💳 Création des méthodes de paiement...")
    
    payment_methods = [
        {'name': 'bank_transfer', 'label': 'Virement bancaire', 'is_default': True, 'is_active': True},
        {'name': 'check', 'label': 'Chèque', 'is_default': False, 'is_active': True},
        {'name': 'cash', 'label': 'Espèces', 'is_default': False, 'is_active': True},
        {'name': 'credit_card', 'label': 'Carte bancaire', 'is_default': False, 'is_active': True},
        {'name': 'direct_debit', 'label': 'Prélèvement automatique', 'is_default': False, 'is_active': True},
    ]
    
    for method_data in payment_methods:
        method, created = PaymentMethod.objects.get_or_create(
            name=method_data['name'],
            defaults=method_data
        )
        if created:
            print(f"  ✓ {method.label} ({method.name})")
        else:
            print(f"  → {method.label} (existe déjà)")


def main():
    """Point d'entrée principal."""
    print("🚀 Initialisation des données de base du Document Service")
    print("=" * 60)
    
    try:
        # Vérifier la connexion à la base de données
        from django.db import connection
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
        print("✓ Connexion à la base de données réussie")
        
        # Vérifier que les modèles sont bien chargés
        print(f"✓ Modèles Django chargés: VATRate = {VATRate}")
        
        # Créer les données de base
        create_vat_rates()
        create_quote_statuses()
        create_invoice_statuses()
        create_payment_methods()
        
        print("\n" + "=" * 60)
        print("✅ Initialisation terminée avec succès!")
        print("\n📋 Résumé :")
        print(f"  • {VATRate.objects.count()} taux de TVA")
        print(f"  • {QuoteStatus.objects.count()} statuts de devis")
        print(f"  • {InvoiceStatus.objects.count()} statuts de factures")
        print(f"  • {PaymentMethod.objects.count()} méthodes de paiement")
        
        print("\n🎯 Le service est prêt à être utilisé!")
        
    except Exception as e:
        print(f"\n❌ Erreur lors de l'initialisation: {e}")
        import traceback
        traceback.print_exc()
        return 1
    
    return 0


if __name__ == '__main__':
    sys.exit(main()) 