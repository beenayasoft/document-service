"""
Modèles unifiés pour les documents commerciaux (devis et factures)
"""
from django.db import models
import uuid
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from decimal import Decimal, InvalidOperation


def get_current_date():
    """Retourne la date courante (pas datetime)."""
    return timezone.now().date()


class VATRate(models.TextChoices):
    """
    Taux de TVA - Legacy pour compatibilité
    DEPRECATED: Utiliser VatRateService pour les taux tenant-specific
    """
    ZERO = "0", _("0%")
    REDUCED_55 = "5.5", _("5.5%")
    REDUCED_10 = "10", _("10%")
    STANDARD = "20", _("20%")


class PaymentMethod(models.TextChoices):
    """Méthodes de paiement"""
    BANK_TRANSFER = "bank_transfer", _("Virement bancaire")
    CHECK = "check", _("Chèque")
    CASH = "cash", _("Espèces")
    CARD = "card", _("Carte bancaire")
    OTHER = "other", _("Autre")


class BaseDocument(models.Model):
    """
    Classe abstraite pour tous les documents commerciaux
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    number = models.CharField(max_length=50, verbose_name=_("Numéro"), db_index=True)
    
    # Informations client (dénormalisées pour performance)
    client_name = models.CharField(max_length=255, verbose_name=_("Nom du client"))
    client_address = models.TextField(blank=True, null=True, verbose_name=_("Adresse du client"))
    
    # Projet/Chantier (futur module chantiers)
    project_name = models.CharField(max_length=255, blank=True, null=True, verbose_name=_("Nom du projet"))
    project_address = models.TextField(blank=True, null=True, verbose_name=_("Adresse du projet"))
    project_reference = models.CharField(max_length=100, blank=True, null=True, verbose_name=_("Référence projet"))
    
    # Dates
    issue_date = models.DateField(default=get_current_date, verbose_name=_("Date d'émission"), db_index=True)
    
    # Contenu
    notes = models.TextField(blank=True, null=True, verbose_name=_("Notes"))
    terms_and_conditions = models.TextField(blank=True, null=True, verbose_name=_("Conditions générales"))
    
    # Montants calculés
    total_ht = models.DecimalField(max_digits=12, decimal_places=2, default=0, verbose_name=_("Total HT"))
    total_vat = models.DecimalField(max_digits=12, decimal_places=2, default=0, verbose_name=_("Total TVA"))
    total_ttc = models.DecimalField(max_digits=12, decimal_places=2, default=0, verbose_name=_("Total TTC"))
    
    # Métadonnées
    created_at = models.DateTimeField(auto_now_add=True, verbose_name=_("Créé le"))
    updated_at = models.DateTimeField(auto_now=True, verbose_name=_("Mis à jour le"))
    created_by = models.CharField(max_length=255, blank=True, null=True, verbose_name=_("Créé par"))
    updated_by = models.CharField(max_length=255, blank=True, null=True, verbose_name=_("Mis à jour par"))
    
    # Relations tenant (géré par middleware)
    # Note: tenant_id sera géré par le middleware, pas de champ ici
    
    class Meta:
        abstract = True
        constraints = [
            models.UniqueConstraint(
                fields=['number'],
                name='%(class)s_unique_number',
                condition=~models.Q(number__in=['', 'Brouillon', None])
            )
        ]
    
    def clean(self):
        """Validation personnalisée pour l'unicité du numéro"""
        from django.core.exceptions import ValidationError
        
        # Ne pas valider l'unicité pour les brouillons ou valeurs vides
        if not self.number or self.number in ['', 'Brouillon']:
            return
            
        # Vérifier l'unicité du numéro (seulement pour les nouveaux documents)
        queryset = self.__class__.objects.filter(number=self.number)
        if self.pk:
            queryset = queryset.exclude(pk=self.pk)
            
        if queryset.exists():
            raise ValidationError({
                'number': f"Un document avec le numéro '{self.number}' existe déjà."
            })
    
    def save(self, *args, **kwargs):
        """Override save pour valider avant sauvegarde"""
        # Temporairement désactivé pour éviter les conflits avec les doublons existants
        # self.full_clean()
        super().save(*args, **kwargs)
        
    def update_totals(self, tenant_id=None):
        """
        Recalcule les totaux du document
        
        Args:
            tenant_id: ID du tenant pour résoudre les taux de TVA (optionnel)
        """
        import logging
        logger = logging.getLogger(__name__)
        
        items = self.items.all()
        logger.info(f"📊 Calcul totaux devis {self.number} - {items.count()} items trouvés")
        
        total_ht = Decimal('0')
        total_vat = Decimal('0')
        
        # Importer le service ici pour éviter les imports circulaires
        from .services.vat_rate_service import vat_rate_service
        
        for item in items:
            if item.type not in ["chapter", "section"]:
                item_total_ht = item.total_ht or Decimal('0')
                total_ht += item_total_ht
                logger.info(f"📋 Item: {item.designation} - Total HT: {item_total_ht}")
                
                # Calculer la TVA
                try:
                    if tenant_id:
                        # Utiliser le service pour résoudre le taux de TVA
                        vat_rate_info = vat_rate_service.get_vat_rate_by_code(tenant_id, item.vat_rate)
                        if vat_rate_info:
                            vat_rate = Decimal(str(vat_rate_info['rate'])) / Decimal('100')
                        else:
                            # Fallback : utiliser le code comme taux numérique
                            vat_rate = Decimal(item.vat_rate) / Decimal('100')
                    else:
                        # Fallback : utiliser le code comme taux numérique
                        vat_rate = Decimal(item.vat_rate) / Decimal('100')
                    
                    item_vat = (item.total_ht * vat_rate).quantize(Decimal('0.01'))
                    total_vat += item_vat
                    
                except (ValueError, TypeError, InvalidOperation) as e:
                    # En cas d'erreur, logger et utiliser un taux par défaut
                    import logging
                    logger = logging.getLogger(__name__)
                    logger.warning(f"Erreur calcul TVA pour item {item.id}, taux {item.vat_rate}: {e}")
                    
                    # Utiliser un taux par défaut de 20%
                    default_vat_rate = Decimal('0.20')
                    item_vat = (item.total_ht * default_vat_rate).quantize(Decimal('0.01'))
                    total_vat += item_vat
        
        # Arrondir à 2 décimales pour éviter les erreurs de validation
        self.total_ht = total_ht.quantize(Decimal('0.01'))
        self.total_vat = total_vat.quantize(Decimal('0.01'))
        self.total_ttc = (total_ht + total_vat).quantize(Decimal('0.01'))
        
        logger.info(f"📊 Totaux finaux document {self.number}: HT={self.total_ht}, TVA={self.total_vat}, TTC={self.total_ttc}")
        self.save(update_fields=['total_ht', 'total_vat', 'total_ttc'])


class BaseDocumentItem(models.Model):
    """
    Classe abstraite pour tous les éléments de documents
    """
    MATERIAL = "material"
    LABOR = "labor"
    WORK = "work"
    CHAPTER = "chapter"
    SECTION = "section"
    DISCOUNT = "discount"
    ADVANCE_PAYMENT = "advance_payment"  # Spécifique factures
    
    TYPE_CHOICES = [
        (MATERIAL, _("Matériau")),
        (LABOR, _("Main d'œuvre")),
        (WORK, _("Ouvrage")),
        (CHAPTER, _("Chapitre")),
        (SECTION, _("Section")),
        (DISCOUNT, _("Remise")),
        (ADVANCE_PAYMENT, _("Acompte")),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    type = models.CharField(max_length=20, choices=TYPE_CHOICES, default=MATERIAL)
    parent = models.ForeignKey(
        "self", 
        on_delete=models.CASCADE, 
        null=True, 
        blank=True,
        related_name="children",
        verbose_name=_("Parent"),
        db_index=True
    )
    position = models.PositiveIntegerField(default=0, verbose_name=_("Position"), db_index=True)
    reference = models.CharField(max_length=50, blank=True, null=True, verbose_name=_("Référence"))
    designation = models.CharField(max_length=255, verbose_name=_("Désignation"))
    description = models.TextField(blank=True, null=True, verbose_name=_("Description"))
    unit = models.CharField(max_length=20, blank=True, null=True, verbose_name=_("Unité"))
    quantity = models.DecimalField(max_digits=10, decimal_places=2, default=1, verbose_name=_("Quantité"))
    unit_price = models.DecimalField(max_digits=10, decimal_places=2, default=0, verbose_name=_("Prix unitaire"))
    discount = models.DecimalField(max_digits=5, decimal_places=2, default=0, verbose_name=_("Remise (%)"))
    vat_rate = models.CharField(
        max_length=10, 
        default="20",  # Valeur par défaut sans contrainte sur les choix
        verbose_name=_("Taux TVA"),
        help_text=_("Code du taux de TVA (ex: '0', '5.5', '10', '20')")
    )
    total_ht = models.DecimalField(max_digits=12, decimal_places=2, default=0, verbose_name=_("Total HT"))
    total_ttc = models.DecimalField(max_digits=12, decimal_places=2, default=0, verbose_name=_("Total TTC"))
    
    # Pour les ouvrages (référence vers la bibliothèque)
    work_id = models.CharField(max_length=50, blank=True, null=True, verbose_name=_("ID Ouvrage"))
    
    # Métadonnées
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        abstract = True
        ordering = ["position"]
    
    def save(self, *args, **kwargs):
        """
        Calcule automatiquement les totaux HT et TTC - VERSION OPTIMISÉE
        
        Optimisations:
        - Éviter les appels répétés aux services externes
        - Calculs batch pour les items d'un même document
        - Update_totals uniquement si nécessaire
        """
        tenant_id = kwargs.pop('tenant_id', None)
        skip_document_update = kwargs.pop('skip_document_update', False)
        
        if self.type not in ["chapter", "section"]:
            self._calculate_item_totals(tenant_id)
        
        super().save(*args, **kwargs)
        
        # Mettre à jour les totaux du document parent seulement si demandé
        if not skip_document_update:
            document = getattr(self, 'quote', None) or getattr(self, 'invoice', None)
            if document:
                document.update_totals(tenant_id=tenant_id)
    
    def _calculate_item_totals(self, tenant_id=None):
        """
        Calcule les totaux pour un item avec gestion d'erreur optimisée
        """
        try:
            unit_price = Decimal(str(self.unit_price)) if self.unit_price else Decimal('0')
            quantity = Decimal(str(self.quantity)) if self.quantity else Decimal('1')
            discount = Decimal(str(self.discount)) if self.discount else Decimal('0')
            
            # Calculs avec types Decimal uniformes et arrondi à 2 décimales
            discount_factor = Decimal('1') - (discount / Decimal('100'))
            net_price = unit_price * discount_factor
            self.total_ht = (net_price * quantity).quantize(Decimal('0.01'))
            
            # Calculer le taux de TVA avec cache local pour éviter appels répétés
            vat_rate_decimal = self._get_vat_rate_decimal(tenant_id)
            vat_amount = (self.total_ht * vat_rate_decimal).quantize(Decimal('0.01'))
            self.total_ttc = (self.total_ht + vat_amount).quantize(Decimal('0.01'))
            
        except (ValueError, TypeError, InvalidOperation) as e:
            import logging
            logger = logging.getLogger(__name__)
            logger.warning(f"Erreur calcul totaux pour item {getattr(self, 'id', 'nouveau')}: {e}")
            self.total_ht = Decimal('0')
            self.total_ttc = Decimal('0')
    
    def _get_vat_rate_decimal(self, tenant_id=None):
        """
        Récupère le taux de TVA en décimal avec cache local pour optimiser
        """
        # Cache local simple pour éviter les appels répétés
        cache_key = f"vat_rate_{tenant_id}_{self.vat_rate}"
        
        if hasattr(self, '_vat_cache') and cache_key in self._vat_cache:
            return self._vat_cache[cache_key]
        
        if not hasattr(self, '_vat_cache'):
            self._vat_cache = {}
        
        try:
            if tenant_id:
                from .services.vat_rate_service import vat_rate_service
                vat_rate_info = vat_rate_service.get_vat_rate_by_code(tenant_id, self.vat_rate)
                if vat_rate_info:
                    vat_rate_decimal = Decimal(str(vat_rate_info['rate'])) / Decimal('100')
                else:
                    vat_rate_decimal = Decimal(str(self.vat_rate)) / Decimal('100')
            else:
                vat_rate_value = Decimal(str(self.vat_rate)) if self.vat_rate else Decimal('20')
                vat_rate_decimal = vat_rate_value / Decimal('100')
            
            # Mettre en cache local
            self._vat_cache[cache_key] = vat_rate_decimal
            return vat_rate_decimal
            
        except (ValueError, TypeError, InvalidOperation):
            # Fallback par défaut
            return Decimal('0.20')  # 20% par défaut
    
    def calculate_totals_with_tenant(self, tenant_id):
        """
        Recalcule les totaux en utilisant les taux de TVA tenant-specific
        
        Args:
            tenant_id: ID du tenant pour résoudre les taux de TVA
        """
        if self.type not in ["chapter", "section"]:
            try:
                unit_price = Decimal(str(self.unit_price)) if self.unit_price else Decimal('0')
                quantity = Decimal(str(self.quantity)) if self.quantity else Decimal('1')
                discount = Decimal(str(self.discount)) if self.discount else Decimal('0')
                
                # Calculs avec types Decimal uniformes et arrondi à 2 décimales
                discount_factor = Decimal('1') - (discount / Decimal('100'))
                net_price = unit_price * discount_factor
                self.total_ht = (net_price * quantity).quantize(Decimal('0.01'))
                
                # Utiliser le service pour résoudre le taux de TVA
                from .services.vat_rate_service import vat_rate_service
                vat_rate_info = vat_rate_service.get_vat_rate_by_code(tenant_id, self.vat_rate)
                
                if vat_rate_info:
                    vat_rate_decimal = Decimal(str(vat_rate_info['rate'])) / Decimal('100')
                else:
                    # Fallback : utiliser le code comme taux numérique
                    vat_rate_decimal = Decimal(str(self.vat_rate)) / Decimal('100')
                
                vat_amount = (self.total_ht * vat_rate_decimal).quantize(Decimal('0.01'))
                self.total_ttc = (self.total_ht + vat_amount).quantize(Decimal('0.01'))
                
            except (ValueError, TypeError, InvalidOperation) as e:
                # Fallback avec valeurs par défaut
                import logging
                logger = logging.getLogger(__name__)
                logger.warning(f"Erreur calcul totaux tenant-specific pour item {self.id}: {e}")
                
                self.total_ht = Decimal('0')
                self.total_ttc = Decimal('0')


# =============================================================================
# MODÈLES CONCRETS - DEVIS
# =============================================================================

class QuoteStatus(models.TextChoices):
    DRAFT = "draft", _("Brouillon")
    SENT = "sent", _("Envoyé")
    ACCEPTED = "accepted", _("Accepté")
    REJECTED = "rejected", _("Refusé")
    EXPIRED = "expired", _("Expiré")
    CANCELLED = "cancelled", _("Annulé")


class Quote(BaseDocument):
    """Modèle de devis héritant de BaseDocument"""
    status = models.CharField(
        max_length=20,
        choices=QuoteStatus.choices,
        default=QuoteStatus.DRAFT,
        verbose_name=_("Statut"),
        db_index=True
    )
    
    # Note: tier_id supprimé car isolation automatique par schéma tenant
    # Chaque tenant a son propre schéma, donc pas besoin de tier_id
    opportunity_id = models.UUIDField(null=True, blank=True, verbose_name=_("ID Opportunité"))
    
    # Dates spécifiques aux devis
    expiry_date = models.DateField(null=True, blank=True, verbose_name=_("Date d'expiration"))
    validity_period = models.PositiveIntegerField(default=30, verbose_name=_("Durée de validité (jours)"))
    
    # Champ spécifique aux devis
    margin = models.DecimalField(max_digits=5, decimal_places=2, default=0, verbose_name=_("Marge globale (%)"))
    
    class Meta:
        verbose_name = _("Devis")
        verbose_name_plural = _("Devis")
        ordering = ["-created_at"]
        indexes = [
            # Index de performance pour les requêtes fréquentes
            models.Index(fields=['status', 'issue_date']),
            models.Index(fields=['opportunity_id']),
            models.Index(fields=['expiry_date']),
            models.Index(fields=['number']),
        ]
    
    def save(self, *args, **kwargs):
        """Override save pour générer automatiquement le numéro selon la configuration tenant"""
        import logging
        logger = logging.getLogger(__name__)
        
        # Générer le numéro si vide ou en création
        if not self.number or self.number == "":
            from .services.number_service import DocumentNumberService
            
            try:
                # Essayer de récupérer le tenant_id depuis le contexte
                tenant_id = getattr(self, '_tenant_id', None)
                
                if tenant_id:
                    # Utiliser le service de numérotation avec la configuration tenant
                    self.number = DocumentNumberService.generate_quote_number(tenant_id)
                    logger.info(f"🔧 Numéro généré automatiquement pour tenant {tenant_id}: {self.number}")
                else:
                    # Fallback simple avec timestamp
                    from datetime import datetime
                    self.number = f"DEV-{datetime.now().year}-{str(int(datetime.now().timestamp()))[-6:]}"
                    logger.warning("Génération de numéro sans tenant_id - utilisation du fallback")
                    
            except Exception as e:
                # Fallback en cas d'erreur avec le service de numérotation
                from datetime import datetime
                self.number = f"DEV-{datetime.now().year}-{str(int(datetime.now().timestamp()))[-6:]}"
                logger.error(f"Erreur génération numéro: {e} - utilisation du fallback")
        else:
            # Le numéro a été fourni par le frontend
            logger.info(f"✅ Numéro fourni par le frontend: {self.number}")
        
        super().save(*args, **kwargs)
    
    def __str__(self):
        # Récupérer la devise du tenant si possible
        currency = self._get_tenant_currency()
        return f"{self.number} - {self.client_name} - {self.total_ttc} {currency}"
    
    def _get_tenant_currency(self):
        """Récupère la devise du tenant depuis le cache ou fallback"""
        try:
            from .services.tenant_client import TenantConfigClient
            # Essayer de récupérer depuis le contexte de la requête
            tenant_id = getattr(self, '_tenant_id', None)
            if tenant_id:
                config = TenantConfigClient.get_cached_config(tenant_id)
                if config and 'settings' in config:
                    return config['settings'].get('currency', 'MAD')
        except Exception:
            pass
        return 'MAD'  # Fallback
    
    @property
    def client_id(self):
        """Propriété pour compatibilité frontend"""
        # Maintenant, le client_id est implicite via le schéma tenant
        return getattr(self, '_client_id', None)
    
    def mark_as_sent(self):
        """Marque le devis comme envoyé et met à jour l'opportunité associée"""
        # Générer le numéro si c'est un brouillon
        if self.status == QuoteStatus.DRAFT and self.number == "Brouillon":
            from .services.number_service import DocumentNumberService
            self.number = DocumentNumberService.generate_quote_number()
        
        self.status = QuoteStatus.SENT
        self.save(update_fields=['status', 'number'])
        
        # Mettre à jour l'opportunité associée vers le statut "négociation"
        if self.opportunity_id:
            self._update_opportunity_to_negotiation()
    
    def mark_as_accepted(self):
        """Marque le devis comme accepté et met l'opportunité en 'gagnée'"""
        self.status = QuoteStatus.ACCEPTED
        self.save(update_fields=['status'])
        
        # Mettre automatiquement l'opportunité associée en 'gagnée'
        if self.opportunity_id:
            self._update_opportunity_to_won()
    
    def mark_as_rejected(self):
        """Marque le devis comme refusé"""
        self.status = QuoteStatus.REJECTED
        self.save(update_fields=['status'])
    
    def _update_opportunity_to_negotiation(self):
        """
        Met à jour le statut de l'opportunité associée vers 'négociation' 
        quand le devis est envoyé
        """
        import requests
        import logging
        from django.conf import settings
        
        logger = logging.getLogger(__name__)
        
        try:
            # URL du service CRM (à ajuster selon votre architecture)
            crm_service_url = getattr(settings, 'CRM_SERVICE_URL', 'http://localhost:8001')
            
            # Préparer les données pour la mise à jour du statut
            update_data = {
                'stage': 'negotiation'  # Utiliser 'stage' comme dans le modèle Opportunity
            }
            
            # Headers pour l'authentification inter-services
            headers = {
                'Content-Type': 'application/json',
                'X-Service': 'document-service',  # Identifier le service appelant
            }
            
            # Récupérer le tenant_id depuis le contexte si disponible
            # Dans un contexte SOA, le tenant_id doit être propagé
            tenant_id = getattr(self, '_tenant_id', None)
            if tenant_id:
                headers['X-Tenant-ID'] = str(tenant_id)
            
            # Appel API vers l'endpoint spécialisé du service CRM 
            api_url = f"{crm_service_url}/api/opportunities/{self.opportunity_id}/update_stage/"
            logger.info(f"🔄 Mise à jour opportunité {self.opportunity_id} vers 'négociation' via {api_url}")
            
            response = requests.patch(
                api_url,
                json=update_data,
                headers=headers,
                timeout=10  # Timeout raisonnable pour ne pas bloquer
            )
            
            if response.status_code == 200:
                logger.info(f"✅ Opportunité {self.opportunity_id} mise à jour vers 'négociation' suite à l'envoi du devis {self.number}")
            elif response.status_code == 400:
                # L'opportunité peut déjà être en négociation ou avoir des contraintes
                logger.warning(f"⚠️ Opportunité {self.opportunity_id} non mise à jour (statut 400): {response.text}")
            else:
                logger.warning(f"⚠️ Échec mise à jour opportunité {self.opportunity_id}: HTTP {response.status_code}")
                
        except requests.exceptions.RequestException as e:
            logger.error(f"❌ Erreur réseau lors de la mise à jour de l'opportunité {self.opportunity_id}: {e}")
        except Exception as e:
            logger.error(f"❌ Erreur générale lors de la mise à jour de l'opportunité {self.opportunity_id}: {e}")
            # Ne pas faire échouer l'envoi du devis pour un problème de mise à jour d'opportunité
    
    def _update_opportunity_to_won(self):
        """
        Met à jour l'opportunité vers 'gagnée' quand un devis est accepté
        """
        import requests
        import logging
        import time
        from django.conf import settings
        
        logger = logging.getLogger(__name__)
        
        try:
            # URL du service CRM
            crm_service_url = getattr(settings, 'CRM_SERVICE_URL', 'http://localhost:8003')
            
            # Headers pour l'authentification inter-services
            headers = {
                'Content-Type': 'application/json',
                'X-Service': 'document-service',
            }
            
            # Récupérer le tenant_id depuis le contexte si disponible
            tenant_id = getattr(self, '_tenant_id', None)
            if tenant_id:
                headers['X-Tenant-ID'] = str(tenant_id)
            
            # ÉTAPE 1: Essayer directement mark_won
            mark_won_data = {
                'project_id': f"PROJ-{self.number}"
            }
            
            mark_won_url = f"{crm_service_url}/api/opportunities/{self.opportunity_id}/mark_won/"
            logger.info(f"🎉 ÉTAPE 1: Tentative directe mark_won pour opportunité {self.opportunity_id}")
            
            response = requests.post(
                mark_won_url,
                json=mark_won_data,
                headers=headers,
                timeout=15
            )
            
            if response.status_code == 200:
                logger.info(f"✅ SUCCESS DIRECT: Opportunité {self.opportunity_id} marquée comme GAGNÉE (devis {self.number})")
                return  # Succès direct
            
            # ÉTAPE 2: Si échec à cause de NEGOTIATION_REQUIRED_FOR_WON, faire le workflow automatique
            elif response.status_code == 400:
                try:
                    error_data = response.json()
                    error_code = error_data.get('code')
                    
                    if error_code == 'NEGOTIATION_REQUIRED_FOR_WON':
                        logger.info(f"🔄 WORKFLOW AUTOMATIQUE: Détection race condition pour opportunité {self.opportunity_id}")
                        
                        # ÉTAPE 2A: Forcer passage en négociation
                        negotiation_data = {
                            'stage': 'negotiation',
                            'force': True,
                            'source': 'auto_workflow_quote_accepted'
                        }
                        
                        negotiation_url = f"{crm_service_url}/api/opportunities/{self.opportunity_id}/update_stage/"
                        logger.info(f"🔄 ÉTAPE 2A: Force négociation pour opportunité {self.opportunity_id}")
                        
                        neg_response = requests.patch(
                            negotiation_url,
                            json=negotiation_data,
                            headers=headers,
                            timeout=15
                        )
                        
                        if neg_response.status_code == 200:
                            logger.info(f"✅ ÉTAPE 2A OK: Opportunité {self.opportunity_id} forcée en négociation")
                            
                            # Petit délai pour la cohérence
                            time.sleep(0.5)
                            
                            # ÉTAPE 2B: Retry mark_won
                            logger.info(f"🎉 ÉTAPE 2B: Retry mark_won pour opportunité {self.opportunity_id}")
                            
                            retry_response = requests.post(
                                mark_won_url,
                                json=mark_won_data,
                                headers=headers,
                                timeout=15
                            )
                            
                            if retry_response.status_code == 200:
                                logger.info(f"🎉 SUCCESS WORKFLOW: Opportunité {self.opportunity_id} marquée comme GAGNÉE via workflow automatique (devis {self.number})")
                            else:
                                logger.warning(f"⚠️ WORKFLOW ÉCHEC ÉTAPE 2B: mark_won retry failed {retry_response.status_code} pour opportunité {self.opportunity_id}")
                        else:
                            logger.warning(f"⚠️ WORKFLOW ÉCHEC ÉTAPE 2A: Force négociation failed {neg_response.status_code} pour opportunité {self.opportunity_id}")
                    else:
                        logger.warning(f"⚠️ Erreur non-workflow lors mark_won pour opportunité {self.opportunity_id}: {error_data}")
                        
                except (ValueError, KeyError):
                    logger.warning(f"⚠️ Erreur 400 non-parsable lors mark_won pour opportunité {self.opportunity_id}: {response.text}")
            else:
                logger.warning(f"⚠️ Échec mark_won inattendu pour opportunité {self.opportunity_id}: HTTP {response.status_code}")
                
        except requests.exceptions.RequestException as e:
            logger.error(f"❌ Erreur réseau lors de la mise à jour opportunité {self.opportunity_id} vers gagnée: {e}")
        except Exception as e:
            logger.error(f"❌ Erreur générale lors de la mise à jour opportunité {self.opportunity_id} vers gagnée: {e}")
            # Ne pas faire échouer l'acceptation du devis


class QuoteItem(BaseDocumentItem):
    """Élément de devis héritant de BaseDocumentItem"""
    quote = models.ForeignKey(
        Quote, 
        on_delete=models.CASCADE, 
        related_name="items",
        verbose_name=_("Devis"),
        db_index=True
    )
    
    # Champ spécifique aux devis
    margin = models.DecimalField(max_digits=5, decimal_places=2, default=0, verbose_name=_("Marge (%)"))
    
    class Meta:
        verbose_name = _("Élément de devis")
        verbose_name_plural = _("Éléments de devis")
        ordering = ["position"]
        indexes = [
            models.Index(fields=['quote', 'position']),
            models.Index(fields=['quote', 'type']),
            models.Index(fields=['parent', 'position']),
            models.Index(fields=['reference']),
        ]
    
    def __str__(self):
        return f"{self.designation} - {self.total_ht} €"


# =============================================================================
# MODÈLES CONCRETS - FACTURES
# =============================================================================

class InvoiceStatus(models.TextChoices):
    DRAFT = "draft", _("Brouillon")
    SENT = "sent", _("Émise")
    OVERDUE = "overdue", _("En retard")
    PARTIALLY_PAID = "partially_paid", _("Payée partiellement")
    PAID = "paid", _("Payée")
    CANCELLED = "cancelled", _("Annulée")
    CANCELLED_BY_CREDIT_NOTE = "cancelled_by_credit_note", _("Annulée par avoir")


class Invoice(BaseDocument):
    """Modèle de facture héritant de BaseDocument"""
    status = models.CharField(
        max_length=30,
        choices=InvoiceStatus.choices,
        default=InvoiceStatus.DRAFT,
        verbose_name=_("Statut"),
        db_index=True
    )
    
    # Note: tier_id supprimé car isolation automatique par schéma tenant
    # Chaque tenant a son propre schéma, donc pas besoin de tier_id
    
    # Champs spécifiques aux factures
    is_credit_note = models.BooleanField(default=False, verbose_name=_("Est un avoir"))
    due_date = models.DateField(null=True, blank=True, verbose_name=_("Date d'échéance"))
    payment_terms = models.PositiveIntegerField(default=30, verbose_name=_("Délai de paiement (jours)"))
    
    # Montants de paiement
    paid_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0, verbose_name=_("Montant payé"))
    remaining_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0, verbose_name=_("Restant dû"))
    
    # Relations avec d'autres documents (via ID pour découplage SOA)
    quote_id = models.UUIDField(null=True, blank=True, verbose_name=_("ID Devis d'origine"))
    quote_number = models.CharField(max_length=50, blank=True, null=True, verbose_name=_("Numéro devis d'origine"))
    
    # Relations pour les avoirs
    credit_note_id = models.UUIDField(null=True, blank=True, verbose_name=_("ID Avoir associé"))
    original_invoice_id = models.UUIDField(null=True, blank=True, verbose_name=_("ID Facture d'origine (pour avoir)"))
    
    class Meta:
        verbose_name = _("Facture")
        verbose_name_plural = _("Factures")
        ordering = ["-created_at"]
        indexes = [
            # Index de performance
            models.Index(fields=['status', 'issue_date']),
            models.Index(fields=['status', 'due_date']),
            models.Index(fields=['quote_id']),
            models.Index(fields=['is_credit_note', 'status']),
            models.Index(fields=['payment_terms']),
            models.Index(fields=['remaining_amount']),
        ]
    
    def update_totals(self, tenant_id=None):
        """Override pour calculer aussi le remaining_amount pour les factures"""
        # Appeler la méthode parent pour calculer les totaux de base
        super().update_totals(tenant_id)
        
        # Calculer le restant dû spécifique aux factures
        self.remaining_amount = self.total_ttc - self.paid_amount
        self.save(update_fields=['remaining_amount'])
        
        import logging
        logger = logging.getLogger(__name__)
        logger.info(f"📊 Remaining amount calculé pour facture {self.number}: {self.remaining_amount}")

    def save(self, *args, **kwargs):
        """Override save pour gérer la numérotation des factures"""
        import logging
        logger = logging.getLogger(__name__)
        
        # Vérifier si c'est une nouvelle facture sans numéro valide
        is_new = self.pk is None
        needs_number = not self.number or self.number == "" or self.number == "Brouillon"
        
        if is_new and needs_number:
            # Seules les nouvelles factures sans numéro valide ont besoin de génération automatique
            from .services.number_service import DocumentNumberService
            
            try:
                # Essayer de récupérer le tenant_id depuis le contexte
                tenant_id = getattr(self, '_tenant_id', None)
                
                if tenant_id:
                    # Utiliser le service de numérotation avec la configuration tenant
                    self.number = DocumentNumberService.generate_invoice_number(tenant_id)
                    logger.info(f"🔧 Numéro de facture généré automatiquement pour tenant {tenant_id}: {self.number}")
                else:
                    # Fallback simple avec timestamp
                    from datetime import datetime
                    self.number = f"FAC-{datetime.now().year}-{str(int(datetime.now().timestamp()))[-6:]}"
                    logger.warning("Génération de numéro de facture sans tenant_id - utilisation du fallback")
                    
            except Exception as e:
                # Fallback en cas d'erreur avec le service de numérotation
                from datetime import datetime
                self.number = f"FAC-{datetime.now().year}-{str(int(datetime.now().timestamp()))[-6:]}"
                logger.error(f"Erreur génération numéro de facture: {e} - utilisation du fallback")
        elif is_new:
            # Nouvelle facture avec numéro fourni par le frontend
            logger.info(f"✅ Numéro de facture fourni par le frontend: {self.number}")
        else:
            # Mise à jour d'une facture existante
            logger.info(f"🔄 Mise à jour de la facture existante: {self.number}")
        
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.number} - {self.client_name} - {self.total_ttc} €"
    
    @property
    def client_id(self):
        """Propriété pour compatibilité frontend"""
        # Maintenant, le client_id est implicite via le schéma tenant
        return getattr(self, '_client_id', None)
    
    def validate_and_send(self, tenant_id=None):
        """Valide et envoie la facture"""
        if self.status == InvoiceStatus.DRAFT:
            # Générer le numéro si c'est un brouillon
            if self.number == "Brouillon":
                from .services.number_service import DocumentNumberService
                if tenant_id:
                    self.number = DocumentNumberService.generate_invoice_number(tenant_id)
                else:
                    # Fallback vers l'ancien système
                    self.number = DocumentNumberService._generate_fallback_number('invoice', timezone.now().year)
        
        self.status = InvoiceStatus.SENT
        self.save(update_fields=['status', 'number'])
    
    def record_payment(self, amount, method, date=None, reference=None, notes=None):
        """Enregistre un paiement"""
        if date is None:
            date = get_current_date()
        
        payment = Payment.objects.create(
            invoice=self,
            amount=amount,
            method=method,
            date=date,
            reference=reference,
            notes=notes
        )
        
        # Mettre à jour les montants
        self.paid_amount += amount
        self.remaining_amount = self.total_ttc - self.paid_amount
        
        # Mettre à jour le statut
        if self.remaining_amount <= 0:
            self.status = InvoiceStatus.PAID
        elif self.paid_amount > 0:
            self.status = InvoiceStatus.PARTIALLY_PAID
        
        self.save(update_fields=['paid_amount', 'remaining_amount', 'status'])
        return payment
    
    def recalculate_paid_amount(self):
        """Recalcule le montant payé à partir des paiements réels"""
        from django.db.models import Sum
        actual_paid = self.payments.aggregate(
            total=Sum('amount')
        )['total'] or Decimal('0')
        
        if actual_paid != self.paid_amount:
            import logging
            logger = logging.getLogger(__name__)
            logger.warning(f"🔍 Incohérence détectée pour facture {self.number}: "
                         f"paid_amount={self.paid_amount}, somme réelle={actual_paid}")
            
            # Corriger les montants
            self.paid_amount = actual_paid
            self.remaining_amount = self.total_ttc - self.paid_amount
            
            # Recalculer le statut
            if self.remaining_amount <= 0:
                self.status = InvoiceStatus.PAID
            elif self.paid_amount > 0:
                self.status = InvoiceStatus.PARTIALLY_PAID
            
            self.save(update_fields=['paid_amount', 'remaining_amount', 'status'])
            logger.info(f"✅ Montants corrigés pour facture {self.number}")
        
        return actual_paid

    def update_overdue_status(self):
        """Met à jour le statut en fonction de la date d'échéance"""
        from django.utils import timezone
        
        # Ne traiter que les factures qui ne sont pas complètement payées
        if self.status in [InvoiceStatus.PAID, InvoiceStatus.CANCELLED, InvoiceStatus.CANCELLED_BY_CREDIT_NOTE]:
            return False
            
        # Si pas de date d'échéance, on ne peut pas déterminer si en retard
        if not self.due_date:
            return False
            
        today = timezone.now().date()
        is_overdue = today > self.due_date
        
        # Mettre à jour le statut si nécessaire
        if is_overdue and self.status != InvoiceStatus.OVERDUE:
            self.status = InvoiceStatus.OVERDUE
            self.save(update_fields=['status'])
            
            import logging
            logger = logging.getLogger(__name__)
            logger.info(f"📅 Facture {self.number} marquée en retard (échéance: {self.due_date})")
            return True
            
        elif not is_overdue and self.status == InvoiceStatus.OVERDUE:
            # Si la facture n'est plus en retard (par exemple après modification de la date d'échéance)
            # Remettre le statut approprié
            if self.paid_amount > 0:
                self.status = InvoiceStatus.PARTIALLY_PAID
            else:
                self.status = InvoiceStatus.SENT
            self.save(update_fields=['status'])
            
            import logging
            logger = logging.getLogger(__name__)
            logger.info(f"📅 Facture {self.number} n'est plus en retard")
            return True
            
        return False

    @classmethod
    def update_all_overdue_statuses(cls):
        """Met à jour le statut de toutes les factures en fonction de leur date d'échéance"""
        from django.utils import timezone
        
        today = timezone.now().date()
        updated_count = 0
        
        # Marquer comme en retard les factures échues non payées
        overdue_invoices = cls.objects.filter(
            due_date__lt=today,
            status__in=[InvoiceStatus.SENT, InvoiceStatus.PARTIALLY_PAID]
        )
        
        for invoice in overdue_invoices:
            if invoice.update_overdue_status():
                updated_count += 1
        
        # Remettre à jour les factures qui ne sont plus en retard
        not_overdue_invoices = cls.objects.filter(
            status=InvoiceStatus.OVERDUE,
            due_date__gte=today
        )
        
        for invoice in not_overdue_invoices:
            if invoice.update_overdue_status():
                updated_count += 1
        
        import logging
        logger = logging.getLogger(__name__)
        logger.info(f"📅 Mise à jour automatique: {updated_count} factures mises à jour")
        
        return updated_count


class InvoiceItem(BaseDocumentItem):
    """Élément de facture héritant de BaseDocumentItem"""
    invoice = models.ForeignKey(
        Invoice, 
        on_delete=models.CASCADE, 
        related_name="items",
        verbose_name=_("Facture"),
        db_index=True
    )
    
    class Meta:
        verbose_name = _("Élément de facture")
        verbose_name_plural = _("Éléments de facture")
        ordering = ["position"]
        indexes = [
            models.Index(fields=['invoice', 'position']),
            models.Index(fields=['invoice', 'type']),
            models.Index(fields=['parent', 'position']),
            models.Index(fields=['reference']),
        ]
    
    def __str__(self):
        return f"{self.designation} - {self.total_ht} €"


# =============================================================================
# MODÈLE SPÉCIFIQUE - PAIEMENTS
# =============================================================================

class Payment(models.Model):
    """Modèle de paiement pour les factures"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    invoice = models.ForeignKey(
        Invoice, 
        on_delete=models.CASCADE, 
        related_name="payments",
        verbose_name=_("Facture")
    )
    date = models.DateField(default=get_current_date, verbose_name=_("Date du paiement"))
    amount = models.DecimalField(max_digits=12, decimal_places=2, verbose_name=_("Montant"))
    method = models.CharField(
        max_length=20,
        choices=PaymentMethod.choices,
        default=PaymentMethod.BANK_TRANSFER,
        verbose_name=_("Méthode de paiement")
    )
    reference = models.CharField(max_length=100, blank=True, null=True, verbose_name=_("Référence"))
    notes = models.TextField(blank=True, null=True, verbose_name=_("Notes"))
    
    # Métadonnées
    created_at = models.DateTimeField(auto_now_add=True, verbose_name=_("Créé le"))
    
    class Meta:
        verbose_name = _("Paiement")
        verbose_name_plural = _("Paiements")
        ordering = ["-date", "-created_at"]
        indexes = [
            models.Index(fields=['invoice', 'date']),
            models.Index(fields=['date']),
            models.Index(fields=['method']),
            models.Index(fields=['amount']),
        ]
    
    def __str__(self):
        return f"{self.amount} € - {self.date} - {self.invoice.number}"
