"""
Mixins pour les ViewSets de documents
"""
import hashlib
import json
from datetime import datetime, timedelta
from decimal import Decimal

from django.core.cache import cache
from django.db.models import Q, Count, Sum, Avg, F, Max, Min
from django.utils import timezone
from rest_framework import status
from rest_framework.response import Response


class CacheMixin:
    """Mixin pour la gestion du cache Redis"""
    
    cache_timeout = 30  # 30 secondes par défaut
    
    def _get_cache_key(self, action, **kwargs):
        """Génère une clé de cache unique basée sur l'action et les paramètres"""
        # Récupérer l'ID du tenant depuis le middleware
        tenant_id = getattr(self.request, 'tenant_id', 'default')
        user_id = self.request.user.id if self.request.user.is_authenticated else 'anonymous'
        
        # Créer un hash des paramètres pour une clé unique
        params_hash = hashlib.md5(
            json.dumps(kwargs, sort_keys=True, default=str).encode()
        ).hexdigest()[:8]
        
        model_name = self.get_queryset().model._meta.label_lower.replace('.', '_')
        return f"{model_name}_{action}_{tenant_id}_{user_id}_{params_hash}"
    
    def _invalidate_cache(self):
        """Invalide le cache pour ce tenant et utilisateur"""
        tenant_id = getattr(self.request, 'tenant_id', 'default')
        user_id = self.request.user.id if self.request.user.is_authenticated else 'anonymous'
        model_name = self.get_queryset().model._meta.label_lower.replace('.', '_')
        
        # Clés communes à invalider
        common_keys = [
            f"{model_name}_list_{tenant_id}_{user_id}_",
            f"{model_name}_stats_{tenant_id}_{user_id}_"
        ]
        
        cache.delete_many(common_keys)
    
    def get_cached_response(self, action, cache_key_params=None):
        """Récupère une réponse depuis le cache"""
        if cache_key_params is None:
            cache_key_params = {'filters': self.request.GET.dict()}
        
        cache_key = self._get_cache_key(action, **cache_key_params)
        cached_data = cache.get(cache_key)
        
        if cached_data:
            response = Response(cached_data)
            response['X-Cache-Status'] = 'HIT'
            response['X-Cache-Key'] = cache_key
            return response
        
        return None
    
    def set_cached_response(self, action, data, cache_key_params=None):
        """Met en cache une réponse"""
        if cache_key_params is None:
            cache_key_params = {'filters': self.request.GET.dict()}
        
        cache_key = self._get_cache_key(action, **cache_key_params)
        cache.set(cache_key, data, self.cache_timeout)
        
        # Ajouter les headers de cache à la réponse
        response = Response(data)
        response['X-Cache-Status'] = 'MISS'
        response['X-Cache-Key'] = cache_key
        return response


class QueryOptimizationMixin:
    """Mixin pour les optimisations de requêtes"""
    
    def get_optimized_queryset(self, action=None):
        """Retourne un queryset optimisé selon l'action"""
        base_queryset = self.get_queryset()
        action = action or getattr(self, 'action', 'list')
        
        if action == 'list':
            # Pour la liste, éviter les gros champs et optimiser les relations
            return base_queryset.select_related().defer(
                'notes', 'terms_and_conditions', 'client_address', 'project_address'
            ).annotate(items_count=Count('items'))
        
        elif action == 'retrieve':
            # Pour le détail, charger toutes les relations nécessaires
            return base_queryset.select_related().prefetch_related('items')
        
        elif action in ['stats', 'get_stats']:
            # Pour les stats, seulement les champs nécessaires
            return base_queryset.only(
                'id', 'status', 'total_ht', 'total_ttc', 'tier_id',
                'issue_date', 'created_at'
            )
        
        return base_queryset.select_related()


class FilterMixin:
    """Mixin pour les filtres avancés"""
    
    def apply_advanced_filters(self, queryset):
        """Applique les filtres avancés depuis les paramètres de requête"""
        # Filtre par client
        client_id = self.request.query_params.get('client_id')
        if client_id:
            queryset = queryset.filter(tier_id=client_id)
        
        # Filtre par statut multiple
        status_list = self.request.query_params.get('status_list')
        if status_list:
            status_values = status_list.split(',')
            queryset = queryset.filter(status__in=status_values)
        
        # Filtres par date
        date_from = self.request.query_params.get('date_from')
        if date_from:
            try:
                date_from = datetime.strptime(date_from, '%Y-%m-%d').date()
                queryset = queryset.filter(issue_date__gte=date_from)
            except ValueError:
                pass
        
        date_to = self.request.query_params.get('date_to')
        if date_to:
            try:
                date_to = datetime.strptime(date_to, '%Y-%m-%d').date()
                queryset = queryset.filter(issue_date__lte=date_to)
            except ValueError:
                pass
        
        # Filtres par montant
        min_amount = self.request.query_params.get('min_amount')
        if min_amount:
            try:
                min_amount = Decimal(min_amount)
                queryset = queryset.filter(total_ttc__gte=min_amount)
            except (ValueError, TypeError):
                pass
        
        max_amount = self.request.query_params.get('max_amount')
        if max_amount:
            try:
                max_amount = Decimal(max_amount)
                queryset = queryset.filter(total_ttc__lte=max_amount)
            except (ValueError, TypeError):
                pass
        
        # Recherche textuelle
        search = self.request.query_params.get('search')
        if search:
            queryset = queryset.filter(
                Q(number__icontains=search) |
                Q(client_name__icontains=search) |
                Q(project_name__icontains=search) |
                Q(notes__icontains=search)
            )
        
        return queryset


class StatsMixin:
    """Mixin pour les statistiques"""
    
    def calculate_base_stats(self, queryset):
        """Calcule les statistiques de base pour tous les documents"""
        # Compter par statut avec une seule requête
        status_counts = queryset.aggregate(
            total=Count('id'),
            **{
                status_value: Count('id', filter=Q(status=status_value))
                for status_value, _ in self.get_queryset().model.status.field.choices
            }
        )
        
        # Montants totaux
        amounts = queryset.aggregate(
            total_amount_ht=Sum('total_ht') or Decimal('0'),
            total_amount_ttc=Sum('total_ttc') or Decimal('0'),
            average_amount=Avg('total_ttc') or Decimal('0')
        )
        
        return {**status_counts, **amounts}


class AuditMixin:
    """Mixin pour l'audit et les métadonnées"""
    
    def get_user_info(self):
        """Récupère les informations de l'utilisateur connecté"""
        if self.request.user and hasattr(self.request.user, 'email'):
            return self.request.user.email
        elif self.request.user and hasattr(self.request.user, 'username'):
            return self.request.user.username
        return None
    
    def perform_create(self, serializer):
        """Personnalise la création avec l'utilisateur créateur"""
        serializer.save(created_by=self.get_user_info())
        self._invalidate_cache()
    
    def perform_update(self, serializer):
        """Personnalise la mise à jour avec l'utilisateur modificateur"""
        serializer.save(updated_by=self.get_user_info())
        self._invalidate_cache()
    
    def perform_destroy(self, instance):
        """Logique métier lors de la suppression"""
        super().perform_destroy(instance)
        self._invalidate_cache()


class DocumentActionMixin:
    """Mixin pour les actions sur les documents"""
    
    def perform_document_action(self, instance, action, note=None):
        """Effectue une action sur un document avec audit"""
        # Mapper les actions vers les méthodes
        action_methods = {
            'send': self._send_document,
            'accept': self._accept_document,
            'reject': self._reject_document,
            'cancel': self._cancel_document,
            'validate': self._validate_document
        }
        
        if action not in action_methods:
            return Response(
                {'error': f'Action "{action}" non supportée'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            result = action_methods[action](instance, note)
            self._invalidate_cache()
            return Response(result)
        except Exception as e:
            return Response(
                {'error': str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )
    
    def _send_document(self, instance, note=None):
        """Envoie un document (devis ou facture)"""
        if hasattr(instance, 'mark_as_sent'):
            instance.mark_as_sent()
        elif hasattr(instance, 'validate_and_send'):
            instance.validate_and_send()
        else:
            # Fallback générique
            instance.status = 'sent'
            instance.save(update_fields=['status'])
        
        return {'message': 'Document envoyé avec succès', 'status': instance.status}
    
    def _accept_document(self, instance, note=None):
        """Accepte un document (principalement pour les devis)"""
        if hasattr(instance, 'mark_as_accepted'):
            instance.mark_as_accepted()
            return {'message': 'Devis accepté avec succès', 'status': instance.status}
        else:
            return {'error': 'Action non supportée pour ce type de document'}
    
    def _reject_document(self, instance, note=None):
        """Rejette un document"""
        if hasattr(instance, 'mark_as_rejected'):
            instance.mark_as_rejected()
            return {'message': 'Document rejeté', 'status': instance.status}
        else:
            return {'error': 'Action non supportée pour ce type de document'}
    
    def _cancel_document(self, instance, note=None):
        """Annule un document"""
        if hasattr(instance, 'mark_as_cancelled'):
            instance.mark_as_cancelled()
        else:
            # Fallback générique
            instance.status = 'cancelled'
            instance.save(update_fields=['status'])
        
        return {'message': 'Document annulé', 'status': instance.status}
    
    def _validate_document(self, instance, note=None):
        """Valide un document (principalement pour les factures)"""
        if hasattr(instance, 'validate_and_send'):
            instance.validate_and_send()
            return {'message': 'Facture validée et envoyée', 'status': instance.status}
        else:
            return {'error': 'Action non supportée pour ce type de document'}


class BulkOperationMixin:
    """Mixin pour les opérations en lot"""
    
    def perform_bulk_operation(self, action, document_ids, extra_data=None):
        """Effectue une opération en lot sur plusieurs documents"""
        if len(document_ids) > 100:
            return Response(
                {'error': 'Maximum 100 documents autorisés par opération en lot'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        queryset = self.get_queryset().filter(id__in=document_ids)
        
        if action == 'delete':
            count = queryset.count()
            queryset.delete()
            self._invalidate_cache()
            return Response({'message': f'{count} documents supprimés'})
        
        elif action == 'send':
            count = 0
            for instance in queryset:
                if hasattr(instance, 'mark_as_sent'):
                    instance.mark_as_sent()
                    count += 1
            self._invalidate_cache()
            return Response({'message': f'{count} documents envoyés'})
        
        elif action == 'cancel':
            count = queryset.update(status='cancelled')
            self._invalidate_cache()
            return Response({'message': f'{count} documents annulés'})
        
        else:
            return Response(
                {'error': f'Action "{action}" non supportée'},
                status=status.HTTP_400_BAD_REQUEST
            )


class ExportMixin:
    """Mixin pour l'export de documents"""
    
    def export_document(self, instance, format_type='pdf', include_details=True):
        """Exporte un document dans le format spécifié"""
        # TODO: Implémenter les générateurs de PDF/Excel
        # Pour l'instant, retourner les données JSON
        
        if format_type == 'pdf':
            return self._export_pdf(instance, include_details)
        elif format_type == 'excel':
            return self._export_excel(instance, include_details)
        elif format_type == 'csv':
            return self._export_csv(instance, include_details)
        else:
            return Response(
                {'error': 'Format non supporté'},
                status=status.HTTP_400_BAD_REQUEST
            )
    
    def _export_pdf(self, instance, include_details):
        """Export PDF - À implémenter"""
        return Response({
            'message': 'Export PDF non encore implémenté',
            'format': 'pdf',
            'document_id': str(instance.id)
        })
    
    def _export_excel(self, instance, include_details):
        """Export Excel - À implémenter"""
        return Response({
            'message': 'Export Excel non encore implémenté',
            'format': 'excel',
            'document_id': str(instance.id)
        })
    
    def _export_csv(self, instance, include_details):
        """Export CSV - À implémenter"""
        return Response({
            'message': 'Export CSV non encore implémenté',
            'format': 'csv',
            'document_id': str(instance.id)
        }) 