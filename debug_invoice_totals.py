#!/usr/bin/env python
"""
Script pour déboguer les totaux des factures
"""
import os
import sys
import django

# Ajouter le chemin du projet Django
sys.path.append('/services/document-service')

# Configurer Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'document_service.settings')
django.setup()

from documents.models import Invoice, InvoiceItem
from decimal import Decimal

def debug_invoice_totals():
    """Débogue les totaux des factures"""
    print("=== DEBUG TOTAUX DES FACTURES ===")
    
    # Récupérer toutes les factures
    invoices = Invoice.objects.all()
    print(f"Nombre de factures: {invoices.count()}")
    
    for invoice in invoices[:5]:  # Limiter à 5 pour le debug
        print(f"\n--- Facture {invoice.number} ---")
        print(f"ID: {invoice.id}")
        print(f"Total HT: {invoice.total_ht}")
        print(f"Total TVA: {invoice.total_vat}")
        print(f"Total TTC: {invoice.total_ttc}")
        
        # Vérifier les items
        items = InvoiceItem.objects.filter(invoice=invoice)
        print(f"Nombre d'items: {items.count()}")
        
        # Calculer les totaux manuellement
        calculated_ht = Decimal('0')
        calculated_vat = Decimal('0')
        
        for item in items:
            if item.type not in ["chapter", "section"]:
                print(f"  Item: {item.designation}")
                print(f"    Total HT: {item.total_ht}")
                print(f"    Total TTC: {item.total_ttc}")
                print(f"    Taux TVA: {item.vat_rate}")
                
                calculated_ht += item.total_ht or Decimal('0')
                
                # Calculer TVA
                try:
                    vat_rate = Decimal(item.vat_rate) / Decimal('100')
                    item_vat = item.total_ht * vat_rate
                    calculated_vat += item_vat
                except:
                    print(f"    ERREUR: Impossible de calculer la TVA")
        
        calculated_ttc = calculated_ht + calculated_vat
        
        print(f"Totaux calculés:")
        print(f"  HT calculé: {calculated_ht}")
        print(f"  TVA calculée: {calculated_vat}")
        print(f"  TTC calculé: {calculated_ttc}")
        
        # Vérifier si il y a des différences
        if invoice.total_ht != calculated_ht:
            print(f"  ⚠️  DIFFÉRENCE HT: DB={invoice.total_ht}, Calculé={calculated_ht}")
        if invoice.total_ttc != calculated_ttc:
            print(f"  ⚠️  DIFFÉRENCE TTC: DB={invoice.total_ttc}, Calculé={calculated_ttc}")

if __name__ == "__main__":
    debug_invoice_totals()