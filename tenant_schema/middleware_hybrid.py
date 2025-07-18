"""
Middleware hybride pour gérer les headers X-Tenant-ID avec django-tenants - Document Service
"""
import logging
from django.http import JsonResponse
from django.utils.deprecation import MiddlewareMixin
from django_tenants.utils import get_tenant_model
from django.db import connection

logger = logging.getLogger(__name__)

class HeaderTenantMiddleware(MiddlewareMixin):
    """
    Middleware hybride qui convertit les headers X-Tenant-ID en tenant django-tenants
    """
    
    def process_request(self, request):
        """
        Traite les headers X-Tenant-ID et configure le tenant approprié
        """
        # Extraire le tenant_id depuis les headers
        tenant_id = request.META.get('HTTP_X_TENANT_ID')
        
        if not tenant_id:
            # Pour les endpoints publics, utiliser le schéma public
            if request.path in ['/health/', '/admin/', '/api/schema/', '/api/docs/']:
                return None
            
            return JsonResponse({
                'error': 'Header X-Tenant-ID requis',
                'detail': 'Le service Document nécessite un tenant_id pour fonctionner'
            }, status=400)
        
        # Validation du format UUID
        try:
            import uuid
            uuid.UUID(tenant_id)
        except ValueError:
            return JsonResponse({
                'error': 'Format tenant_id invalide',
                'detail': 'Le tenant_id doit être un UUID valide'
            }, status=400)
        
        try:
            # Chercher le tenant correspondant
            Client = get_tenant_model()
            try:
                tenant = Client.objects.get(tenant_uuid=tenant_id)
                logger.info(f"Tenant existant trouvé: {tenant.schema_name} pour UUID {tenant_id}")
            except Client.DoesNotExist:
                # Si le tenant n'existe pas, le créer automatiquement
                logger.info(f"Création automatique du tenant pour UUID {tenant_id}")
                tenant = self._create_tenant_from_uuid(tenant_id)
                if not tenant:
                    return JsonResponse({
                        'error': 'Impossible de créer le tenant',
                        'detail': f'Erreur lors de la création du tenant pour {tenant_id}'
                    }, status=500)
            
            # Configurer le tenant dans la requête
            request.tenant = tenant
            
            # Basculer vers le schéma du tenant
            connection.set_tenant(tenant)
            
            logger.info(f"Tenant configuré: {tenant.schema_name} pour UUID {tenant_id}")
            
        except Exception as e:
            logger.error(f"Erreur lors de la configuration du tenant {tenant_id}: {e}")
            # En cas d'erreur, continuer sans tenant (mode dégradé)
            logger.warning(f"Continuation en mode dégradé pour {tenant_id}")
            return None
        
        return None
    
    def _create_tenant_from_uuid(self, tenant_id):
        """
        Crée un nouveau tenant à partir d'un UUID
        """
        try:
            from django.db import transaction
            Client = get_tenant_model()
            from .models import Domain
            
            # Créer le nom de schéma à partir de l'UUID
            schema_name = f"tenant_{tenant_id.replace('-', '_')}"
            
            # Utiliser une transaction atomique pour éviter les conflits
            with transaction.atomic():
                # Vérifier si le tenant existe déjà (double-check)
                if Client.objects.filter(tenant_uuid=tenant_id).exists():
                    return Client.objects.get(tenant_uuid=tenant_id)
                
                # Créer le tenant avec auto_create_schema=True
                tenant = Client(
                    schema_name=schema_name,
                    name=f"Tenant {tenant_id}",
                    tenant_uuid=tenant_id
                )
                tenant.save()
                
                # Créer le domaine fictif
                Domain.objects.create(
                    tenant=tenant,
                    domain=f"{tenant_id}.internal",
                    is_primary=True
                )
                
                logger.info(f"Tenant créé automatiquement: {schema_name} pour UUID {tenant_id}")
                return tenant
            
        except Exception as e:
            logger.error(f"Erreur lors de la création du tenant {tenant_id}: {e}")
            return None