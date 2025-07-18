"""
Service de calculs unifiés pour les documents
"""
from decimal import Decimal, ROUND_HALF_UP
from typing import List, Dict, Any, Union
from django.db.models import QuerySet


class CalculationService:
    """Service pour tous les calculs financiers des documents"""
    
    @staticmethod
    def calculate_item_totals(unit_price: Decimal, quantity: Decimal, 
                             discount: Decimal = Decimal('0'), 
                             vat_rate: Decimal = Decimal('20')) -> Dict[str, Decimal]:
        """
        Calcule les totaux d'un élément de document
        
        Args:
            unit_price: Prix unitaire
            quantity: Quantité
            discount: Remise en pourcentage (0-100)
            vat_rate: Taux de TVA en pourcentage
            
        Returns:
            Dict avec total_ht et total_ttc
        """
        try:
            # Convertir en Decimal si nécessaire
            unit_price = Decimal(str(unit_price)) if unit_price else Decimal('0')
            quantity = Decimal(str(quantity)) if quantity else Decimal('1')
            discount = Decimal(str(discount)) if discount else Decimal('0')
            vat_rate = Decimal(str(vat_rate)) if vat_rate else Decimal('20')
            
            # Calcul du prix net après remise
            discount_factor = Decimal('1') - (discount / Decimal('100'))
            net_price = unit_price * discount_factor
            
            # Total HT
            total_ht = (net_price * quantity).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
            
            # Calcul de la TVA
            vat_amount = (total_ht * vat_rate / Decimal('100')).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
            
            # Total TTC
            total_ttc = total_ht + vat_amount
            
            return {
                'total_ht': total_ht,
                'total_ttc': total_ttc,
                'vat_amount': vat_amount,
                'net_unit_price': net_price
            }
            
        except (ValueError, TypeError, ArithmeticError):
            # En cas d'erreur, retourner des zéros
            return {
                'total_ht': Decimal('0'),
                'total_ttc': Decimal('0'),
                'vat_amount': Decimal('0'),
                'net_unit_price': Decimal('0')
            }
    
    @staticmethod
    def calculate_document_totals(items: Union[QuerySet, List]) -> Dict[str, Decimal]:
        """
        Calcule les totaux d'un document à partir de ses éléments
        
        Args:
            items: QuerySet ou liste des éléments du document
            
        Returns:
            Dict avec tous les totaux calculés
        """
        total_ht = Decimal('0')
        total_vat = Decimal('0')
        vat_breakdown = {}
        
        for item in items:
            # Ignorer les chapitres et sections qui n'ont pas de montant
            if hasattr(item, 'type') and item.type in ['chapter', 'section']:
                continue
            
            # Ajouter le montant HT
            item_total_ht = getattr(item, 'total_ht', Decimal('0')) or Decimal('0')
            total_ht += item_total_ht
            
            # Calculer la TVA par taux
            vat_rate = str(getattr(item, 'vat_rate', '20'))
            if vat_rate not in vat_breakdown:
                vat_breakdown[vat_rate] = {
                    'base_ht': Decimal('0'),
                    'vat_amount': Decimal('0'),
                    'rate': vat_rate
                }
            
            vat_breakdown[vat_rate]['base_ht'] += item_total_ht
            
            # Calculer le montant de TVA pour cet élément
            vat_rate_decimal = Decimal(vat_rate) / Decimal('100')
            item_vat = (item_total_ht * vat_rate_decimal).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
            vat_breakdown[vat_rate]['vat_amount'] += item_vat
            total_vat += item_vat
        
        # Total TTC
        total_ttc = total_ht + total_vat
        
        return {
            'total_ht': total_ht.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP),
            'total_vat': total_vat.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP),
            'total_ttc': total_ttc.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP),
            'vat_breakdown': list(vat_breakdown.values())
        }
    
    @staticmethod
    def calculate_payment_totals(payments: Union[QuerySet, List]) -> Dict[str, Decimal]:
        """
        Calcule les totaux de paiements
        
        Args:
            payments: QuerySet ou liste des paiements
            
        Returns:
            Dict avec les totaux de paiements
        """
        total_paid = Decimal('0')
        payment_count = 0
        
        for payment in payments:
            amount = getattr(payment, 'amount', Decimal('0')) or Decimal('0')
            total_paid += amount
            payment_count += 1
        
        return {
            'total_paid': total_paid.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP),
            'payment_count': payment_count
        }
    
    @staticmethod
    def calculate_invoice_balances(total_ttc: Decimal, paid_amount: Decimal = Decimal('0')) -> Dict[str, Decimal]:
        """
        Calcule les soldes d'une facture
        
        Args:
            total_ttc: Montant total TTC de la facture
            paid_amount: Montant déjà payé
            
        Returns:
            Dict avec remaining_amount et payment_percentage
        """
        total_ttc = Decimal(str(total_ttc)) if total_ttc else Decimal('0')
        paid_amount = Decimal(str(paid_amount)) if paid_amount else Decimal('0')
        
        remaining_amount = (total_ttc - paid_amount).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
        
        # Pourcentage de paiement
        if total_ttc > 0:
            payment_percentage = (paid_amount / total_ttc * Decimal('100')).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
        else:
            payment_percentage = Decimal('0')
        
        return {
            'remaining_amount': remaining_amount,
            'payment_percentage': payment_percentage,
            'is_fully_paid': remaining_amount <= Decimal('0'),
            'is_partially_paid': Decimal('0') < paid_amount < total_ttc
        }
    
    @staticmethod
    def calculate_quote_margins(items: Union[QuerySet, List]) -> Dict[str, Decimal]:
        """
        Calcule les marges d'un devis
        
        Args:
            items: QuerySet ou liste des éléments du devis
            
        Returns:
            Dict avec les calculs de marge
        """
        total_cost = Decimal('0')
        total_selling_price = Decimal('0')
        
        for item in items:
            if hasattr(item, 'type') and item.type in ['chapter', 'section']:
                continue
            
            # Prix de vente (total HT)
            selling_price = getattr(item, 'total_ht', Decimal('0')) or Decimal('0')
            total_selling_price += selling_price
            
            # Coût (prix unitaire avant marge)
            unit_price = getattr(item, 'unit_price', Decimal('0')) or Decimal('0')
            quantity = getattr(item, 'quantity', Decimal('1')) or Decimal('1')
            discount = getattr(item, 'discount', Decimal('0')) or Decimal('0')
            margin = getattr(item, 'margin', Decimal('0')) or Decimal('0')
            
            # Calculer le coût d'origine (avant application de la marge)
            if margin > 0:
                # Déduire la marge du prix de vente pour retrouver le coût
                margin_factor = Decimal('1') + (margin / Decimal('100'))
                cost_price = unit_price / margin_factor
            else:
                cost_price = unit_price
            
            discount_factor = Decimal('1') - (discount / Decimal('100'))
            item_cost = cost_price * discount_factor * quantity
            total_cost += item_cost
        
        # Calculs de marge
        if total_cost > 0:
            total_margin = total_selling_price - total_cost
            margin_percentage = (total_margin / total_cost * Decimal('100')).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
            markup_percentage = (total_margin / total_selling_price * Decimal('100')).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
        else:
            total_margin = Decimal('0')
            margin_percentage = Decimal('0')
            markup_percentage = Decimal('0')
        
        return {
            'total_cost': total_cost.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP),
            'total_selling_price': total_selling_price.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP),
            'total_margin': total_margin.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP),
            'margin_percentage': margin_percentage,
            'markup_percentage': markup_percentage
        }
    
    @staticmethod
    def validate_financial_data(unit_price: Any = None, quantity: Any = None, 
                               discount: Any = None, vat_rate: Any = None) -> Dict[str, Any]:
        """
        Valide les données financières et retourne les erreurs éventuelles
        
        Returns:
            Dict avec is_valid (bool) et errors (list)
        """
        errors = []
        
        # Validation du prix unitaire
        if unit_price is not None:
            try:
                price = Decimal(str(unit_price))
                if price < 0:
                    errors.append("Le prix unitaire ne peut pas être négatif")
            except (ValueError, TypeError):
                errors.append("Le prix unitaire doit être un nombre valide")
        
        # Validation de la quantité
        if quantity is not None:
            try:
                qty = Decimal(str(quantity))
                if qty < 0:
                    errors.append("La quantité ne peut pas être négative")
            except (ValueError, TypeError):
                errors.append("La quantité doit être un nombre valide")
        
        # Validation de la remise
        if discount is not None:
            try:
                disc = Decimal(str(discount))
                if disc < 0 or disc > 100:
                    errors.append("La remise doit être comprise entre 0 et 100%")
            except (ValueError, TypeError):
                errors.append("La remise doit être un nombre valide")
        
        # Validation du taux de TVA
        if vat_rate is not None:
            try:
                vat = Decimal(str(vat_rate))
                valid_rates = [Decimal('0'), Decimal('5.5'), Decimal('7'), Decimal('10'), Decimal('14'), Decimal('20')]
                if vat not in valid_rates:
                    errors.append(f"Taux de TVA non valide. Taux autorisés : {', '.join(str(r) for r in valid_rates)}%")
            except (ValueError, TypeError):
                errors.append("Le taux de TVA doit être un nombre valide")
        
        return {
            'is_valid': len(errors) == 0,
            'errors': errors
        }
    
    @staticmethod
    def format_currency(amount: Union[Decimal, float, int], currency: str = "€") -> str:
        """
        Formate un montant en devise
        
        Args:
            amount: Montant à formater
            currency: Symbole de la devise
            
        Returns:
            Montant formaté (ex: "1 234,56 €")
        """
        if amount is None:
            return f"0,00 {currency}"
        
        try:
            if isinstance(amount, (int, float)):
                amount = Decimal(str(amount))
            elif not isinstance(amount, Decimal):
                amount = Decimal(str(amount))
            
            # Formater avec séparateur de milliers et virgule décimale
            formatted = f"{amount:,.2f}".replace(",", " ").replace(".", ",")
            return f"{formatted} {currency}"
            
        except (ValueError, TypeError):
            return f"0,00 {currency}"
    
    @staticmethod
    def format_percentage(percentage: Union[Decimal, float, int]) -> str:
        """
        Formate un pourcentage
        
        Args:
            percentage: Pourcentage à formater
            
        Returns:
            Pourcentage formaté (ex: "12,34 %")
        """
        if percentage is None:
            return "0,00 %"
        
        try:
            if isinstance(percentage, (int, float)):
                percentage = Decimal(str(percentage))
            elif not isinstance(percentage, Decimal):
                percentage = Decimal(str(percentage))
            
            formatted = f"{percentage:.2f}".replace(".", ",")
            return f"{formatted} %"
            
        except (ValueError, TypeError):
            return "0,00 %" 