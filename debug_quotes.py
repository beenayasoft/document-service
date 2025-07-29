#!/usr/bin/env python
"""
Script de diagnostic pour analyser les problèmes de récupération des devis
"""
import os
import sys
import django
from django.conf import settings

# Configurer Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'document_service.settings')
django.setup()

from django.db import connection
from documents.models import Quote
import uuid

def debug_quotes():
    """Diagnostic complet des devis en base"""
    
    print("DIAGNOSTIC DES DEVIS - DOCUMENT SERVICE")
    print("=" * 50)
    
    # 1. Vérifier la connexion DB
    print("\n1. CONNEXION BASE DE DONNEES")
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT current_database(), current_schema()")
            db_info = cursor.fetchone()
            print(f"[OK] Base: {db_info[0]}, Schema: {db_info[1]}")
    except Exception as e:
        print(f"[ERREUR] DB: {e}")
        return
    
    # 2. Lister tous les schémas tenant
    print("\n2. SCHEMAS TENANT DISPONIBLES")
    try:
        with connection.cursor() as cursor:
            cursor.execute("""
                SELECT schema_name 
                FROM information_schema.schemata 
                WHERE schema_name LIKE 'tenant_%'
                ORDER BY schema_name
            """)
            schemas = cursor.fetchall()
            
            if schemas:
                print(f"[OK] {len(schemas)} schemas tenant trouves:")
                for schema in schemas[:5]:  # Limiter à 5 pour l'affichage
                    print(f"   - {schema[0]}")
                if len(schemas) > 5:
                    print(f"   ... et {len(schemas) - 5} autres")
            else:
                print("[ERREUR] Aucun schema tenant trouve!")
                return
                
    except Exception as e:
        print(f"[ERREUR] Schemas: {e}")
        return
    
    # 3. Compter les devis dans chaque schéma
    print("\n3. DEVIS PAR SCHEMA")
    total_quotes = 0
    
    for schema in schemas:
        schema_name = schema[0]
        try:
            with connection.cursor() as cursor:
                cursor.execute(f"SET search_path TO {schema_name}, public")
                cursor.execute("SELECT COUNT(*) FROM documents_quote")
                count = cursor.fetchone()[0]
                
                if count > 0:
                    print(f"✅ {schema_name}: {count} devis")
                    total_quotes += count
                    
                    # Détails des devis dans ce schéma
                    cursor.execute("""
                        SELECT id, number, client_name, status, created_at 
                        FROM documents_quote 
                        ORDER BY created_at DESC 
                        LIMIT 3
                    """)
                    quotes_details = cursor.fetchall()
                    
                    for quote in quotes_details:
                        print(f"   📄 {quote[1]} - {quote[2]} - {quote[3]} - {quote[4]}")
                        
        except Exception as e:
            print(f"❌ Erreur schéma {schema_name}: {e}")
    
    # Remettre le schéma par défaut
    with connection.cursor() as cursor:
        cursor.execute("SET search_path TO public")
    
    print(f"\n📊 TOTAL: {total_quotes} devis trouvés dans {len(schemas)} schémas")
    
    # 4. Test avec le nouveau middleware (simulation)
    print("\n4️⃣ TEST NOUVEAU MIDDLEWARE")
    
    if schemas:
        # Prendre le premier schéma comme exemple
        test_schema = schemas[0][0]
        
        # Extraire l'UUID du nom de schéma
        if test_schema.startswith('tenant_'):
            tenant_uuid_part = test_schema.replace('tenant_', '').replace('_', '-')
            
            # Essayer de reconstituer l'UUID
            try:
                if len(tenant_uuid_part) == 32:  # UUID sans tirets
                    formatted_uuid = f"{tenant_uuid_part[:8]}-{tenant_uuid_part[8:12]}-{tenant_uuid_part[12:16]}-{tenant_uuid_part[16:20]}-{tenant_uuid_part[20:]}"
                else:
                    formatted_uuid = tenant_uuid_part
                
                # Vérifier que c'est un UUID valide
                uuid.UUID(formatted_uuid)
                
                print(f"✅ Schéma de test: {test_schema}")
                print(f"✅ UUID reconstruit: {formatted_uuid}")
                
                # Tester l'accès aux devis dans ce schéma
                with connection.cursor() as cursor:
                    cursor.execute(f"SET search_path TO {test_schema}, public")
                    cursor.execute("SELECT COUNT(*) FROM documents_quote")
                    count = cursor.fetchone()[0]
                    print(f"✅ Devis accessibles: {count}")
                    
            except ValueError as e:
                print(f"❌ UUID invalide: {tenant_uuid_part} - {e}")
            except Exception as e:
                print(f"❌ Erreur test: {e}")
    
    # 5. Recommandations
    print("\n5️⃣ RECOMMANDATIONS")
    
    if total_quotes == 0:
        print("❌ Aucun devis trouvé - Vérifiez les migrations et l'insertion de données")
    elif len(schemas) == 0:
        print("❌ Aucun schéma tenant - Le middleware tenant ne peut pas fonctionner")
    else:
        print("✅ Données présentes - Problème probablement au niveau:")
        print("   • Headers X-Tenant-ID manquants")
        print("   • UUID tenant incorrect")
        print("   • Configuration frontend")
        print("   • Middleware authentication")
    
    print("\n🔧 ÉTAPES SUIVANTES:")
    print("1. Vérifiez que le frontend envoie le header X-Tenant-ID")
    print("2. Testez avec curl: curl -H 'X-Tenant-ID: UUID' http://localhost:8004/api/quotes/")
    print("3. Vérifiez les logs en temps réel: tail -f logs/document.log")

if __name__ == "__main__":
    debug_quotes()