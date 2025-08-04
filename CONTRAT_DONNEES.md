# Contrats de Données - Service Document

## Vue d'ensemble

Ce document définit les contrats de données pour le **service document-service**. Il garantit une intégration cohérente entre le backend et le frontend en spécifiant les structures exactes des données échangées.

**Version**: 1.0  
**Service**: document-service  
**Port**: 8004  
**Base URL**: `/api/v1/` (legacy: `/api/`)  

---

## 📋 Index des Contrats

### Gestion des Devis (`/quotes/`)
- [Quote](#quote) - Documents de devis
- [QuoteItem](#quoteitem) - Éléments de devis

### Gestion des Factures (`/invoices/`)
- [Invoice](#invoice) - Documents de facture
- [InvoiceItem](#invoiceitem) - Éléments de facture
- [Payment](#payment) - Paiements de factures

### Configuration (`/vat-rates/`, `/payment-terms/`, `/payment-methods/`)
- [VATRate](#vatrate) - Taux de TVA
- [PaymentTerm](#paymentterm) - Conditions de paiement
- [PaymentMethod](#paymentmethod) - Méthodes de paiement

### Services utilitaires
- [PDF Generation](#pdf-generation) - Génération de PDF
- [Health Check](#health-check) - Vérification de l'état du service

---

## 🧾 Contrats Gestion des Devis

### Quote
**Endpoint**: `GET/POST /api/v1/quotes/`

```json
{
  "id": "uuid",
  "number": "string (max: 50, readonly)",
  "status": "DRAFT | SENT | ACCEPTED | REJECTED | EXPIRED | CANCELLED",
  "status_display": "string (readonly)",
  "client_name": "string (max: 255)",
  "client_address": "string (optional)",
  "client_info": "object (readonly)",
  "project_name": "string (max: 255, optional)",
  "project_address": "string (optional)",
  "project_reference": "string (max: 100, optional)",
  "project_info": "object (readonly)",
  "issue_date": "date",
  "issue_date_formatted": "string (readonly)",
  "expiry_date": "date (optional)",
  "validity_period": "integer (default: 30)",
  "opportunity_id": "uuid (optional)",
  "margin": "decimal (5,2, default: 0.0)",
  "notes": "string (optional)",
  "terms_and_conditions": "string (optional)",
  "total_ht": "decimal (12,2, readonly)",
  "total_vat": "decimal (12,2, readonly)",
  "total_ttc": "decimal (12,2, readonly)",
  "items_count": "integer (readonly)",
  "vat_breakdown": "object (readonly)",
  "created_at": "datetime (readonly)",
  "updated_at": "datetime (readonly)",
  "created_by": "string (optional)",
  "updated_by": "string (optional)"
}
```

**Validation**:
- `client_name`: Requis, 1-255 caractères
- `status`: État du workflow du devis
- `validity_period`: Durée de validité en jours
- `margin`: Marge globale en pourcentage

**Champs calculés**:
- `number`: Généré automatiquement (format: DEV-YYYY-XXXXXX)
- `total_ht`, `total_vat`, `total_ttc`: Calculés à partir des items
- `items_count`: Nombre d'éléments dans le devis
- `vat_breakdown`: Détail des montants TVA par taux

**Actions spéciales**:
- `POST /quotes/{id}/send/`: Marquer comme envoyé
- `POST /quotes/{id}/accept/`: Marquer comme accepté
- `POST /quotes/{id}/reject/`: Marquer comme refusé
- `GET /quotes/{id}/pdf/`: Générer PDF

---

### QuoteItem
**Endpoint**: `GET/POST /api/v1/quote-items/`

```json
{
  "id": "uuid",
  "quote": "uuid (foreign key)",
  "type": "MATERIAL | LABOR | WORK | CHAPTER | SECTION | DISCOUNT",
  "type_display": "string (readonly)",
  "parent": "uuid (foreign key, optional)",
  "parent_info": "object (readonly)",
  "position": "integer (default: 0)",
  "reference": "string (max: 50, optional)",
  "designation": "string (max: 255)",
  "description": "string (optional)",
  "unit": "string (max: 20, optional)",
  "quantity": "decimal (10,2, default: 1)",
  "unit_price": "decimal (10,2, default: 0)",
  "discount": "decimal (5,2, default: 0)",
  "margin": "decimal (5,2, default: 0)",
  "vat_rate": "string (max: 10, default: '20')",
  "vat_rate_display": "string (readonly)",
  "total_ht": "decimal (12,2, readonly)",
  "total_ttc": "decimal (12,2, readonly)",
  "work_id": "string (max: 50, optional)",
  "children": "array (readonly)",
  "created_at": "datetime (readonly)",
  "updated_at": "datetime (readonly)"
}
```

**Validation**:
- `quote`: Requis, référence vers un devis
- `designation`: Requis, 1-255 caractères
- `quantity`: Quantité ≥ 0
- `unit_price`: Prix unitaire ≥ 0
- `discount`: Remise en pourcentage (0-100)
- `margin`: Marge spécifique à l'item

**Contrainte unique**: `(quote, position)` pour l'ordre d'affichage

**Champs calculés**:
- `total_ht`: `(unit_price * quantity) * (1 - discount/100)`
- `total_ttc`: `total_ht * (1 + vat_rate/100)`
- `children`: Éléments enfants pour structure hiérarchique

**Structure hiérarchique**:
- `CHAPTER` et `SECTION`: Éléments organisationnels
- `parent`: Référence vers élément parent pour arborescence

---

## 🧾 Contrats Gestion des Factures

### Invoice
**Endpoint**: `GET/POST /api/v1/invoices/`

```json
{
  "id": "uuid",
  "number": "string (max: 50, readonly)",
  "status": "DRAFT | SENT | OVERDUE | PARTIALLY_PAID | PAID | CANCELLED | CANCELLED_BY_CREDIT_NOTE",
  "status_display": "string (readonly)",
  "is_credit_note": "boolean (default: false)",
  "client_name": "string (max: 255)",
  "client_address": "string (optional)",
  "client_info": "object (readonly)",
  "project_name": "string (max: 255, optional)",
  "project_address": "string (optional)",
  "project_reference": "string (max: 100, optional)",
  "project_info": "object (readonly)",
  "issue_date": "date",
  "issue_date_formatted": "string (readonly)",
  "due_date": "date (optional)",
  "payment_terms": "integer (default: 30)",
  "quote_id": "uuid (optional)",
  "quote_number": "string (max: 50, optional)",
  "credit_note_id": "uuid (optional)",
  "original_invoice_id": "uuid (optional)",
  "paid_amount": "decimal (12,2, default: 0)",
  "remaining_amount": "decimal (12,2, default: 0)",
  "notes": "string (optional)",
  "terms_and_conditions": "string (optional)",
  "total_ht": "decimal (12,2, readonly)",
  "total_vat": "decimal (12,2, readonly)",
  "total_ttc": "decimal (12,2, readonly)",
  "items_count": "integer (readonly)",
  "vat_breakdown": "object (readonly)",
  "created_at": "datetime (readonly)",
  "updated_at": "datetime (readonly)",
  "created_by": "string (optional)",
  "updated_by": "string (optional)"
}
```

**Validation**:
- `client_name`: Requis, 1-255 caractères
- `payment_terms`: Délai de paiement en jours
- `paid_amount`: Montant déjà payé ≥ 0
- `remaining_amount`: Restant dû (calculé automatiquement)

**Champs calculés**:
- `number`: Généré automatiquement (format: FAC-YYYY-XXXXXX)
- `due_date`: `issue_date + payment_terms` jours
- `remaining_amount`: `total_ttc - paid_amount`
- `status`: Mis à jour selon les paiements

**Relations**:
- `quote_id`: Référence vers devis d'origine
- `credit_note_id`: Référence vers avoir associé
- `original_invoice_id`: Référence facture originale (pour avoirs)

**Actions spéciales**:
- `POST /invoices/{id}/send/`: Marquer comme émise
- `POST /invoices/{id}/payments/`: Enregistrer un paiement
- `GET /invoices/{id}/pdf/`: Générer PDF

---

### InvoiceItem
**Endpoint**: `GET/POST /api/v1/invoice-items/`

```json
{
  "id": "uuid",
  "invoice": "uuid (foreign key)",
  "type": "MATERIAL | LABOR | WORK | CHAPTER | SECTION | DISCOUNT | ADVANCE_PAYMENT",
  "type_display": "string (readonly)",
  "parent": "uuid (foreign key, optional)",
  "parent_info": "object (readonly)",
  "position": "integer (default: 0)",
  "reference": "string (max: 50, optional)",
  "designation": "string (max: 255)",
  "description": "string (optional)",
  "unit": "string (max: 20, optional)",
  "quantity": "decimal (10,2, default: 1)",
  "unit_price": "decimal (10,2, default: 0)",
  "discount": "decimal (5,2, default: 0)",
  "vat_rate": "string (max: 10, default: '20')",
  "vat_rate_display": "string (readonly)",
  "total_ht": "decimal (12,2, readonly)",
  "total_ttc": "decimal (12,2, readonly)",
  "work_id": "string (max: 50, optional)",
  "children": "array (readonly)",
  "created_at": "datetime (readonly)",
  "updated_at": "datetime (readonly)"
}
```

**Spécificités factures**:
- Type `ADVANCE_PAYMENT`: Pour les acomptes
- Pas de champ `margin` (spécifique aux devis)
- Calculs identiques aux éléments de devis

---

### Payment
**Endpoint**: `GET/POST /api/v1/payments/`

```json
{
  "id": "uuid",
  "invoice": "uuid (foreign key)",
  "date": "date",
  "amount": "decimal (12,2)",
  "method": "BANK_TRANSFER | CHECK | CASH | CARD | OTHER",
  "method_display": "string (readonly)",
  "reference": "string (max: 100, optional)",
  "notes": "string (optional)",
  "created_at": "datetime (readonly)"
}
```

**Validation**:
- `invoice`: Requis, référence vers facture
- `amount`: Requis, montant > 0
- `date`: Date du paiement
- `method`: Méthode de paiement requise

**Logique métier**:
- Met à jour automatiquement `paid_amount` et `remaining_amount` de la facture
- Modifie le statut de la facture selon le montant payé

---

## ⚙️ Contrats Configuration

### VATRate
**Endpoint**: `GET/POST /api/v1/vat-rates/`

```json
{
  "id": "string",
  "code": "string",
  "name": "string",
  "rate": "decimal (5,2)",
  "rate_display": "string",
  "description": "string (optional)",
  "is_default": "boolean",
  "is_active": "boolean"
}
```

**Notes**:
- Taux de TVA configurables par tenant
- Cache de 5 minutes pour optimiser les performances
- Fallback vers taux standards si service indisponible

---

### PaymentTerm
**Endpoint**: `GET/POST /api/v1/payment-terms/`

```json
{
  "id": "string",
  "name": "string",
  "days": "integer",
  "description": "string (optional)",
  "is_default": "boolean",
  "is_active": "boolean"
}
```

---

### PaymentMethod
**Endpoint**: `GET/POST /api/v1/payment-methods/`

```json
{
  "id": "string",
  "code": "string",
  "name": "string",
  "description": "string (optional)",
  "is_active": "boolean"
}
```

---

## 🔗 Relations et Dépendances

### Schéma relationnel
```
Quote ←--→ QuoteItem
  ↓           ↓
  └─→ Invoice ←--→ InvoiceItem
              ↓
            Payment

Quote/Invoice → VATRate (via tenant_id)
Quote/Invoice → PaymentTerm (via tenant_id)
Payment → PaymentMethod
```

### Workflow Documents
```
Quote: DRAFT → SENT → [ACCEPTED|REJECTED|EXPIRED|CANCELLED]
Invoice: DRAFT → SENT → [PARTIALLY_PAID → PAID|OVERDUE|CANCELLED]
```

### Intégrations externes
- **Tenant Service**: Configuration des taux TVA et conditions
- **CRM Service**: Informations clients (dénormalisées)
- **Library Service**: Références d'ouvrages (`work_id`)
- **Auth Service**: Utilisateurs (`created_by`, `updated_by`)

---

## ⚠️ Règles de Validation

### Format des UUIDs
Tous les `id` sont des UUID4 : `xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx`

### Contraintes métier
1. **Montants**: Tous les montants doivent être ≥ 0
2. **Dates**: `due_date` ≥ `issue_date`
3. **Paiements**: `paid_amount` ≤ `total_ttc`
4. **Statuts**: Transitions selon workflow défini
5. **Hiérarchie**: Pas de cycle dans `parent`

### États cohérents
- `total_*` recalculés automatiquement à chaque modification d'item
- `remaining_amount` mis à jour à chaque paiement
- `status` mis à jour selon état des paiements et dates

---

## 📝 Exemples d'utilisation

### Créer un devis
```http
POST /api/v1/quotes/
Content-Type: application/json

{
  "client_name": "SARL Martin",
  "client_address": "123 rue de la Paix, 75001 Paris",
  "project_name": "Rénovation bureau",
  "project_address": "456 avenue Victor Hugo, 75016 Paris",
  "validity_period": 45,
  "margin": 15.0,
  "notes": "Devis pour rénovation complète"
}
```

### Ajouter un élément au devis
```http
POST /api/v1/quote-items/
Content-Type: application/json

{
  "quote": "f47ac10b-58cc-4372-a567-0e02b2c3d479",
  "type": "material",
  "designation": "Peinture acrylique blanche",
  "quantity": "10.00",
  "unit": "L",
  "unit_price": "25.50",
  "vat_rate": "20",
  "position": 1
}
```

### Enregistrer un paiement
```http
POST /api/v1/payments/
Content-Type: application/json

{
  "invoice": "f47ac10b-58cc-4372-a567-0e02b2c3d480",
  "amount": "1500.00",
  "method": "bank_transfer",
  "date": "2025-08-04",
  "reference": "VIR-2025-001234",
  "notes": "Acompte 50%"
}
```

### Générer un PDF
```http
GET /api/v1/quotes/f47ac10b-58cc-4372-a567-0e02b2c3d479/pdf/
Accept: application/pdf
```

---

## 🎯 Points d'attention Frontend

### Gestion des états
- Les champs `readonly` ne doivent jamais être envoyés en POST/PUT
- Les totaux se recalculent automatiquement
- Les `*_display` sont pour l'affichage uniquement

### Format des dates
- **datetime**: ISO 8601 avec timezone (`2025-08-04T10:30:00Z`)
- **date**: Format ISO (`2025-08-04`)

### Pagination
Tous les endpoints de liste supportent la pagination DRF standard :
```json
{
  "count": 150,
  "next": "http://localhost:8004/api/v1/quotes/?page=2",
  "previous": null,
  "results": [...]
}
```

### Filtres disponibles
Utiliser les query params pour filtrer :
- `?status=draft`
- `?client_name=martin`
- `?issue_date__gte=2025-01-01`
- `?total_ttc__gte=1000`
- `?search=terme` (recherche full-text)
- `?ordering=-created_at`

### Structure hiérarchique des items
- Utiliser `parent` pour créer des arborescences
- `CHAPTER` et `SECTION` pour organiser les éléments
- `position` pour l'ordre d'affichage dans chaque niveau

### Optimisations performances
- Cache Redis pour les taux TVA (5 min TTL)
- Calculs batch lors de modifications multiples
- Index sur les champs de recherche fréquents

### Multi-tenant
- Isolation par schéma PostgreSQL automatique
- Configuration des taux TVA par tenant
- Pas de `tenant_id` dans les modèles (géré par middleware)

---

**Généré automatiquement à partir des modèles Django**  
**Date**: 2025-08-04  
**Équipe Backend**: Service Document