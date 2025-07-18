"""
Router pour la gestion des migrations avec schémas multiples
"""

class TenantSchemaRouter:
    """
    Router pour gérer les migrations et requêtes avec des schémas PostgreSQL séparés par tenant
    """
    
    def db_for_read(self, model, **hints):
        """
        Détermine quelle base de données utiliser pour les lectures
        """
        return 'default'
    
    def db_for_write(self, model, **hints):
        """
        Détermine quelle base de données utiliser pour les écritures
        """
        return 'default'
    
    def allow_migrate(self, db, app_label, model_name=None, **hints):
        """
        Détermine si une migration doit être appliquée
        """
        # Permettre toutes les migrations dans la base par défaut
        return db == 'default'
    
    def allow_relation(self, obj1, obj2, **hints):
        """
        Détermine si une relation entre deux objets est autorisée
        """
        return True 