"""
Middleware pour la conversion camelCase <-> snake_case
"""
import logging
from django.utils.deprecation import MiddlewareMixin
from django.http.request import QueryDict
from .utils import to_snake_case

logger = logging.getLogger(__name__)


class CamelCaseToSnakeCaseMiddleware(MiddlewareMixin):
    """
    Middleware pour convertir les paramètres de requête de camelCase à snake_case
    """
    def process_request(self, request):
        """
        Convertit les paramètres GET et POST de camelCase à snake_case
        """
        # Convertir les paramètres GET
        if request.GET:
            # Créer un nouveau QueryDict pour stocker les paramètres convertis
            converted_get = QueryDict('', mutable=True)
            
            # Logger les paramètres avant conversion pour débogage
            logger.debug(f"Paramètres GET avant conversion: {dict(request.GET.items())}")
            
            for key, values in request.GET.lists():
                # Convertir la clé en snake_case
                snake_key = to_snake_case(key)
                
                # Ajouter toutes les valeurs associées à cette clé
                for value in values:
                    converted_get.appendlist(snake_key, value)
            
            # Logger les paramètres après conversion pour débogage
            logger.debug(f"Paramètres GET après conversion: {dict(converted_get.items())}")
            
            # Remplacer les paramètres GET par les paramètres convertis
            request.GET = converted_get
        
        # Convertir les paramètres POST
        if request.POST:
            # Créer un nouveau QueryDict pour stocker les paramètres convertis
            converted_post = QueryDict('', mutable=True)
            
            # Logger les paramètres avant conversion pour débogage
            logger.debug(f"Paramètres POST avant conversion: {dict(request.POST.items())}")
            
            for key, values in request.POST.lists():
                # Convertir la clé en snake_case
                snake_key = to_snake_case(key)
                
                # Ajouter toutes les valeurs associées à cette clé
                for value in values:
                    converted_post.appendlist(snake_key, value)
            
            # Logger les paramètres après conversion pour débogage
            logger.debug(f"Paramètres POST après conversion: {dict(converted_post.items())}")
            
            # Remplacer les paramètres POST par les paramètres convertis
            request.POST = converted_post
        
        return None
