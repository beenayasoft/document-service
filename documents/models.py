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
        
    def update_totals(self, tenant_id=None):
        """
        Recalcule les totaux du document
        
        Args:
            tenant_id: ID du tenant pour résoudre les taux de TVA (optionnel)
        """
        items = self.items.all()
        
        total_ht = Decimal('0')
        total_vat = Decimal('0')
        
        # Importer le service ici pour éviter les imports circulaires
        from .services.vat_rate_service import vat_rate_service
        
        for item in items:
            if item.type not in ["chapter", "section"]:
                total_ht += item.total_ht or Decimal('0')
                
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
                    
                    item_vat = item.total_ht * vat_rate
                    total_vat += item_vat
                    
                except (ValueError, TypeError, InvalidOperation) as e:
                    # En cas d'erreur, logger et utiliser un taux par défaut
                    import logging
                    logger = logging.getLogger(__name__)
                    logger.warning(f"Erreur calcul TVA pour item {item.id}, taux {item.vat_rate}: {e}")
                    
                    # Utiliser un taux par défaut de 20%
                    default_vat_rate = Decimal('0.20')
                    item_vat = item.total_ht * default_vat_rate
                    total_vat += item_vat
        
        self.total_ht = total_ht
        self.total_vat = total_vat
        self.total_ttc = total_ht + total_vat
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
            
            # Calculs avec types Decimal uniformes
            discount_factor = Decimal('1') - (discount / Decimal('100'))
            net_price = unit_price * discount_factor
            self.total_ht = net_price * quantity
            
            # Calculer le taux de TVA avec cache local pour éviter appels répétés
            vat_rate_decimal = self._get_vat_rate_decimal(tenant_id)
            vat_amount = self.total_ht * vat_rate_decimal
            self.total_ttc = self.total_ht + vat_amount
            
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
                
                # Calculs avec types Decimal uniformes
                discount_factor = Decimal('1') - (discount / Decimal('100'))
                net_price = unit_price * discount_factor
                self.total_ht = net_price * quantity
                
                # Utiliser le service pour résoudre le taux de TVA
                from .services.vat_rate_service import vat_rate_service
                vat_rate_info = vat_rate_service.get_vat_rate_by_code(tenant_id, self.vat_rate)
                
                if vat_rate_info:
                    vat_rate_decimal = Decimal(str(vat_rate_info['rate'])) / Decimal('100')
                else:
                    # Fallback : utiliser le code comme taux numérique
                    vat_rate_decimal = Decimal(str(self.vat_rate)) / Decimal('100')
                
                vat_amount = self.total_ht * vat_rate_decimal
                self.total_ttc = self.total_ht + vat_amount
                
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
        """Override save pour générer automatiquement le numéro"""
        # Générer le numéro si vide ou en création
        if not self.number or self.number == "":
            from .services.number_service import DocumentNumberService
            # Pour la génération du numéro, on a besoin du tenant_id
            # On utilise une approche de fallback simple pour l'instant
            try:
                # Essayer de récupérer le tenant_id depuis le contexte de la requête
                tenant_id = getattr(self, '_tenant_id', None)
                if tenant_id:
                    self.number = DocumentNumberService.generate_quote_number(tenant_id)
                else:
                    # Fallback simple avec timestamp
                    from datetime import datetime
                    self.number = f"DEV-{datetime.now().year}-{str(int(datetime.now().timestamp()))[-6:]}"
            except Exception as e:
                # Fallback en cas d'erreur
                from datetime import datetime
                self.number = f"DEV-{datetime.now().year}-{str(int(datetime.now().timestamp()))[-6:]}"
        
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
        """Marque le devis comme envoyé"""
        # Générer le numéro si c'est un brouillon
        if self.status == QuoteStatus.DRAFT and self.number == "Brouillon":
            from .services.number_service import DocumentNumberService
            self.number = DocumentNumberService.generate_quote_number()
        
        self.status = QuoteStatus.SENT
        self.save(update_fields=['status', 'number'])
    
    def mark_as_accepted(self):
        """Marque le devis comme accepté"""
        self.status = QuoteStatus.ACCEPTED
        self.save(update_fields=['status'])
    
    def mark_as_rejected(self):
        """Marque le devis comme refusé"""
        self.status = QuoteStatus.REJECTED
        self.save(update_fields=['status'])


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
    
    def __str__(self):
        return f"{self.number} - {self.client_name} - {self.total_ttc} €"
    
    @property
    def client_id(self):
        """Propriété pour compatibilité frontend"""
        # Maintenant, le client_id est implicite via le schéma tenant
        return getattr(self, '_client_id', None)
    
    def validate_and_send(self):
        """Valide et envoie la facture"""
        if self.status == InvoiceStatus.DRAFT:
            # Générer le numéro si c'est un brouillon
            if self.number == "Brouillon":
                from .services.number_service import DocumentNumberService
                self.number = DocumentNumberService.generate_invoice_number()
        
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
