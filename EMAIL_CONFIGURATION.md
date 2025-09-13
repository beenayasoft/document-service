# Configuration d'Envoi d'Emails avec Brevo

Ce guide détaille la configuration et l'utilisation du système d'envoi d'emails pour les devis et factures avec Brevo (ex-Sendinblue).

## 📋 Table des matières

1. [Configuration Brevo](#configuration-brevo)
2. [Configuration Railway](#configuration-railway) 
3. [Configuration Django](#configuration-django)
4. [Test de la configuration](#test-de-la-configuration)
5. [Utilisation](#utilisation)
6. [Templates d'emails](#templates-demails)
7. [Logs et débogage](#logs-et-débogage)
8. [Dépannage](#dépannage)

## 🚀 Configuration Brevo

### 1. Créer un compte Brevo

1. Aller sur [brevo.com](https://brevo.com)
2. Créer un compte gratuit (300 emails/jour)
3. Confirmer l'email de verification

### 2. Obtenir les clés API

1. Se connecter au dashboard Brevo
2. Aller dans **Settings** > **SMTP & API**
3. Dans l'onglet **SMTP**, noter :
   - **SMTP Server**: `smtp-relay.brevo.com`
   - **Port**: `587`
   - **Login**: Votre email de connexion
   - **SMTP Key**: Cliquer sur "Generate a new SMTP key"

⚠️ **Important** : Garder précieusement la clé SMTP, elle ne s'affiche qu'une fois !

## 🚂 Configuration Railway

### Variables d'environnement à définir

Connectez-vous à Railway et ajoutez ces variables dans votre service Document :

```bash
# Variables Brevo
BREVO_EMAIL=votre-email@domain.com
BREVO_PASSWORD=xsmtpsib-votre-cle-smtp-ici
DEFAULT_FROM_EMAIL=votre-email@domain.com
```

### Commandes Railway CLI

```bash
# Se connecter à Railway
railway login

# Aller dans le bon projet
railway environment

# Ajouter les variables
railway variables set BREVO_EMAIL=votre-email@domain.com
railway variables set BREVO_PASSWORD=xsmtpsib-votre-cle-smtp
railway variables set DEFAULT_FROM_EMAIL=votre-email@domain.com

# Vérifier les variables
railway variables
```

## ⚙️ Configuration Django

La configuration a déjà été ajoutée dans `settings.py` :

```python
# Configuration Email avec Brevo (Sendinblue)
EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'
EMAIL_HOST = 'smtp-relay.brevo.com'
EMAIL_PORT = 587
EMAIL_USE_TLS = True
EMAIL_HOST_USER = config('BREVO_EMAIL', default='')
EMAIL_HOST_PASSWORD = config('BREVO_PASSWORD', default='')
DEFAULT_FROM_EMAIL = config('DEFAULT_FROM_EMAIL', default=EMAIL_HOST_USER)
SERVER_EMAIL = DEFAULT_FROM_EMAIL

# Configuration pour les emails en développement (optionnel)
if DEBUG and not EMAIL_HOST_USER:
    # En développement, utiliser la console si Brevo n'est pas configuré
    EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'
```

## 🧪 Test de la configuration

### 1. Test via Django Shell

```python
# Se connecter au conteneur Railway
railway shell

# Lancer le shell Django
python manage.py shell

# Tester la configuration
from documents.services.email_service import EmailService
result = EmailService.test_email_configuration()
print(result)
```

### 2. Test d'envoi réel

```python
from django.core.mail import send_mail

send_mail(
    'Test Beenaya',
    'Test de configuration email',
    'votre-email@domain.com',  # From
    ['destinataire@test.com'], # To
    fail_silently=False,
)
```

## 📧 Utilisation

### API Endpoint pour envoyer un devis

**POST** `/api/quotes/{id}/send/`

**Payload JSON :**
```json
{
  "recipientEmail": "client@example.com",
  "message": "Voici votre devis personnalisé..."
}
```

**Réponse de succès :**
```json
{
  "message": "Document envoyé avec succès à client@example.com",
  "status": "sent", 
  "recipient": "client@example.com"
}
```

### Frontend (TypeScript/React)

```typescript
// Dans votre service quotes API
const sendQuote = async (quoteId: string, emailData: {
  recipientEmail: string;
  message?: string;
}) => {
  const response = await api.post(`/quotes/${quoteId}/send/`, emailData);
  return response.data;
};

// Utilisation dans un composant
const handleSendQuote = async () => {
  try {
    const result = await quotesApi.sendQuote(quote.id, {
      recipientEmail: 'client@example.com',
      message: 'Voici votre devis...'
    });
    
    toast.success(result.message);
  } catch (error) {
    toast.error('Erreur lors de l\'envoi');
  }
};
```

## 🎨 Templates d'emails

Les templates se trouvent dans `documents/templates/emails/` :

### Template devis (`quote_send.html`)
- **Sujet** : "Devis {numero} - {nom_client}"
- **Contenu** : Détails du devis avec design responsive
- **Variables disponibles** : `quote`, `custom_message`, `tenant_id`

### Template facture (`invoice_send.html`)
- **Sujet** : "Facture {numero} - {nom_client}"
- **Contenu** : Détails de la facture avec informations de paiement
- **Variables disponibles** : `invoice`, `custom_message`, `tenant_id`

### Personnalisation

Pour personnaliser les templates :

1. Modifier le fichier HTML dans `documents/templates/emails/`
2. Redéployer sur Railway
3. Tester l'envoi

## 📊 Logs et débogage

### Logs d'envoi

Les logs sont automatiquement générés :

```python
# Logs de succès
logger.info(f"Email envoyé avec succès pour le devis {quote.number} à {recipient_email}")

# Logs d'erreur
logger.error(f"Échec d'envoi email pour le devis {quote.number}: {error_message}")
```

### Consulter les logs Railway

```bash
# Voir les logs en temps réel
railway logs --follow

# Filtrer les logs email
railway logs | grep -i email
```

### Dashboard Brevo

- Connectez-vous à [app.brevo.com](https://app.brevo.com)
- Allez dans **Statistics** > **Email**
- Consultez les statistiques d'envoi, ouvertures, clics

## 🔧 Dépannage

### Erreur : "SMTPAuthenticationError"

```
SMTPAuthenticationError: (535, b'5.7.1 Invalid login or password')
```

**Solutions :**
1. Vérifier que `BREVO_EMAIL` correspond à l'email du compte
2. Vérifier que `BREVO_PASSWORD` est bien la clé SMTP (commence par `xsmtpsib-`)
3. Régénérer une nouvelle clé SMTP dans Brevo

### Erreur : "Connection refused"

```
ConnectionRefusedError: [Errno 111] Connection refused
```

**Solutions :**
1. Vérifier la connectivité réseau depuis Railway
2. Tester avec `telnet smtp-relay.brevo.com 587`
3. Vérifier les paramètres de firewall

### Emails en spam

**Solutions :**
1. Configurer l'authentification SPF/DKIM dans Brevo
2. Utiliser un domaine personnalisé vérifié
3. Améliorer le contenu des emails (éviter mots-spam)
4. Utiliser une adresse expéditeur cohérente

### Mode développement

En développement, si Brevo n'est pas configuré, les emails s'affichent dans la console :

```bash
# Lancer le serveur de développement
python manage.py runserver

# Les emails apparaissent dans les logs console au lieu d'être envoyés
```

## 📈 Limites et tarifs Brevo

### Plan gratuit
- **300 emails/jour**
- **Illimité en contacts**
- **Templates inclus**
- **Support email**

### Plans payants
- **Lite** : €25/mois pour 20 000 emails
- **Premium** : €65/mois pour 20 000 emails + fonctionnalités avancées
- **Enterprise** : Sur devis

### Conseils d'optimisation
1. **Grouper les envois** : Éviter d'envoyer 1 par 1
2. **Templates réutilisables** : Utiliser les templates Brevo
3. **Segmentation** : Cibler les bons destinataires
4. **Timing** : Envoyer aux heures ouvrables

## 🔒 Sécurité

### Bonnes pratiques
1. **Variables d'environnement** : Ne jamais committer les clés
2. **Rotation des clés** : Changer régulièrement les clés SMTP
3. **Logs sensibles** : Ne pas logger les emails complets
4. **Validation** : Toujours valider les emails destinataires
5. **Rate limiting** : Implémenter des limites d'envoi

### Exemple de validation

```python
import re
from django.core.validators import validate_email
from django.core.exceptions import ValidationError

def validate_recipient_email(email):
    """Validation robuste des emails"""
    try:
        validate_email(email)
        
        # Vérifications supplémentaires
        if email.count('@') != 1:
            raise ValidationError("Format email invalide")
            
        domain = email.split('@')[1]
        if domain in ['example.com', 'test.com']:
            raise ValidationError("Domaine de test non autorisé")
            
        return email.lower().strip()
    except ValidationError:
        raise ValidationError("Adresse email invalide")
```

## ✅ Checklist de déploiement

- [ ] Compte Brevo créé et vérifié
- [ ] Clés SMTP générées 
- [ ] Variables Railway configurées
- [ ] Configuration Django vérifiée
- [ ] Test d'envoi réussi
- [ ] Templates personnalisés (optionnel)
- [ ] Logs configurés
- [ ] Documentation équipe mise à jour

---

**Support** : Pour toute question, consultez la [documentation Brevo](https://help.brevo.com/) ou les logs Railway.

**Dernière mise à jour** : Janvier 2025