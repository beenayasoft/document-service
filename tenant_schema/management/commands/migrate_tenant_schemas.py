"""
Commande Django pour appliquer les migrations manquantes aux schémas tenant existants - Document Service
"""

import logging
from django.core.management.base import BaseCommand
from django.db import connection
from django.utils import timezone

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Applique les migrations manquantes aux schémas tenant existants (Document Service)'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Affiche les actions sans les exécuter',
        )
        parser.add_argument(
            '--tenant-id',
            type=str,
            help='Appliquer les migrations à un tenant spécifique seulement',
        )

    def handle(self, *args, **options):
        self.dry_run = options['dry_run']
        self.specific_tenant = options['tenant_id']
        
        if self.dry_run:
            self.stdout.write(self.style.WARNING('Mode DRY-RUN activé - aucune modification ne sera effectuée'))
        
        # Obtenir la liste des schémas tenant
        tenant_schemas = self._get_tenant_schemas()
        
        if not tenant_schemas:
            self.stdout.write(self.style.WARNING('Aucun schéma tenant trouvé'))
            return
        
        self.stdout.write(f'Trouvé {len(tenant_schemas)} schéma(s) tenant à traiter')
        
        # Traiter chaque schéma tenant
        for schema_name in tenant_schemas:
            if self.specific_tenant:
                # Vérifier si ce schéma correspond au tenant spécifié
                tenant_id = schema_name.replace('tenant_', '').replace('_', '-')
                if tenant_id != self.specific_tenant:
                    continue
            
            try:
                self._migrate_tenant_schema(schema_name)
            except Exception as e:
                self.stdout.write(
                    self.style.ERROR(f'Erreur lors de la migration du schéma {schema_name}: {e}')
                )
                continue
        
        self.stdout.write(self.style.SUCCESS('✅ Migration des schémas tenant terminée (Document Service)'))

    def _get_tenant_schemas(self):
        """Récupère la liste des schémas tenant existants"""
        with connection.cursor() as cursor:
            cursor.execute("""
                SELECT schema_name 
                FROM information_schema.schemata 
                WHERE schema_name LIKE 'tenant_%'
                ORDER BY schema_name
            """)
            return [row[0] for row in cursor.fetchall()]

    def _migrate_tenant_schema(self, schema_name):
        """Applique les migrations manquantes à un schéma tenant"""
        self.stdout.write(f'🔄 Traitement du schéma: {schema_name}')
        
        with connection.cursor() as cursor:
            # Basculer vers le schéma tenant
            cursor.execute(f"SET search_path TO {schema_name}, public")
            
            # Vérifier quelles tables manquent
            missing_tables = self._check_missing_tables(cursor, schema_name)
            
            if not missing_tables:
                self.stdout.write(f'  ✅ Toutes les tables sont déjà présentes dans {schema_name}')
                return
            
            self.stdout.write(f'  📋 Tables manquantes: {", ".join(missing_tables)}')
            
            if not self.dry_run:
                # Créer les tables manquantes
                for table_name in missing_tables:
                    self._create_missing_table(cursor, schema_name, table_name)
                    self.stdout.write(f'  ✅ Table {table_name} créée')
            
            # Enregistrer les migrations comme appliquées
            if not self.dry_run:
                self._mark_migrations_applied(cursor, schema_name)

    def _check_missing_tables(self, cursor, schema_name):
        """Vérifie quelles tables sont manquantes dans le schéma"""
        # Tables attendues pour l'app documents
        expected_tables = {
            'documents_quote',
            'documents_quoteitem', 
            'documents_invoice',
            'documents_invoiceitem',
            'documents_payment',
        }
        
        # Obtenir les tables existantes
        cursor.execute(f"""
            SELECT table_name 
            FROM information_schema.tables 
            WHERE table_schema = %s
        """, [schema_name])
        
        existing_tables = {row[0] for row in cursor.fetchall()}
        
        # Retourner les tables manquantes
        return expected_tables - existing_tables

    def _create_missing_table(self, cursor, schema_name, table_name):
        """Crée une table manquante dans le schéma"""
        
        if table_name == 'documents_quote':
            self._create_quote_table(cursor, schema_name)
        elif table_name == 'documents_quoteitem':
            self._create_quoteitem_table(cursor, schema_name)
        elif table_name == 'documents_invoice':
            self._create_invoice_table(cursor, schema_name)
        elif table_name == 'documents_invoiceitem':
            self._create_invoiceitem_table(cursor, schema_name)
        elif table_name == 'documents_payment':
            self._create_payment_table(cursor, schema_name)
        else:
            self.stdout.write(
                self.style.WARNING(f'  ⚠️  Table {table_name} inconnue - création ignorée')
            )

    def _create_quote_table(self, cursor, schema_name):
        """Crée la table des devis dans le schéma"""
        cursor.execute(f"""
            CREATE TABLE IF NOT EXISTS {schema_name}.documents_quote (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                number VARCHAR(50) UNIQUE NOT NULL,
                status VARCHAR(20) NOT NULL DEFAULT 'draft',
                tier_id VARCHAR(255) NOT NULL,
                opportunity_id VARCHAR(255),
                client_name VARCHAR(255) NOT NULL,
                client_address TEXT,
                project_name VARCHAR(255),
                project_address TEXT,
                issue_date DATE NOT NULL DEFAULT CURRENT_DATE,
                expiry_date DATE,
                validity_period INTEGER NOT NULL DEFAULT 30,
                notes TEXT,
                terms_and_conditions TEXT,
                total_ht DECIMAL(12,2) NOT NULL DEFAULT 0,
                total_vat DECIMAL(12,2) NOT NULL DEFAULT 0,
                total_ttc DECIMAL(12,2) NOT NULL DEFAULT 0,
                created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
                created_by VARCHAR(255),
                updated_by VARCHAR(255)
            )
        """)
        
        # Index pour performance
        indexes = [
            f"CREATE INDEX IF NOT EXISTS idx_{schema_name}_quote_status ON {schema_name}.documents_quote (status)",
            f"CREATE INDEX IF NOT EXISTS idx_{schema_name}_quote_tier ON {schema_name}.documents_quote (tier_id)",
            f"CREATE INDEX IF NOT EXISTS idx_{schema_name}_quote_created ON {schema_name}.documents_quote (created_at)",
        ]
        
        for index_sql in indexes:
            cursor.execute(index_sql)

    def _create_quoteitem_table(self, cursor, schema_name):
        """Crée la table des éléments de devis dans le schéma"""
        cursor.execute(f"""
            CREATE TABLE IF NOT EXISTS {schema_name}.documents_quoteitem (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                quote_id UUID NOT NULL REFERENCES {schema_name}.documents_quote(id) ON DELETE CASCADE,
                type VARCHAR(20) NOT NULL DEFAULT 'product',
                parent_id UUID REFERENCES {schema_name}.documents_quoteitem(id) ON DELETE CASCADE,
                position INTEGER NOT NULL DEFAULT 0,
                reference VARCHAR(50),
                designation VARCHAR(255) NOT NULL,
                description TEXT,
                unit VARCHAR(20),
                quantity DECIMAL(10,2) NOT NULL DEFAULT 1,
                unit_price DECIMAL(10,2) NOT NULL DEFAULT 0,
                discount DECIMAL(5,2) NOT NULL DEFAULT 0,
                vat_rate VARCHAR(10) NOT NULL DEFAULT '20',
                margin DECIMAL(5,2) NOT NULL DEFAULT 0,
                total_ht DECIMAL(12,2) NOT NULL DEFAULT 0,
                total_ttc DECIMAL(12,2) NOT NULL DEFAULT 0,
                work_id VARCHAR(50),
                created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
            )
        """)

    def _create_invoice_table(self, cursor, schema_name):
        """Crée la table des factures dans le schéma"""
        cursor.execute(f"""
            CREATE TABLE IF NOT EXISTS {schema_name}.documents_invoice (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                number VARCHAR(50) NOT NULL DEFAULT 'Brouillon',
                status VARCHAR(30) NOT NULL DEFAULT 'draft',
                is_credit_note BOOLEAN NOT NULL DEFAULT false,
                tier_id VARCHAR(255) NOT NULL,
                client_name VARCHAR(255) NOT NULL,
                client_address TEXT,
                project_name VARCHAR(255),
                project_address TEXT,
                project_reference VARCHAR(100),
                issue_date DATE NOT NULL DEFAULT CURRENT_DATE,
                due_date DATE,
                payment_terms INTEGER NOT NULL DEFAULT 30,
                notes TEXT,
                terms_and_conditions TEXT,
                total_ht DECIMAL(12,2) NOT NULL DEFAULT 0,
                total_vat DECIMAL(12,2) NOT NULL DEFAULT 0,
                total_ttc DECIMAL(12,2) NOT NULL DEFAULT 0,
                paid_amount DECIMAL(12,2) NOT NULL DEFAULT 0,
                remaining_amount DECIMAL(12,2) NOT NULL DEFAULT 0,
                quote_id UUID REFERENCES {schema_name}.documents_quote(id) ON DELETE SET NULL,
                quote_number VARCHAR(50),
                credit_note_id UUID REFERENCES {schema_name}.documents_invoice(id) ON DELETE SET NULL,
                original_invoice_id UUID REFERENCES {schema_name}.documents_invoice(id) ON DELETE SET NULL,
                created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
                created_by VARCHAR(255),
                updated_by VARCHAR(255)
            )
        """)
        
        # Index pour performance
        indexes = [
            f"CREATE INDEX IF NOT EXISTS idx_{schema_name}_invoice_status ON {schema_name}.documents_invoice (status)",
            f"CREATE INDEX IF NOT EXISTS idx_{schema_name}_invoice_tier ON {schema_name}.documents_invoice (tier_id)",
            f"CREATE INDEX IF NOT EXISTS idx_{schema_name}_invoice_quote ON {schema_name}.documents_invoice (quote_id)",
        ]
        
        for index_sql in indexes:
            cursor.execute(index_sql)

    def _create_invoiceitem_table(self, cursor, schema_name):
        """Crée la table des éléments de facture dans le schéma"""
        cursor.execute(f"""
            CREATE TABLE IF NOT EXISTS {schema_name}.documents_invoiceitem (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                invoice_id UUID NOT NULL REFERENCES {schema_name}.documents_invoice(id) ON DELETE CASCADE,
                type VARCHAR(20) NOT NULL DEFAULT 'product',
                parent_id UUID REFERENCES {schema_name}.documents_invoiceitem(id) ON DELETE CASCADE,
                position INTEGER NOT NULL DEFAULT 0,
                reference VARCHAR(50),
                designation VARCHAR(255) NOT NULL,
                description TEXT,
                unit VARCHAR(20),
                quantity DECIMAL(10,2) NOT NULL DEFAULT 1,
                unit_price DECIMAL(10,2) NOT NULL DEFAULT 0,
                discount DECIMAL(5,2) NOT NULL DEFAULT 0,
                vat_rate VARCHAR(10) NOT NULL DEFAULT '20',
                total_ht DECIMAL(12,2) NOT NULL DEFAULT 0,
                total_ttc DECIMAL(12,2) NOT NULL DEFAULT 0,
                work_id VARCHAR(50)
            )
        """)

    def _create_payment_table(self, cursor, schema_name):
        """Crée la table des paiements dans le schéma"""
        cursor.execute(f"""
            CREATE TABLE IF NOT EXISTS {schema_name}.documents_payment (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                invoice_id UUID NOT NULL REFERENCES {schema_name}.documents_invoice(id) ON DELETE CASCADE,
                date DATE NOT NULL DEFAULT CURRENT_DATE,
                amount DECIMAL(12,2) NOT NULL,
                method VARCHAR(20) NOT NULL DEFAULT 'bank_transfer',
                reference VARCHAR(100),
                notes TEXT,
                created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
            )
        """)

    def _mark_migrations_applied(self, cursor, schema_name):
        """Marque les migrations comme appliquées dans le schéma"""
        
        # Assurer que la table django_migrations existe
        cursor.execute(f"""
            CREATE TABLE IF NOT EXISTS {schema_name}.django_migrations (
                id SERIAL PRIMARY KEY,
                app VARCHAR(255) NOT NULL,
                name VARCHAR(255) NOT NULL,
                applied TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
            )
        """)
        
        # Marquer les migrations documents comme appliquées
        cursor.execute(f"""
            INSERT INTO {schema_name}.django_migrations (app, name, applied)
            SELECT 'documents', '0001_initial', NOW()
            WHERE NOT EXISTS (
                SELECT 1 FROM {schema_name}.django_migrations 
                WHERE app = 'documents' AND name = '0001_initial'
            )
        """)
        
        cursor.execute(f"""
            INSERT INTO {schema_name}.django_migrations (app, name, applied)
            SELECT 'documents', '0002_remove_invoice_documents_i_status_c3dfed_idx_and_more', NOW()
            WHERE NOT EXISTS (
                SELECT 1 FROM {schema_name}.django_migrations 
                WHERE app = 'documents' AND name = '0002_remove_invoice_documents_i_status_c3dfed_idx_and_more'
            )
        """)
        
        logger.info(f"Migrations marquées comme appliquées dans le schéma {schema_name}")