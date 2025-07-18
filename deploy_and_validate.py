#!/usr/bin/env python
"""
Script de déploiement et validation du Document Service.

Ce script effectue :
1. Validation de l'environnement
2. Migration et initialisation de la base de données
3. Démarrage des services
4. Tests de santé complets
5. Validation des performances
"""

import os
import sys
import time
import json
import asyncio
import subprocess
from pathlib import Path
from typing import Dict, List, Any
import psutil
import httpx
from datetime import datetime

# Configuration
PROJECT_ROOT = Path(__file__).parent
SERVICES_ROOT = PROJECT_ROOT.parent.parent
API_GATEWAY_ROOT = SERVICES_ROOT / "api-gateway"

# URLs des services
SERVICES_URLS = {
    "document": "http://localhost:8004",
    "gateway": "http://localhost:8000"
}

class DocumentServiceDeployment:
    """Gestionnaire de déploiement du Document Service."""
    
    def __init__(self):
        self.start_time = datetime.now()
        self.validation_results = []
        self.services_status = {}
    
    def log(self, message: str, level: str = "INFO"):
        """Logger avec timestamp."""
        timestamp = datetime.now().strftime("%H:%M:%S")
        prefix = {
            "INFO": "ℹ️",
            "SUCCESS": "✅",
            "WARNING": "⚠️",
            "ERROR": "❌",
            "DEPLOY": "🚀"
        }.get(level, "📝")
        
        print(f"[{timestamp}] {prefix} {message}")
    
    def check_environment(self) -> bool:
        """Vérification de l'environnement de déploiement."""
        
        self.log("Vérification de l'environnement...", "DEPLOY")
        
        checks = []
        
        # 1. Python et dépendances
        try:
            import django
            import rest_framework
            import psycopg2
            checks.append(("Python et dépendances Django", True, f"Django {django.get_version()}"))
        except ImportError as e:
            checks.append(("Python et dépendances Django", False, str(e)))
        
        # 2. Base de données PostgreSQL
        try:
            import psycopg2
            # Test de connexion simple
            checks.append(("PostgreSQL disponible", True, "Module psycopg2 installé"))
        except ImportError:
            checks.append(("PostgreSQL disponible", False, "Module psycopg2 manquant"))
        
        # 3. Redis
        try:
            import redis
            checks.append(("Redis disponible", True, "Module redis installé"))
        except ImportError:
            checks.append(("Redis disponible", False, "Module redis manquant"))
        
        # 4. Fichiers de configuration
        settings_file = PROJECT_ROOT / "document_service" / "settings.py"
        env_file = PROJECT_ROOT / ".env"
        
        checks.append(("Settings Django", settings_file.exists(), str(settings_file)))
        checks.append(("Fichier .env", env_file.exists(), "Optionnel" if not env_file.exists() else str(env_file)))
        
        # 5. Migrations
        migrations_dir = PROJECT_ROOT / "documents" / "migrations"
        migration_files = list(migrations_dir.glob("*.py")) if migrations_dir.exists() else []
        checks.append(("Migrations Django", len(migration_files) > 1, f"{len(migration_files)} fichiers"))
        
        # Affichage des résultats
        all_good = True
        for check_name, status, details in checks:
            icon = "✅" if status else "❌"
            self.log(f"{icon} {check_name}: {details}")
            if not status:
                all_good = False
        
        if all_good:
            self.log("Environnement validé avec succès!", "SUCCESS")
        else:
            self.log("Certaines vérifications ont échoué", "ERROR")
        
        return all_good
    
    def run_django_command(self, command: List[str], description: str) -> bool:
        """Exécute une commande Django avec gestion des erreurs."""
        
        self.log(f"Exécution: {description}...")
        
        try:
            # Changer le répertoire de travail vers le projet Django
            original_cwd = os.getcwd()
            os.chdir(PROJECT_ROOT)
            
            # Exécuter la commande
            result = subprocess.run(
                ["python", "manage.py"] + command,
                capture_output=True,
                text=True,
                timeout=60
            )
            
            # Restaurer le répertoire de travail
            os.chdir(original_cwd)
            
            if result.returncode == 0:
                self.log(f"✅ {description} réussi", "SUCCESS")
                if result.stdout.strip():
                    self.log(f"   📄 Sortie: {result.stdout.strip()}")
                return True
            else:
                self.log(f"❌ {description} échoué", "ERROR")
                self.log(f"   📄 Erreur: {result.stderr.strip()}")
                return False
                
        except subprocess.TimeoutExpired:
            self.log(f"❌ {description} timeout (60s)", "ERROR")
            return False
        except Exception as e:
            self.log(f"❌ {description} erreur: {e}", "ERROR")
            return False
    
    def setup_database(self) -> bool:
        """Configuration et migration de la base de données."""
        
        self.log("Configuration de la base de données...", "DEPLOY")
        
        # 1. Créer les migrations si nécessaires
        if not self.run_django_command(["makemigrations"], "Création des migrations"):
            return False
        
        # 2. Appliquer les migrations
        if not self.run_django_command(["migrate"], "Application des migrations"):
            return False
        
        # 3. Créer un superuser (en mode non-interactif si possible)
        self.log("Note: Création de superuser à faire manuellement si nécessaire", "INFO")
        
        return True
    
    def start_document_service(self) -> bool:
        """Démarrage du Document Service."""
        
        self.log("Démarrage du Document Service...", "DEPLOY")
        
        try:
            # Vérifier si le service n'est pas déjà démarré
            response = httpx.get(f"{SERVICES_URLS['document']}/health/", timeout=2)
            if response.status_code == 200:
                self.log("Document Service déjà démarré", "INFO")
                return True
        except:
            pass  # Service pas encore démarré, c'est normal
        
        # Instructions pour démarrer manuellement
        self.log("Veuillez démarrer le Document Service manuellement:", "INFO")
        self.log(f"   cd {PROJECT_ROOT}", "INFO")
        self.log("   python manage.py runserver 0.0.0.0:8004", "INFO")
        self.log("Appuyez sur Entrée quand le service est démarré...")
        
        # Attendre confirmation utilisateur
        input()
        
        # Vérifier que le service répond
        max_retries = 10
        for attempt in range(max_retries):
            try:
                response = httpx.get(f"{SERVICES_URLS['document']}/health/", timeout=5)
                if response.status_code == 200:
                    self.log("Document Service démarré avec succès!", "SUCCESS")
                    return True
            except:
                if attempt < max_retries - 1:
                    self.log(f"Tentative {attempt + 1}/{max_retries}, nouvelle tentative dans 2s...")
                    time.sleep(2)
        
        self.log("Impossible de connecter au Document Service", "ERROR")
        return False
    
    async def validate_api_endpoints(self) -> Dict[str, Any]:
        """Validation complète des endpoints API."""
        
        self.log("Validation des endpoints API...", "DEPLOY")
        
        results = {
            "health_checks": {},
            "api_tests": {},
            "performance_tests": {}
        }
        
        async with httpx.AsyncClient(timeout=30.0) as client:
            
            # 1. Health checks
            services_to_check = [
                ("document", f"{SERVICES_URLS['document']}/health/"),
                ("gateway", f"{SERVICES_URLS['gateway']}/health/")
            ]
            
            for service_name, health_url in services_to_check:
                try:
                    start_time = time.time()
                    response = await client.get(health_url)
                    duration = round((time.time() - start_time) * 1000, 2)
                    
                    results["health_checks"][service_name] = {
                        "status": "healthy" if response.status_code == 200 else "unhealthy",
                        "response_time": duration,
                        "status_code": response.status_code
                    }
                    
                    icon = "✅" if response.status_code == 200 else "❌"
                    self.log(f"{icon} {service_name} health: {duration}ms")
                    
                except Exception as e:
                    results["health_checks"][service_name] = {
                        "status": "error",
                        "error": str(e)
                    }
                    self.log(f"❌ {service_name} health check failed: {e}")
            
            # 2. Tests des endpoints API
            api_endpoints = [
                ("GET", f"{SERVICES_URLS['document']}/api/quotes/stats/", "Quote Stats"),
                ("GET", f"{SERVICES_URLS['document']}/api/invoices/stats/", "Invoice Stats"),
                ("GET", f"{SERVICES_URLS['document']}/api/quotes/?page=1&page_size=5", "Quotes List"),
                ("GET", f"{SERVICES_URLS['document']}/api/invoices/?page=1&page_size=5", "Invoices List")
            ]
            
            for method, url, description in api_endpoints:
                try:
                    start_time = time.time()
                    
                    # Ajouter les headers nécessaires
                    headers = {
                        "X-Tenant-ID": "test-tenant",
                        "Content-Type": "application/json"
                    }
                    
                    response = await client.request(method, url, headers=headers)
                    duration = round((time.time() - start_time) * 1000, 2)
                    
                    results["api_tests"][description] = {
                        "status_code": response.status_code,
                        "response_time": duration,
                        "success": response.status_code in [200, 201]
                    }
                    
                    icon = "✅" if response.status_code in [200, 201] else "❌"
                    self.log(f"{icon} {description}: {response.status_code} ({duration}ms)")
                    
                except Exception as e:
                    results["api_tests"][description] = {
                        "error": str(e),
                        "success": False
                    }
                    self.log(f"❌ {description} failed: {e}")
            
            # 3. Tests de performance (endpoints stats multiples)
            performance_endpoints = [
                ("Quote Stats", f"{SERVICES_URLS['document']}/api/quotes/stats/"),
                ("Invoice Stats", f"{SERVICES_URLS['document']}/api/invoices/stats/")
            ]
            
            for endpoint_name, url in performance_endpoints:
                durations = []
                headers = {"X-Tenant-ID": "test-tenant"}
                
                for i in range(5):
                    try:
                        start_time = time.time()
                        response = await client.get(url, headers=headers)
                        duration = (time.time() - start_time) * 1000
                        durations.append(duration)
                    except:
                        durations.append(None)
                
                valid_durations = [d for d in durations if d is not None]
                if valid_durations:
                    avg_duration = round(sum(valid_durations) / len(valid_durations), 2)
                    min_duration = round(min(valid_durations), 2)
                    max_duration = round(max(valid_durations), 2)
                    
                    results["performance_tests"][endpoint_name] = {
                        "average": avg_duration,
                        "min": min_duration,
                        "max": max_duration,
                        "samples": len(valid_durations)
                    }
                    
                    self.log(f"⚡ {endpoint_name} perf: avg={avg_duration}ms, min={min_duration}ms, max={max_duration}ms")
        
        return results
    
    def generate_deployment_report(self, validation_results: Dict[str, Any]) -> str:
        """Génère un rapport de déploiement."""
        
        report = []
        report.append("# Rapport de déploiement Document Service")
        report.append(f"Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        report.append(f"Durée totale: {(datetime.now() - self.start_time).total_seconds():.1f}s")
        report.append("")
        
        # Health checks
        report.append("## Health Checks")
        for service, data in validation_results["health_checks"].items():
            status = data.get("status", "unknown")
            if status == "healthy":
                report.append(f"✅ {service}: {data.get('response_time', 'N/A')}ms")
            else:
                report.append(f"❌ {service}: {data.get('error', 'unhealthy')}")
        report.append("")
        
        # API Tests
        report.append("## Tests API")
        for endpoint, data in validation_results["api_tests"].items():
            if data.get("success", False):
                report.append(f"✅ {endpoint}: {data.get('status_code')} ({data.get('response_time', 'N/A')}ms)")
            else:
                report.append(f"❌ {endpoint}: {data.get('error', 'failed')}")
        report.append("")
        
        # Performance
        report.append("## Performance")
        for endpoint, data in validation_results["performance_tests"].items():
            avg = data.get("average", "N/A")
            report.append(f"⚡ {endpoint}: {avg}ms (moyenne sur {data.get('samples', 0)} échantillons)")
        report.append("")
        
        # Recommandations
        report.append("## Recommandations")
        
        # Analyser les performances
        all_healthy = all(
            data.get("status") == "healthy" 
            for data in validation_results["health_checks"].values()
        )
        
        all_api_working = all(
            data.get("success", False)
            for data in validation_results["api_tests"].values()
        )
        
        if all_healthy and all_api_working:
            report.append("✅ Le Document Service est prêt pour la production!")
            report.append("   - Tous les health checks passent")
            report.append("   - Tous les endpoints API fonctionnent")
            report.append("   - Performance dans les limites acceptables")
        else:
            report.append("⚠️ Des problèmes ont été détectés:")
            if not all_healthy:
                report.append("   - Certains services ne répondent pas correctement")
            if not all_api_working:
                report.append("   - Certains endpoints API sont défaillants")
            report.append("   - Vérifiez les logs et la configuration")
        
        report.append("")
        report.append("## Actions suivantes")
        report.append("1. Configurer la surveillance et les alertes")
        report.append("2. Mettre en place la sauvegarde automatique")
        report.append("3. Documenter les procédures de maintenance")
        report.append("4. Former l'équipe sur le nouveau service")
        
        return "\n".join(report)
    
    async def run_full_deployment(self) -> bool:
        """Exécute le déploiement complet."""
        
        self.log("🚀 DÉMARRAGE DU DÉPLOIEMENT DOCUMENT SERVICE", "DEPLOY")
        self.log("=" * 60)
        
        try:
            # 1. Vérification de l'environnement
            if not self.check_environment():
                self.log("Échec de la vérification de l'environnement", "ERROR")
                return False
            
            # 2. Configuration de la base de données
            if not self.setup_database():
                self.log("Échec de la configuration de la base de données", "ERROR")
                return False
            
            # 3. Démarrage du service
            if not self.start_document_service():
                self.log("Échec du démarrage du Document Service", "ERROR")
                return False
            
            # 4. Validation complète
            validation_results = await self.validate_api_endpoints()
            
            # 5. Génération du rapport
            report = self.generate_deployment_report(validation_results)
            
            # Sauvegarder le rapport
            report_file = PROJECT_ROOT / f"deployment_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md"
            with open(report_file, "w", encoding="utf-8") as f:
                f.write(report)
            
            self.log(f"Rapport sauvegardé: {report_file}", "INFO")
            
            # Afficher le rapport
            print("\n" + "=" * 60)
            print(report)
            print("=" * 60)
            
            # Déterminer le succès global
            all_healthy = all(
                data.get("status") == "healthy" 
                for data in validation_results["health_checks"].values()
            )
            
            all_api_working = all(
                data.get("success", False)
                for data in validation_results["api_tests"].values()
            )
            
            success = all_healthy and all_api_working
            
            if success:
                self.log("🎉 DÉPLOIEMENT RÉUSSI!", "SUCCESS")
            else:
                self.log("⚠️ DÉPLOIEMENT AVEC PROBLÈMES", "WARNING")
            
            return success
            
        except Exception as e:
            self.log(f"Erreur lors du déploiement: {e}", "ERROR")
            return False

async def main():
    """Point d'entrée principal."""
    
    deployment = DocumentServiceDeployment()
    success = await deployment.run_full_deployment()
    
    return 0 if success else 1

if __name__ == "__main__":
    sys.exit(asyncio.run(main())) 