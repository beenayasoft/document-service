# Generated manually - Migration des données pour les nouveaux types d'articles

from django.db import migrations


def migrate_item_types_forward(apps, schema_editor):
    """Convertir les anciens types vers les nouveaux types"""
    QuoteItem = apps.get_model('documents', 'QuoteItem')
    
    # Dictionnaire de conversion des anciens vers nouveaux types
    type_mapping = {
        'product': 'material',    # Produit → Matériau
        'service': 'labor',       # Service → Main d'œuvre  
        'work': 'work',          # Ouvrage → Ouvrage (inchangé)
        'chapter': 'chapter',    # Chapitre → Chapitre (inchangé)
        'section': 'section',    # Section → Section (inchangé)
        'discount': 'discount',  # Remise → Remise (inchangé)
        'advance_payment': 'advance_payment'  # Acompte → Acompte (inchangé)
    }
    
    # Conversion pour QuoteItem seulement
    for item in QuoteItem.objects.all():
        if item.type in type_mapping:
            new_type = type_mapping[item.type]
            if new_type != item.type:  # Seulement si le type change
                item.type = new_type
                item.save(update_fields=['type'])


def migrate_item_types_reverse(apps, schema_editor):
    """Convertir les nouveaux types vers les anciens types (rollback)"""
    QuoteItem = apps.get_model('documents', 'QuoteItem')
    
    # Dictionnaire de conversion inverse
    reverse_type_mapping = {
        'material': 'product',    # Matériau → Produit
        'labor': 'service',       # Main d'œuvre → Service
        'work': 'work',          # Ouvrage → Ouvrage (inchangé)
        'chapter': 'chapter',    # Chapitre → Chapitre (inchangé)
        'section': 'section',    # Section → Section (inchangé)
        'discount': 'discount',  # Remise → Remise (inchangé)
        'advance_payment': 'advance_payment'  # Acompte → Acompte (inchangé)
    }
    
    # Conversion inverse pour QuoteItem seulement
    for item in QuoteItem.objects.all():
        if item.type in reverse_type_mapping:
            old_type = reverse_type_mapping[item.type]
            if old_type != item.type:  # Seulement si le type change
                item.type = old_type
                item.save(update_fields=['type'])


class Migration(migrations.Migration):

    dependencies = [
        ('documents', '0004_update_item_types'),
    ]

    operations = [
        migrations.RunPython(
            migrate_item_types_forward,
            migrate_item_types_reverse,
            hints={'preserve_default': False}
        ),
    ]