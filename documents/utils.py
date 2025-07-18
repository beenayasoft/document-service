"""
Utilitaires pour le service document
"""
import re
from collections import OrderedDict
from rest_framework.utils.serializer_helpers import ReturnDict
from django.utils.deprecation import MiddlewareMixin


def to_camel_case(snake_str):
    """
    Convertit une chaîne snake_case en camelCase
    Exemple: 'hello_world' -> 'helloWorld'
    """
    components = snake_str.split('_')
    return components[0] + ''.join(x.title() for x in components[1:])


def to_snake_case(camel_str):
    """
    Convertit une chaîne camelCase en snake_case
    Exemple: 'helloWorld' -> 'hello_world'
    """
    # Utilise une expression régulière pour insérer un underscore avant chaque lettre majuscule
    # puis convertit tout en minuscules
    s1 = re.sub('(.)([A-Z][a-z]+)', r'\1_\2', camel_str)
    return re.sub('([a-z0-9])([A-Z])', r'\1_\2', s1).lower()


class CamelCaseResponseMixin:
    """
    Mixin pour convertir les clés des réponses de snake_case à camelCase
    """
    def to_representation(self, instance):
        """
        Surcharge la méthode to_representation pour convertir les clés en camelCase
        """
        result = super().to_representation(instance)
        return self._convert_dict_keys_to_camel_case(result)

    def _convert_dict_keys_to_camel_case(self, data):
        """
        Convertit récursivement toutes les clés d'un dictionnaire de snake_case à camelCase
        """
        if isinstance(data, dict):
            new_dict = OrderedDict()
            for key, value in data.items():
                if key == 'id' or key.endswith('_id'):  # Garder id et les clés *_id telles quelles
                    new_key = key
                else:
                    new_key = to_camel_case(key)
                new_dict[new_key] = self._convert_dict_keys_to_camel_case(value)
            
            # Si c'est un ReturnDict (résultat de serializer.data), préserver le contexte
            if isinstance(data, ReturnDict):
                return ReturnDict(new_dict, serializer=data.serializer)
            return new_dict
        elif isinstance(data, list):
            return [self._convert_dict_keys_to_camel_case(item) for item in data]
        return data
        
    @staticmethod
    def to_camel_case(data):
        """
        Méthode statique pour convertir les clés d'un dictionnaire de snake_case à camelCase
        sans avoir besoin d'instancier la classe
        """
        if isinstance(data, dict):
            new_dict = OrderedDict()
            for key, value in data.items():
                if key == 'id' or key.endswith('_id'):  # Garder id et les clés *_id telles quelles
                    new_key = key
                else:
                    new_key = to_camel_case(key)
                new_dict[new_key] = CamelCaseResponseMixin.to_camel_case(value)
            return new_dict
        elif isinstance(data, list):
            return [CamelCaseResponseMixin.to_camel_case(item) for item in data]
        return data
