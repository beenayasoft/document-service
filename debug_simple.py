#!/usr/bin/env python
"""
Script de diagnostic simple pour les devis
"""
import os
import sys
import django

# Configurer Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'document_service.settings')
django.setup()

from django.db import connection

def debug_simple():
    print("DIAGNOSTIC SIMPLE - DEVIS")
    print("=" * 30)
    
    # 1. Connexion DB
    print("\n1. BASE DE DONNEES")
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT current_database(), current_schema()")
            db_info = cursor.fetchone()
            print(f"Base: {db_info[0]}")
            print(f"Schema actuel: {db_info[1]}")
    except Exception as e:
        print(f"Erreur DB: {e}")
        return
    
    # 2. Schemas tenant
    print("\n2. SCHEMAS TENANT")
    try:
        with connection.cursor() as cursor:
            cursor.execute("""
                SELECT schema_name 
                FROM information_schema.schemata 
                WHERE schema_name LIKE 'tenant_%'
                ORDER BY schema_name
            """)
            schemas = cursor.fetchall()
            
            print(f"Schemas trouves: {len(schemas)}")
            for schema in schemas:
                print(f"  - {schema[0]}")
                
    except Exception as e:
        print(f"Erreur schemas: {e}")
        return
    
    # 3. Devis par schema
    print("\n3. DEVIS PAR SCHEMA")
    total_devis = 0
    
    for schema in schemas:
        schema_name = schema[0]
        try:
            with connection.cursor() as cursor:
                cursor.execute(f"SET search_path TO {schema_name}, public")
                cursor.execute("SELECT COUNT(*) FROM documents_quote")
                count = cursor.fetchone()[0]
                
                print(f"{schema_name}: {count} devis")
                total_devis += count
                
                if count > 0:
                    cursor.execute("""
                        SELECT number, client_name, status, created_at 
                        FROM documents_quote 
                        ORDER BY created_at DESC 
                        LIMIT 2
                    """)
                    devis = cursor.fetchall()
                    
                    for devis_info in devis:
                        print(f"    {devis_info[0]} - {devis_info[1]} - {devis_info[2]}")
                        
        except Exception as e:
            print(f"Erreur schema {schema_name}: {e}")
    
    # Reset schema
    with connection.cursor() as cursor:
        cursor.execute("SET search_path TO public")
    
    print(f"\nTOTAL: {total_devis} devis dans {len(schemas)} schemas")
    
    # 4. Recommandations
    if total_devis == 0:
        print("\nPROBLEME: Aucun devis trouve")
        print("- Verifiez les migrations")
        print("- Verifiez l'insertion des donnees")
    elif len(schemas) == 0:
        print("\nPROBLEME: Aucun schema tenant")
        print("- Le middleware ne peut pas fonctionner")
    else:
        print("\nDONNEES OK - Probleme probable:")
        print("- Header X-Tenant-ID manquant")
        print("- UUID tenant incorrect")
        print("- Configuration frontend")

if __name__ == "__main__":
    debug_simple()