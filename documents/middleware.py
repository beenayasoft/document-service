"""
Middleware pour la gestion automatique des schémas par tenant
"""
import logging
from django.db import connection
from django.http import JsonResponse
from django.utils.deprecation import MiddlewareMixin

logger = logging.getLogger(__name__)

class TenantSchemaMiddleware(MiddlewareMixin):
    """
    Middleware qui gère automatiquement la sélection du schéma basé sur le tenant_id
    """
    
    def process_request(self, request):
        """
        Sélectionne le bon schéma avant le traitement de la requête
        """
        
        # Extraire le tenant_id depuis les headers (envoyé par l'API Gateway)
        tenant_id = request.META.get('HTTP_X_TENANT_ID')
        
        if not tenant_id:
            # Pour les endpoints publics (health check), utiliser le schéma public
            if request.path in ['/health/', '/admin/', '/api/schema/', '/api/docs/', '/api/debug/']:
                self._set_schema('public')
                return None
            
            return JsonResponse({
                'error': 'Header X-Tenant-ID requis',
                'detail': 'Le service Document nécessite un tenant_id pour fonctionner'
            }, status=400)
        
        # Validation basique du format UUID
        try:
            import uuid
            uuid.UUID(tenant_id)
        except ValueError:
            return JsonResponse({
                'error': 'Format tenant_id invalide',
                'detail': 'Le tenant_id doit être un UUID valide'
            }, status=400)
        
        # Nettoyer le tenant_id pour le nom de schéma (enlever les tirets)
        schema_name = f"tenant_{tenant_id.replace('-', '_')}"
        
        # Vérifier si le schéma existe, sinon le créer
        if not self._schema_exists(schema_name):
            if not self._create_tenant_schema(schema_name, tenant_id):
                return JsonResponse({
                    'error': 'Impossible de créer le schéma tenant',
                    'detail': f'Erreur lors de la création du schéma pour le tenant {tenant_id}'
                }, status=500)
        
        # Sélectionner le schéma
        self._set_schema(schema_name)
        
        # Stocker le tenant_id dans la requête pour usage ultérieur
        request.tenant_id = tenant_id
        request.schema_name = schema_name
        
        logger.info(f"Schéma sélectionné: {schema_name} pour tenant {tenant_id}")
        
        return None
    
    def _set_schema(self, schema_name):
        """
        Configure PostgreSQL pour utiliser le schéma spécifié
        """
        with connection.cursor() as cursor:
            cursor.execute(f"SET search_path TO {schema_name}, public")
    
    def _schema_exists(self, schema_name):
        """
        Vérifie si un schéma existe dans la base de données
        """
        with connection.cursor() as cursor:
            cursor.execute("""
                SELECT 1 FROM information_schema.schemata 
                WHERE schema_name = %s
            """, [schema_name])
            return cursor.fetchone() is not None
    
    def _create_tenant_schema(self, schema_name, tenant_id):
        """
        Crée un nouveau schéma pour un tenant et y applique les migrations
        """
        try:
            with connection.cursor() as cursor:
                # Créer le schéma
                cursor.execute(f"CREATE SCHEMA IF NOT EXISTS {schema_name}")
                logger.info(f"Schéma {schema_name} créé")
                
                # Sélectionner le nouveau schéma
                cursor.execute(f"SET search_path TO {schema_name}, public")
                
                # Appliquer les migrations dans ce schéma
                self._run_migrations_for_schema(schema_name)
                
                logger.info(f"Migrations appliquées pour le schéma {schema_name}")
                return True
                
        except Exception as e:
            logger.error(f"Erreur lors de la création du schéma {schema_name}: {e}")
            return False
    
    def _run_migrations_for_schema(self, schema_name):
        """
        Applique les migrations Django dans le schéma spécifié
        """
        from django.db import transaction
        
        # Temporairement changer le schéma par défaut
        with connection.cursor() as cursor:
            cursor.execute(f"SET search_path TO {schema_name}, public")
            
            # Créer les tables Django core dans ce schéma
            with transaction.atomic():
                # Créer les tables de migration Django
                cursor.execute(f"""
                    CREATE TABLE IF NOT EXISTS {schema_name}.django_migrations (
                        id SERIAL PRIMARY KEY,
                        app VARCHAR(255) NOT NULL,
                        name VARCHAR(255) NOT NULL,
                        applied TIMESTAMP WITH TIME ZONE NOT NULL
                    )
                """)
                
                # Créer les tables de documents
                self._create_documents_tables(cursor, schema_name)
    
    def _create_documents_tables(self, cursor, schema_name):
        """
        Crée les tables de l'app documents dans le schéma spécifié
        """
        
        # Table Quote (Devis)
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
        
        # Index pour performance sur Quote
        cursor.execute(f"""
            CREATE INDEX IF NOT EXISTS idx_{schema_name}_quote_status 
            ON {schema_name}.documents_quote (status)
        """)
        cursor.execute(f"""
            CREATE INDEX IF NOT EXISTS idx_{schema_name}_quote_tier 
            ON {schema_name}.documents_quote (tier_id)
        """)
        cursor.execute(f"""
            CREATE INDEX IF NOT EXISTS idx_{schema_name}_quote_created 
            ON {schema_name}.documents_quote (created_at)
        """)
        
        # Table QuoteItem (Éléments de devis)
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
        
        # Table Invoice (Factures)
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
        
        # Index pour performance sur Invoice
        cursor.execute(f"""
            CREATE INDEX IF NOT EXISTS idx_{schema_name}_invoice_status 
            ON {schema_name}.documents_invoice (status)
        """)
        cursor.execute(f"""
            CREATE INDEX IF NOT EXISTS idx_{schema_name}_invoice_tier 
            ON {schema_name}.documents_invoice (tier_id)
        """)
        cursor.execute(f"""
            CREATE INDEX IF NOT EXISTS idx_{schema_name}_invoice_quote 
            ON {schema_name}.documents_invoice (quote_id)
        """)
        
        # Table InvoiceItem (Éléments de facture)
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
        
        # Table Payment (Paiements)
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


class TenantSchemaRoutingMiddleware(MiddlewareMixin):
    """
    Middleware de nettoyage qui remet le schéma par défaut après chaque requête
    """
    
    def process_response(self, request, response):
        """
        Remet le schéma par défaut après traitement de la requête
        """
        with connection.cursor() as cursor:
            cursor.execute("SET search_path TO public")
        return response 