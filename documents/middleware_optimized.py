"""
Middleware optimisé pour le document-service
Basé sur le middleware du library-service mais adapté aux schémas manuels
SANS REDIS - Cache Django simple
"""
import uuid
import logging
import requests
from django.conf import settings
from django.core.cache import cache
from django.http import JsonResponse
from django.utils.deprecation import MiddlewareMixin
from django.db import connection

logger = logging.getLogger(__name__)

class OptimizedTenantMiddleware(MiddlewareMixin):
    """
    Middleware optimisé pour la gestion des tenants via headers HTTP.
    
    Améliore les performances par rapport au middleware original :
    1. Cache simple Django (pas de Redis)
    2. Un seul appel au tenant-service par requête
    3. Pas de création automatique de schémas
    4. Validation tenant mise en cache
    """
    
    # Endpoints qui ne nécessitent pas de X-Tenant-ID header
    PUBLIC_ENDPOINTS = [
        '/health/',
        '/admin/',
        '/api/schema/',
        '/api/docs/',
        '/api/debug/',
        '/static/',
        '/favicon.ico',
    ]
    
    def process_request(self, request):
        """
        Traite les headers X-Tenant-ID de manière optimisée
        """
        # Vérifier si l'endpoint est public
        if any(request.path.startswith(endpoint) for endpoint in self.PUBLIC_ENDPOINTS):
            self._set_schema('public')
            return None
            
        tenant_id = request.META.get('HTTP_X_TENANT_ID')
        
        if not tenant_id:
            return JsonResponse({
                'error': 'Header X-Tenant-ID requis',
                'detail': 'Le service Document nécessite un tenant_id pour fonctionner',
                'service': 'document-service'
            }, status=400)

        try:
            # Validation UUID rapide
            try:
                tenant_uuid = uuid.UUID(tenant_id)
            except ValueError:
                return JsonResponse({
                    'error': 'X-Tenant-ID doit être un UUID valide',
                    'code': 'invalid_uuid_format',
                    'service': 'document-service'
                }, status=400)
            
            # Vérifier le cache en premier (optimisation clé)
            cache_key = f'document_tenant_validation:{tenant_id}'
            tenant_validation = cache.get(cache_key)
            
            if not tenant_validation:
                # Validation tenant via un seul appel
                tenant_validation = self._validate_tenant_with_service(tenant_id)
                if not tenant_validation['is_valid']:
                    return JsonResponse({
                        'error': tenant_validation['error'],
                        'code': 'invalid_tenant_id',
                        'service': 'document-service'
                    }, status=401)
                
                # Mettre en cache pour 10 minutes (plus long que library-service)
                cache.set(cache_key, tenant_validation, 600)
                logger.info(f"Document - Tenant {tenant_id} validé et mis en cache")
            else:
                logger.debug(f"Document - Cache hit pour tenant {tenant_id}")
            
            # Vérifier que le tenant est actif
            if not tenant_validation.get('is_active', True):
                return JsonResponse({
                    'error': 'Tenant is inactive',
                    'code': 'inactive_tenant',
                    'service': 'document-service'
                }, status=403)

            # Configurer le schéma PostgreSQL (sans création automatique)
            schema_name = f"tenant_{tenant_id.replace('-', '_')}"
            
            if not self._schema_exists(schema_name):
                logger.warning(f"Document - Schéma {schema_name} inexistant pour tenant {tenant_id}")
                return JsonResponse({
                    'error': 'Tenant schema not found',
                    'detail': f'Le schéma {schema_name} doit être créé manuellement',
                    'code': 'schema_not_found',
                    'service': 'document-service'
                }, status=503)
            
            # Sélectionner le schéma
            self._set_schema(schema_name)
            
            # Ajouter les informations du tenant à la requête (format simplifié)
            request.tenant_id = tenant_id
            request.schema_name = schema_name
            request.tenant_name = tenant_validation.get('name', f"Tenant {tenant_id}")
            
            logger.debug(f"Document - Tenant activé: {tenant_id} (schema: {schema_name})")
            
            return None
            
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
    
    def process_response(self, request, response):
        """
        Remet le schéma par défaut après traitement
        """
        try:
            self._set_schema('public')
        except Exception as e:
            logger.warning(f"Document - Erreur reset schéma: {e}")
        return response
    
    def _validate_tenant_with_service(self, tenant_id):
        """
        Valide un tenant avec le tenant-service en un seul appel optimisé
        """
        try:
            tenant_service_url = getattr(settings, 'TENANT_SERVICE_URL', 'http://localhost:8001')
            
            # Un seul appel pour récupérer toutes les infos nécessaires
            response = requests.get(
                f"{tenant_service_url}/api/tenants/{tenant_id}/",
                headers={'Accept': 'application/json'},
                timeout=getattr(settings, 'TENANT_SERVICE_TIMEOUT', 10)
            )
            
            if not response.ok:
                logger.warning(f"Document - Tenant invalide ou inexistant: {tenant_id}")
                return {
                    'is_valid': False,
                    'error': 'Invalid or non-existent tenant'
                }

            tenant_data = response.json()
            return {
                'is_valid': True,
                'tenant_uuid': tenant_data.get('id'),
                'is_active': tenant_data.get('is_active', True),
                'name': tenant_data.get('name', f"Tenant {tenant_id}"),
                'schema_name': f"tenant_{tenant_id.replace('-', '_')}"
            }
            
        except requests.RequestException as e:
            logger.error(f"Document - Erreur validation tenant {tenant_id}: {e}")
            return {
                'is_valid': False,
                'error': f'Tenant service error: {str(e)}'
            }
    
    def _set_schema(self, schema_name):
        """
        Configure PostgreSQL pour utiliser le schéma spécifié
        """
        try:
            with connection.cursor() as cursor:
                cursor.execute(f"SET search_path TO {schema_name}, public")
        except Exception as e:
            logger.error(f"Document - Erreur changement schéma vers {schema_name}: {e}")
    
    def _schema_exists(self, schema_name):
        """
        Vérifie si un schéma existe dans la base de données
        """
        try:
            with connection.cursor() as cursor:
                cursor.execute("""
                    SELECT 1 FROM information_schema.schemata 
                    WHERE schema_name = %s
                """, [schema_name])
                return cursor.fetchone() is not None
        except Exception as e:
            logger.error(f"Document - Erreur vérification schéma {schema_name}: {e}")
            return False