"""
Pagination unifiée pour les documents
"""
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response
from .utils import CamelCaseResponseMixin


class DocumentsPagination(PageNumberPagination):
    """Pagination optimisée pour tous les documents"""
    page_size = 10  # 10 documents par page par défaut
    page_size_query_param = 'page_size'
    max_page_size = 50  # Maximum 50 documents par page
    page_query_param = 'page'
    
    def get_paginated_response(self, data):
        """Réponse paginée enrichie pour le frontend"""
        response_data = {
            'results': data,
            'pagination': {
                'count': self.page.paginator.count,
                'num_pages': self.page.paginator.num_pages,
                'current_page': self.page.number,
                'page_size': self.get_page_size(self.request),
                'has_next': self.page.has_next(),
                'has_previous': self.page.has_previous(),
                'next_page': self.page.next_page_number() if self.page.has_next() else None,
                'previous_page': self.page.previous_page_number() if self.page.has_previous() else None,
            }
        }
        
        # Convertir les clés en camelCase
        return Response(CamelCaseResponseMixin.to_camel_case(response_data))


class QuotesPagination(DocumentsPagination):
    """Pagination spécialisée pour les devis"""
    pass  # Peut être personnalisée plus tard si besoin


class InvoicesPagination(DocumentsPagination):
    """Pagination spécialisée pour les factures"""
    max_page_size = 2000  # Plus élevé pour les exports de factures


class DocumentItemsPagination(PageNumberPagination):
    """Pagination pour les éléments de documents"""
    page_size = 50  # Plus d'éléments par page
    page_size_query_param = 'page_size'
    max_page_size = 200
    page_query_param = 'page'
    
    def get_paginated_response(self, data):
        """Réponse paginée enrichie pour le frontend"""
        response_data = {
            'results': data,
            'pagination': {
                'count': self.page.paginator.count,
                'num_pages': self.page.paginator.num_pages,
                'current_page': self.page.number,
                'page_size': self.get_page_size(self.request),
                'has_next': self.page.has_next(),
                'has_previous': self.page.has_previous(),
                'next_page': self.page.next_page_number() if self.page.has_next() else None,
                'previous_page': self.page.previous_page_number() if self.page.has_previous() else None,
            }
        }
        
        # Convertir les clés en camelCase
        return Response(CamelCaseResponseMixin.to_camel_case(response_data)) 