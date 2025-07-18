#!/usr/bin/env python
"""
Script de lancement des tests pour le document-service.

Usage:
    python run_tests.py                    # Tous les tests
    python run_tests.py --fast             # Tests rapides seulement
    python run_tests.py --performance      # Tests de performance seulement
    python run_tests.py --integration      # Tests d'intégration seulement
    python run_tests.py --coverage         # Avec rapport de couverture
    python run_tests.py --verbose          # Mode verbeux
"""

import os
import sys
import time
import subprocess
import argparse
from pathlib import Path

# Ajouter le projet au PYTHONPATH
project_dir = Path(__file__).parent
sys.path.insert(0, str(project_dir))

# Configuration Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'document_service.settings')

import django
from django.conf import settings
from django.test.utils import get_runner
from django.core.management import execute_from_command_line


class TestRunner:
    """Gestionnaire d'exécution des tests."""
    
    def __init__(self):
        self.start_time = None
        self.results = {}
        
    def setup_environment(self):
        """Configure l'environnement de test."""
        django.setup()
        
        # Configuration spécifique aux tests
        if not hasattr(settings, 'TESTING'):
            settings.TESTING = True
        
        # Base de données en mémoire pour les tests
        settings.DATABASES['default'] = {
            'ENGINE': 'django.db.backends.sqlite3',
            'NAME': ':memory:',
        }
        
        # Cache en mémoire pour les tests
        settings.CACHES = {
            'default': {
                'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
            }
        }
        
        print("✓ Environnement de test configuré")
    
    def run_test_suite(self, test_labels=None, verbosity=2, keepdb=False, **kwargs):
        """Lance une suite de tests."""
        TestRunnerClass = get_runner(settings)
        test_runner = TestRunnerClass(
            verbosity=verbosity,
            interactive=False,
            keepdb=keepdb,
            **kwargs
        )
        
        self.start_time = time.time()
        failures = test_runner.run_tests(test_labels or [])
        execution_time = time.time() - self.start_time
        
        return {
            'failures': failures,
            'execution_time': execution_time,
            'success': failures == 0
        }
    
    def run_models_tests(self, verbosity=1):
        """Lance les tests des modèles."""
        print("\n🧪 Tests des modèles...")
        return self.run_test_suite(['documents.tests.test_models'], verbosity=verbosity)
    
    def run_serializers_tests(self, verbosity=1):
        """Lance les tests des serializers."""
        print("\n🔄 Tests des serializers...")
        return self.run_test_suite(['documents.tests.test_serializers'], verbosity=verbosity)
    
    def run_views_tests(self, verbosity=1):
        """Lance les tests des vues/API."""
        print("\n🌐 Tests des vues/API...")
        return self.run_test_suite(['documents.tests.test_views'], verbosity=verbosity)
    
    def run_services_tests(self, verbosity=1):
        """Lance les tests des services."""
        print("\n⚙️ Tests des services...")
        return self.run_test_suite(['documents.tests.test_services'], verbosity=verbosity)
    
    def run_integration_tests(self, verbosity=1):
        """Lance les tests d'intégration."""
        print("\n🔗 Tests d'intégration...")
        return self.run_test_suite(['documents.tests.test_integration'], verbosity=verbosity)
    
    def run_performance_tests(self, verbosity=1):
        """Lance les tests de performance."""
        print("\n⚡ Tests de performance...")
        return self.run_test_suite(['documents.tests.test_performance'], verbosity=verbosity)
    
    def run_all_tests(self, verbosity=1):
        """Lance tous les tests."""
        print("\n🚀 Lancement de tous les tests...")
        return self.run_test_suite(['documents.tests'], verbosity=verbosity)
    
    def run_fast_tests(self, verbosity=1):
        """Lance les tests rapides (pas de performance ni d'intégration)."""
        print("\n⚡ Tests rapides...")
        test_labels = [
            'documents.tests.test_models',
            'documents.tests.test_serializers',
            'documents.tests.test_views',
            'documents.tests.test_services'
        ]
        return self.run_test_suite(test_labels, verbosity=verbosity)
    
    def run_with_coverage(self, test_labels=None, verbosity=1):
        """Lance les tests avec rapport de couverture."""
        try:
            import coverage
        except ImportError:
            print("❌ Coverage non installé. Installez avec: pip install coverage")
            return {'success': False, 'failures': 1, 'execution_time': 0}
        
        print("\n📊 Tests avec couverture de code...")
        
        # Initialiser coverage
        cov = coverage.Coverage(source=['documents'])
        cov.start()
        
        try:
            result = self.run_test_suite(test_labels, verbosity=verbosity)
            
            # Arrêter et générer le rapport
            cov.stop()
            cov.save()
            
            print("\n📈 Rapport de couverture:")
            cov.report()
            
            # Générer rapport HTML
            html_dir = project_dir / 'htmlcov'
            cov.html_report(directory=str(html_dir))
            print(f"📄 Rapport HTML généré dans: {html_dir}")
            
            return result
            
        except Exception as e:
            print(f"❌ Erreur lors de l'exécution avec coverage: {e}")
            return {'success': False, 'failures': 1, 'execution_time': 0}
    
    def check_migrations(self):
        """Vérifie les migrations."""
        print("\n🔄 Vérification des migrations...")
        try:
            execute_from_command_line(['manage.py', 'makemigrations', '--check', '--dry-run'])
            print("✓ Migrations à jour")
            return True
        except SystemExit as e:
            if e.code != 0:
                print("❌ Migrations manquantes détectées")
                return False
            return True
    
    def run_linting(self):
        """Lance les vérifications de code."""
        print("\n🔍 Vérifications de code...")
        
        checks = []
        
        # Flake8
        try:
            result = subprocess.run(['flake8', 'documents/'], capture_output=True, text=True)
            if result.returncode == 0:
                checks.append(("Flake8", True, ""))
            else:
                checks.append(("Flake8", False, result.stdout))
        except FileNotFoundError:
            checks.append(("Flake8", None, "Non installé"))
        
        # Black
        try:
            result = subprocess.run(['black', '--check', 'documents/'], capture_output=True, text=True)
            if result.returncode == 0:
                checks.append(("Black", True, ""))
            else:
                checks.append(("Black", False, result.stdout))
        except FileNotFoundError:
            checks.append(("Black", None, "Non installé"))
        
        # isort
        try:
            result = subprocess.run(['isort', '--check', 'documents/'], capture_output=True, text=True)
            if result.returncode == 0:
                checks.append(("isort", True, ""))
            else:
                checks.append(("isort", False, result.stdout))
        except FileNotFoundError:
            checks.append(("isort", None, "Non installé"))
        
        # Afficher les résultats
        for tool, status, output in checks:
            if status is True:
                print(f"✓ {tool}")
            elif status is False:
                print(f"❌ {tool}")
                if output:
                    print(f"   {output[:200]}...")
            else:
                print(f"⚠️ {tool} (non installé)")
        
        return all(status is not False for _, status, _ in checks)
    
    def print_summary(self, results):
        """Affiche le résumé des résultats."""
        print("\n" + "="*60)
        print("📊 RÉSUMÉ DES TESTS")
        print("="*60)
        
        total_time = 0
        total_failures = 0
        passed_suites = 0
        
        for suite_name, result in results.items():
            total_time += result.get('execution_time', 0)
            total_failures += result.get('failures', 0)
            
            if result.get('success', False):
                status = "✅ SUCCÈS"
                passed_suites += 1
            else:
                status = "❌ ÉCHEC"
            
            print(f"{suite_name:20} {status:10} ({result.get('execution_time', 0):.2f}s)")
        
        print("-"*60)
        print(f"Suites réussies: {passed_suites}/{len(results)}")
        print(f"Échecs totaux:   {total_failures}")
        print(f"Temps total:     {total_time:.2f}s")
        
        if total_failures == 0:
            print("\n🎉 TOUS LES TESTS SONT PASSÉS!")
            return True
        else:
            print(f"\n💥 {total_failures} test(s) ont échoué")
            return False


def main():
    """Point d'entrée principal."""
    parser = argparse.ArgumentParser(description='Lance les tests du document-service')
    parser.add_argument('--fast', action='store_true', help='Tests rapides seulement')
    parser.add_argument('--performance', action='store_true', help='Tests de performance')
    parser.add_argument('--integration', action='store_true', help='Tests d\'intégration')
    parser.add_argument('--coverage', action='store_true', help='Avec couverture de code')
    parser.add_argument('--verbose', '-v', action='store_true', help='Mode verbeux')
    parser.add_argument('--lint', action='store_true', help='Vérifications de code')
    parser.add_argument('--check-migrations', action='store_true', help='Vérifier les migrations')
    parser.add_argument('--suite', choices=['models', 'serializers', 'views', 'services'], 
                       help='Suite spécifique à lancer')
    
    args = parser.parse_args()
    
    runner = TestRunner()
    results = {}
    
    print("🧪 Document Service - Suite de Tests")
    print("="*50)
    
    try:
        # Configuration
        runner.setup_environment()
        
        # Vérifications préliminaires
        if args.check_migrations or not any([args.fast, args.performance, args.integration, args.suite]):
            if not runner.check_migrations():
                print("❌ Migrations en attente. Lancez 'python manage.py makemigrations' d'abord.")
                return 1
        
        if args.lint:
            if not runner.run_linting():
                print("⚠️ Problèmes de style détectés")
        
        verbosity = 2 if args.verbose else 1
        
        # Sélection des tests à lancer
        if args.suite:
            suite_methods = {
                'models': runner.run_models_tests,
                'serializers': runner.run_serializers_tests,
                'views': runner.run_views_tests,
                'services': runner.run_services_tests,
            }
            results[args.suite] = suite_methods[args.suite](verbosity)
            
        elif args.fast:
            results['fast'] = runner.run_fast_tests(verbosity)
            
        elif args.performance:
            results['performance'] = runner.run_performance_tests(verbosity)
            
        elif args.integration:
            results['integration'] = runner.run_integration_tests(verbosity)
            
        elif args.coverage:
            results['all_with_coverage'] = runner.run_with_coverage(verbosity=verbosity)
            
        else:
            # Suite complète
            results['models'] = runner.run_models_tests(verbosity)
            results['serializers'] = runner.run_serializers_tests(verbosity)
            results['views'] = runner.run_views_tests(verbosity)
            results['services'] = runner.run_services_tests(verbosity)
            results['integration'] = runner.run_integration_tests(verbosity)
            
            if not args.verbose:  # Éviter les tests de performance en mode normal
                print("\n⚠️ Tests de performance ignorés (utilisez --performance pour les lancer)")
        
        # Afficher le résumé
        success = runner.print_summary(results)
        return 0 if success else 1
        
    except KeyboardInterrupt:
        print("\n\n⏹️ Tests interrompus par l'utilisateur")
        return 1
    except Exception as e:
        print(f"\n❌ Erreur inattendue: {e}")
        return 1


if __name__ == '__main__':
    sys.exit(main()) 