# Document Service

Service unifié pour la gestion des documents commerciaux (devis et factures) dans l'architecture SOA de Beenaya.

## 🎯 Objectif

Centraliser et unifier la logique métier des documents commerciaux pour :
- Éviter la duplication de code entre devis et factures
- Optimiser les performances avec cache Redis intégré
- Assurer la cohérence des données et calculs
- Faciliter l'évolution et la maintenance

## 🏗️ Architecture

### Documents gérés
- **Devis** (`Quote`) : Documents commerciaux de proposition avec workflow complet
- **Factures** (`Invoice`) : Documents de facturation avec gestion des paiements
- **Éléments** (`QuoteItem`, `InvoiceItem`) : Lignes avec hiérarchie (chapitres/sections)
- **Paiements** (`Payment`) : Suivi des règlements et échéances

### Multi-tenancy
- **Stratégie** : Schémas PostgreSQL séparés par tenant via `X-Tenant-ID`
- **Isolation** : Données complètement isolées entre tenants
- **Performance** : Index optimisés et cache tenant-aware

### Services métier intégrés
- **CalculationService** : Calculs financiers précis (HT/TTC, remises, TVA)
- **WorkflowService** : Gestion des transitions d'état et validations
- **NumberService** : Numérotation automatique configurable
- **PDFService** : Génération de documents avec templates

## 📦 Structure réelle du Service

```
document-service/
├── document_service/              # Configuration Django
│   ├── __init__.py
│   ├── settings.py               # Configuration multi-tenant + cache
│   ├── urls.py                   # Routage principal
│   ├── wsgi.py
│   └── asgi.py
├── documents/                     # App principale unifiée
│   ├── models.py                 # Modèles unifiés (458 lignes)
│   ├── serializers.py            # Serializers avec mixins (490 lignes)
│   ├── mixins.py                 # Mixins réutilisables (278 lignes)
│   ├── views.py                  # ViewSets unifiés (544 lignes)
│   ├── viewset_mixins.py         # Mixins pour ViewSets (383 lignes)
│   ├── pagination.py             # Pagination optimisée
│   ├── middleware.py             # Middleware multi-tenant (300 lignes)
│   ├── routers.py                # Router pour schémas
│   ├── services/                 # Services métier
│   │   ├── __init__.py
│   │   ├── calculation_service.py # Calculs financiers
│   │   ├── workflow_service.py    # Workflow documents
│   │   ├── number_service.py      # Numérotation
│   │   └── pdf_service.py         # Génération PDF
│   ├── tests/                    # Suite de tests complète
│   │   ├── __init__.py
│   │   ├── fixtures.py           # Fixtures multi-tenant
│   │   ├── test_models.py        # Tests modèles (459 lignes)
│   │   ├── test_serializers.py   # Tests serializers (591 lignes)
│   │   ├── test_views.py         # Tests API (581 lignes)
│   │   ├── test_services.py      # Tests services (563 lignes)
│   │   ├── test_integration.py   # Tests intégration (561 lignes)
│   │   └── test_performance.py   # Tests performance (507 lignes)
│   ├── migrations/
│   │   ├── __init__.py
│   │   └── 0001_initial.py       # Migration unifiée (878 lignes)
│   ├── admin.py
│   ├── apps.py
│   └── urls.py
├── config.env.example            # Configuration d'environnement
├── requirements.txt              # Dépendances Python
├── manage.py                     # Point d'entrée Django
├── setup_initial_data.py         # Script d'initialisation
├── run_tests.py                  # Runner de tests avec couverture
├── deploy_and_validate.py        # Script de déploiement
├── logs/                         # Fichiers de logs
│   └── document.log
└── media/                        # Fichiers générés (PDF, exports)
```

## 🔌 API Endpoints réels

### Devis (Quotes)
```
GET    /api/quotes/                    # Liste paginée avec filtres
POST   /api/quotes/                    # Créer un devis
GET    /api/quotes/{id}/               # Détail complet
PUT    /api/quotes/{id}/               # Modifier
DELETE /api/quotes/{id}/               # Supprimer
GET    /api/quotes/stats/              # Statistiques (cached)

# Actions métier
POST   /api/quotes/{id}/send/          # Marquer comme envoyé
POST   /api/quotes/{id}/validate/      # Valider le devis
POST   /api/quotes/{id}/convert_to_invoice/  # Convertir en facture
POST   /api/quotes/{id}/duplicate/     # Dupliquer
POST   /api/quotes/{id}/pdf/           # Générer PDF
POST   /api/quotes/{id}/export/        # Export (PDF/Excel/CSV)

# Gestion des éléments
GET    /api/quotes/{id}/items/         # Éléments du devis
POST   /api/quotes/{id}/items/         # Ajouter élément
PUT    /api/quotes/{id}/items/{item_id}/   # Modifier élément
DELETE /api/quotes/{id}/items/{item_id}/   # Supprimer élément
POST   /api/quotes/{id}/items/reorder/     # Réorganiser
POST   /api/quotes/{id}/items/bulk_operations/  # Opérations en lot
```

### Factures (Invoices)
```
GET    /api/invoices/                  # Liste paginée avec filtres
POST   /api/invoices/                  # Créer une facture
GET    /api/invoices/{id}/             # Détail complet
PUT    /api/invoices/{id}/             # Modifier
DELETE /api/invoices/{id}/             # Supprimer
GET    /api/invoices/stats/            # Statistiques (cached)

# Actions métier
POST   /api/invoices/{id}/validate/    # Valider la facture
POST   /api/invoices/{id}/record_payment/     # Enregistrer paiement
POST   /api/invoices/{id}/create_credit_note/ # Créer avoir
POST   /api/invoices/{id}/pdf/         # Générer PDF
POST   /api/invoices/{id}/export/      # Export

# Gestion des éléments et paiements
GET    /api/invoices/{id}/items/       # Éléments de la facture
POST   /api/invoices/{id}/items/       # Ajouter élément
GET    /api/invoices/{id}/payments/    # Liste des paiements
POST   /api/invoices/{id}/payments/    # Enregistrer paiement
```

### Santé et monitoring
```
GET    /health/                       # Health check du service
GET    /api/schema/                   # Documentation OpenAPI
```

## 🛠️ Technologies utilisées

- **Framework** : Django 5.0 + Django REST Framework
- **Base de données** : PostgreSQL avec schémas multiples
- **Cache** : Redis avec TTL intelligent (30s)
- **Queue** : Celery ready (pour génération PDF asynchrone)
- **Documentation** : drf-spectacular (OpenAPI)
- **Tests** : Django TestCase + fixtures multi-tenant
- **Monitoring** : Logs structurés avec niveaux

## 🚀 Installation et démarrage

### 1. Installation des dépendances
```bash
cd soa/services/document-service
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Configuration
```bash
# Copier et adapter la configuration
cp config.env.example config.env
# Éditer config.env avec vos paramètres
```

### 3. Base de données
```bash
# Appliquer les migrations
python manage.py migrate

# Initialiser les données de base (optionnel)
python setup_initial_data.py
```

### 4. Démarrage
```bash
# Démarrage du serveur
python manage.py runserver 0.0.0.0:8004

# Ou avec le script de déploiement complet
python deploy_and_validate.py
```

## 🔧 Configuration d'environnement

### Variables requises (config.env)
```bash
# Base de données
DB_NAME=beenaya_documents
DB_USER=postgres
DB_PASSWORD=your_password
DB_HOST=localhost
DB_PORT=5432

# Cache Redis
REDIS_URL=redis://localhost:6379/1

# Django
SECRET_KEY=your-secret-key-change-in-production
DEBUG=True
ALLOWED_HOSTS=localhost,127.0.0.1,document-service

# API
API_HOST=0.0.0.0
API_PORT=8004
```

## 🧪 Tests et qualité

### Exécution des tests
```bash
# Tests complets avec couverture
python run_tests.py

# Tests spécifiques
python manage.py test documents.tests.test_models
python manage.py test documents.tests.test_integration
```

### Métriques de qualité
- **Couverture** : >90% (objectif)
- **Tests** : 50+ tests unitaires et d'intégration
- **Performance** : <200ms pour endpoints stats
- **Cache hit ratio** : >80% sur endpoints fréquents

## 📊 Performance et monitoring

### Cache Redis intégré
- **TTL** : 30 secondes sur endpoints stats
- **Clés intelligentes** : Hash des paramètres pour cache granulaire
- **Headers** : `X-Cache-Status` pour monitoring
- **Invalidation** : Automatique lors des modifications

### Index de performance
- **Modèles** : 20+ index créés automatiquement
- **Requêtes** : Optimisées avec `select_related` et `prefetch_related`
- **Aggregation** : Stats calculées en une seule requête SQL

### Logs structurés
```bash
# Logs en temps réel
tail -f logs/document.log

# Niveaux disponibles : DEBUG, INFO, WARNING, ERROR
```

## 🔄 Workflow métier

### Cycle de vie d'un devis
1. **Création** → `draft`
2. **Validation** → `sent` (+ génération PDF)
3. **Réponse client** → `accepted` | `rejected`
4. **Conversion** → Création facture liée
5. **Archivage** → `expired` (automatique)

### Cycle de vie d'une facture
1. **Création** → `draft` (depuis devis ou directe)
2. **Validation** → `sent` (+ génération PDF)
3. **Paiements** → `partially_paid` → `paid`
4. **Relances** → `overdue` (calcul automatique)
5. **Avoir** → `cancelled_by_credit_note`

## 🛡️ Sécurité et isolation

- **Multi-tenant** : Isolation complète par schémas PostgreSQL
- **Authentification** : JWT via API Gateway
- **Autorisation** : Permissions par ViewSet
- **Headers requis** : `X-Tenant-ID` obligatoire
- **Validation** : Serializers DRF + validateurs métier
- **Audit** : Logs des modifications avec user tracking

## 🔗 Intégration SOA

### API Gateway
- **Routage** : `/api/devis/*` → `/api/quotes/*`
- **Routage** : `/api/factures/*` → `/api/invoices/*`
- **Compatibilité** : Frontend inchangé grâce au mapping

### Services externes
- **CRM Service** : Récupération infos tiers/opportunités
- **Auth Service** : Validation JWT et permissions
- **Tenant Service** : Gestion des schémas multi-tenant

## 🚀 Déploiement production

### Script automatisé
```bash
# Déploiement complet avec validation
python deploy_and_validate.py
```

### Docker (futur)
```bash
# Build et démarrage
docker-compose up -d document-service
```

### Monitoring recommandé
- Health checks réguliers (`/health/`)
- Surveillance des logs d'erreur
- Métriques de performance Redis
- Alertes sur temps de réponse

---

## 📋 TODOs et améliorations à implémenter

### 🔴 TODOs critiques (à faire en priorité)

#### Dans `documents/models.py`
- **Ligne 361** : `# TODO: Implémenter la génération de numéro`
  - Actuellement, la génération automatique de numéros n'est pas implémentée dans le modèle
  - Nécessaire pour la production

#### Dans `documents/services/workflow_service.py`
- **Ligne 166** : `# TODO: Déclencher la création automatique d'un projet si configuré`
  - Intégration avec le service de gestion de projets
- **Ligne 167** : `# TODO: Déclencher la conversion prospect -> client si nécessaire`
  - Logique métier pour automatiser la conversion des prospects

#### Dans `documents/mixins.py`
- **Ligne 173** : `TODO: Implémenter l'appel API vers le service CRM`
  - Récupération des informations tiers depuis le CRM Service
- **Ligne 191** : `# TODO: Appel API vers le service documents pour récupérer le devis`
  - Auto-référence pour les relations entre documents
- **Ligne 202** : `# TODO: Appel API interne pour récupérer la facture`
  - Récupération facture liée pour les avoirs

### 🟡 TODOs moyens (améliorations)

#### Dans `documents/viewset_mixins.py`
- **Ligne 345** : `# TODO: Implémenter les générateurs de PDF/Excel`
  - Export avancé en multiple formats

#### Dans `documents/services/pdf_service.py`
- **Ligne 106** : `# TODO: Récupérer depuis les paramètres ou configuration`
  - Configuration dynamique des templates PDF

### 🟢 TODOs mineurs (nice to have)

#### Dans `deploy_and_validate.py`
- **Ligne 166** : Automatiser la création de superuser
  - Amélioration du processus de déploiement

### 📊 État d'avancement des TODOs

| Priorité | Nombre | Status | Impact |
|----------|--------|--------|---------|
| 🔴 Critique | 5 | À faire | Production bloquante |
| 🟡 Moyen | 2 | Nice to have | Fonctionnalité avancée |
| 🟢 Mineur | 1 | Optionnel | Confort développeur |

### 🎯 Plan d'action recommandé

#### Phase 1 (Immédiat - 1-2 jours)
1. Implémenter la génération automatique de numéros
2. Finaliser les appels API vers CRM Service

#### Phase 2 (Court terme - 1 semaine)
3. Automatisation workflow (projet/conversion prospect)
4. Export avancé PDF/Excel

#### Phase 3 (Moyen terme - 1 mois)
5. Amélioration processus déploiement
6. Configuration dynamique templates

---

## 🏆 Statut actuel

✅ **Service fonctionnel** : API complète, tests passants, intégration Gateway  
⚠️ **TODOs critiques** : 5 éléments à implémenter pour la production  
🚀 **Ready for staging** : Peut être déployé pour tests utilisateurs  

Le Document Service est architecturalement solide et prêt pour l'usage, avec quelques TODOs à finaliser pour une version production complète. 