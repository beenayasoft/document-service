"""
Modèles partagés pour django-tenants - Document Service
"""
from django.db import models
from django_tenants.models import TenantMixin, DomainMixin
import uuid


class Client(TenantMixin):
    """
    Modèle Client pour django-tenants
    Contient les informations sur le tenant/client
    """
    # Champs obligatoires pour django-tenants
    auto_create_schema = True
    
    # Champs métier
    name = models.CharField(max_length=100, verbose_name="Nom du client")
    tenant_uuid = models.UUIDField(
        unique=True, 
        verbose_name="UUID du tenant",
        help_text="UUID fourni par le service auth"
    )
    
    # Métadonnées
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Créé le")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Mis à jour le")
    
    # Champs optionnels pour le futur
    is_active = models.BooleanField(default=True, verbose_name="Actif")
    max_documents = models.IntegerField(
        default=1000, 
        verbose_name="Nombre maximum de documents"
    )
    
    class Meta:
        verbose_name = "Client"
        verbose_name_plural = "Clients"
        indexes = [
            models.Index(fields=['tenant_uuid']),
            models.Index(fields=['is_active']),
        ]
    
    def __str__(self):
        return f"{self.name} ({self.schema_name})"


class Domain(DomainMixin):
    """
    Modèle Domain pour django-tenants
    Associe un domaine à un tenant
    """
    pass
