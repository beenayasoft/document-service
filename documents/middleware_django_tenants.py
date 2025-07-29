"""
Middleware pour la gestion des tenants via headers HTTP - Document Service
Basé sur le middleware fonctionnel du library-service
Compatible avec django-tenants et API Gateway
"""
import uuid
import logging
import requests
from django.conf import settings
from django.core.cache import cache
from django.http import JsonResponse
from django_tenants.utils import get_tenant_model
from tenant_schema.models import Client

logger = logging.getLogger('documents')

class HeaderTenantMiddleware:
    """
    Middleware pour la gestion des tenants via headers HTTP.
    
    Compatible avec l'API Gateway qui propage l'authentification.
    Utilise django-tenants correctement avec connection.set_tenant()
    
    Fonctionnalités:
    1. Validation du tenant_id via tenant-service (avec cache)
    2. Vérification de l'existence locale du tenant
    3. Création contrôlée des tenants si nécessaire
    4. Utilisation correcte de django-tenants
    """
    
    # Endpoints qui ne nécessitent pas de X-Tenant-ID header
    PUBLIC_ENDPOINTS = [
        '/health/',
        '/admin/',
        '/static/',
        '/favicon.ico',
        '/api/schema/',
        '/api/docs/',
        '/api/debug/',
    ]
    
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # Vérifier si l'endpoint est public
        if any(request.path.startswith(endpoint) for endpoint in self.PUBLIC_ENDPOINTS):
            return self.get_response(request)
            
        tenant_id = request.headers.get('X-Tenant-ID')
        
        if not tenant_id:
            return JsonResponse({
                'error': 'Missing X-Tenant-ID header',
                'code': 'missing_tenant_id',
                'service': 'document-service'
            }, status=400)

        try:
            # Valider que c'est un UUID valide
            try:
                tenant_uuid = uuid.UUID(tenant_id)
            except ValueError:
                return JsonResponse({
                    'error': 'X-Tenant-ID doit être un UUID valide',
                    'code': 'invalid_uuid_format',
                    'service': 'document-service'
                }, status=400)
            
            # Vérifier le cache d'abord
            cache_key = f'document_tenant_info:{tenant_id}'
            tenant_info = cache.get(cache_key)
            
            if not tenant_info:
                # Valider le tenant via tenant-service
                tenant_service_url = getattr(settings, 'TENANT_SERVICE_URL', 'http://localhost:8001')
                response = requests.get(
                    f"{tenant_service_url}/api/tenants/{tenant_id}/",
                    headers={'Accept': 'application/json'},
                    timeout=10
                )
                
                if not response.ok:
                    logger.warning(f"Document - Tenant invalide ou inexistant: {tenant_id}")
                    return JsonResponse({
                        'error': 'Invalid or non-existent tenant',
                        'code': 'invalid_tenant_id',
                        'service': 'document-service'
                    }, status=401)

                tenant_data = response.json()
                tenant_info = {
                    'tenant_uuid': tenant_data.get('id'),
                    'is_active': tenant_data.get('is_active', True),
                    'name': tenant_data.get('name', f"Tenant {tenant_id}"),
                    'schema_name': tenant_data.get('schema_name', f"tenant_{str(tenant_uuid).replace('-', '_')}")
                }
                
                # Mettre en cache pour 10 minutes
                cache.set(cache_key, tenant_info, 600)
            
            # Vérifier que le tenant est actif
            if not tenant_info.get('is_active'):
                return JsonResponse({
                    'error': 'Tenant is inactive',
                    'code': 'inactive_tenant',
                    'service': 'document-service'
                }, status=403)

            # Récupérer ou créer le tenant localement (contrôlé et sécurisé)
            tenant = self._get_or_create_tenant(tenant_uuid, tenant_info)
            if not tenant:
                logger.error(f"Document - Impossible de configurer le tenant {tenant_id}")
                return JsonResponse({
                    'error': 'Failed to configure tenant in document service',
                    'code': 'tenant_configuration_failed',
                    'service': 'document-service'
                }, status=503)
            
            # DJANGO-TENANTS CORRECT: Définir le contexte tenant pour la requête
            from django.db import connection
            connection.set_tenant(tenant)
            
            # Ajouter les informations du tenant à la requête
            request.tenant = tenant
            request.tenant_id = tenant_id
            request.tenant_schema = tenant_info['schema_name']
            request.tenant_name = tenant_info['name']
            
            logger.debug(f"Document - Tenant activé: {tenant_id} (schema: {tenant_info['schema_name']})")
            
            response = self.get_response(request)
            
            # DJANGO-TENANTS CORRECT: Réinitialiser le schéma après la requête
            connection.set_schema_to_public()
            
            return response
            
        except requests.RequestException as e:
            logger.error(f"Document - Erreur de connexion au service tenant: {str(e)}")
            return JsonResponse({
                'error': 'Tenant service unavailable',
                'code': 'tenant_service_error',
                'service': 'document-service'
            }, status=503)
            
        except Exception as e:
            logger.error(f"Document - Erreur inattendue dans le middleware: {str(e)}")
            return JsonResponse({
                'error': 'Internal server error',
                'code': 'internal_error',
                'service': 'document-service'
            }, status=500)
    
    def _get_or_create_tenant(self, tenant_uuid, tenant_info):
        """
        Récupère un tenant existant ou le crée de manière contrôlée.
        Compatible avec l'architecture SOA mais sécurisé.
        """
        try:
            # Essayer de récupérer le tenant existant
            tenant = Client.objects.filter(tenant_uuid=tenant_uuid).first()
            if tenant:
                logger.debug(f"Document - Tenant trouvé: {tenant.name}")
                return tenant
            
            # Tenant validé par tenant-service mais inexistant localement
            # Création contrôlée uniquement si validé par tenant-service
            logger.info(f"Document - Création contrôlée du tenant: {tenant_uuid}")
            
            schema_name = tenant_info['schema_name']
            tenant_name = tenant_info['name']
            
            # Éviter les conflits de nom de schéma
            if Client.objects.filter(schema_name=schema_name).exists():
                schema_name = f"tenant_{str(tenant_uuid).replace('-', '_')[:12]}"
            
            # Créer le tenant de manière atomique
            from django.db import transaction
            try:
                with transaction.atomic():
                    tenant = Client.objects.create(
                        tenant_uuid=tenant_uuid,
                        schema_name=schema_name,
                        name=tenant_name,
                        is_active=True
                    )
                    
                    # Exécuter les migrations pour le nouveau schéma
                    from django.core.management import call_command
                    call_command('migrate_schemas', schema_name=schema_name, verbosity=0)
                    
                    logger.info(f"Document - Tenant créé: {tenant_name} (schema: {schema_name})")
                    return tenant
                    
            except Exception as create_error:
                # En cas d'erreur, essayer de récupérer (race condition possible)
                logger.warning(f"Document - Erreur création, récupération: {str(create_error)}")
                tenant = Client.objects.filter(tenant_uuid=tenant_uuid).first()
                if tenant:
                    return tenant
                raise create_error
                
        except Exception as e:
            logger.error(f"Document - Erreur configuration tenant: {str(e)}")
            return None