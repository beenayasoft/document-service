"""
Générateur CSS dynamique pour les templates de documents
Conversion des styles de templates en CSS optimisé pour PDF
"""
import logging
from typing import Dict, Any, List, Optional
from pathlib import Path
from django.conf import settings

from ..schemas.document_template_schema import TemplateStyles, PageSettings

logger = logging.getLogger(__name__)


class CSSGenerator:
    """Générateur CSS dynamique depuis les styles de templates"""
    
    def __init__(self):
        self.base_css_path = Path(__file__).parent.parent / 'static' / 'css' / 'base_styles.css'
    
    def generate_css_from_template_styles(self, 
                                        styles: TemplateStyles,
                                        page_settings: PageSettings,
                                        custom_overrides: Dict[str, Any] = None) -> str:
        """
        Génère le CSS complet depuis les styles du template
        
        Args:
            styles: Styles du template
            page_settings: Paramètres de page
            custom_overrides: Overrides CSS personnalisés
            
        Returns:
            CSS complet pour le document
        """
        try:
            css_parts = []
            
            # 1. CSS de base
            base_css = self._load_base_css()
            css_parts.append(base_css)
            
            # 2. Configuration de page
            page_css = self._generate_page_css(page_settings)
            css_parts.append(page_css)
            
            # 3. Variables CSS depuis les styles
            variables_css = self._generate_css_variables(styles)
            css_parts.append(variables_css)
            
            # 4. Styles dynamiques
            dynamic_css = self._generate_dynamic_styles(styles)
            css_parts.append(dynamic_css)
            
            # 5. Overrides personnalisés
            if custom_overrides:
                override_css = self._generate_overrides_css(custom_overrides)
                css_parts.append(override_css)
            
            # Combiner tous les CSS
            complete_css = "\n\n".join(css_parts)
            
            logger.debug(f"CSS généré: {len(complete_css)} caractères")
            return complete_css
            
        except Exception as e:
            logger.error(f"Erreur génération CSS: {e}")
            # Fallback vers le CSS de base
            return self._load_base_css()
    
    def _load_base_css(self) -> str:
        """Charge le CSS de base"""
        try:
            if self.base_css_path.exists():
                return self.base_css_path.read_text(encoding='utf-8')
            else:
                logger.warning(f"CSS de base non trouvé: {self.base_css_path}")
                return self._get_fallback_css()
        except Exception as e:
            logger.error(f"Erreur chargement CSS de base: {e}")
            return self._get_fallback_css()
    
    def _generate_page_css(self, page_settings: PageSettings) -> str:
        """Génère le CSS de configuration de page"""
        size = page_settings.size or 'A4'
        orientation = page_settings.orientation or 'portrait'
        margins = page_settings.margins or {}
        
        # Marges par défaut
        top_margin = margins.get('top', 20)
        right_margin = margins.get('right', 20)
        bottom_margin = margins.get('bottom', 20)
        left_margin = margins.get('left', 20)
        units = page_settings.units or 'mm'
        
        css = f"""
/* Configuration de page dynamique */
@page {{
    size: {size} {orientation};
    margin-top: {top_margin}{units};
    margin-right: {right_margin}{units};
    margin-bottom: {bottom_margin}{units};
    margin-left: {left_margin}{units};
    
    @bottom-center {{
        content: counter(page) " / " counter(pages);
        font-size: 8px;
        color: #6b7280;
        margin-top: 5mm;
    }}
}}
"""
        
        # Styles spécifiques à l'orientation
        if orientation == 'landscape':
            css += """
@page :first {
    size: """ + size + """ landscape;
}
"""
        
        return css
    
    def _generate_css_variables(self, styles: TemplateStyles) -> str:
        """Génère les variables CSS depuis les styles du template"""
        css = """
/* Variables CSS dynamiques */
:root {
"""
        
        # Variables de polices
        css += f"    --font-family: {styles.font_family};\n"
        css += f"    --font-size-base: {styles.font_size_base}px;\n"
        css += f"    --font-size-small: {styles.font_size_small}px;\n"
        css += f"    --font-size-large: {styles.font_size_large}px;\n"
        css += f"    --font-size-title: {styles.font_size_title}px;\n"
        
        # Variables de couleurs
        css += f"    --color-primary: {styles.primary_color};\n"
        css += f"    --color-secondary: {styles.secondary_color};\n"
        css += f"    --color-accent: {styles.accent_color};\n"
        css += f"    --color-success: {styles.success_color};\n"
        css += f"    --color-warning: {styles.warning_color};\n"
        css += f"    --color-error: {styles.error_color};\n"
        
        # Variables d'espacement
        css += f"    --spacing-xs: {styles.spacing_xs}px;\n"
        css += f"    --spacing-sm: {styles.spacing_sm}px;\n"
        css += f"    --spacing-md: {styles.spacing_md}px;\n"
        css += f"    --spacing-lg: {styles.spacing_lg}px;\n"
        css += f"    --spacing-xl: {styles.spacing_xl}px;\n"
        
        # Variables de bordures
        css += f"    --border-radius: {styles.border_radius}px;\n"
        css += f"    --border-width: {styles.border_width}px;\n"
        css += f"    --border-color: {styles.border_color};\n"
        
        # Variables de tableaux
        css += f"    --table-header-bg: {styles.table_header_bg};\n"
        css += f"    --table-padding: {styles.table_padding}px;\n"
        
        css += "}\n"
        
        return css
    
    def _generate_dynamic_styles(self, styles: TemplateStyles) -> str:
        """Génère les styles dynamiques appliqués aux éléments"""
        css = """
/* Styles dynamiques basés sur le template */

body {
    font-family: var(--font-family);
    font-size: var(--font-size-base);
    color: var(--color-primary);
}

.document-title {
    font-size: var(--font-size-title);
    color: var(--color-primary);
}

.address-title {
    color: var(--color-primary);
}

.items-table th {
    background-color: var(--table-header-bg);
    padding: var(--table-padding);
    border: var(--border-width) solid var(--border-color);
}

.items-table td {
    padding: var(--table-padding);
    border: var(--border-width) solid var(--border-color);
}

.totals-summary .grand-total .total-label,
.totals-summary .grand-total .total-value {
    border-top: 2px solid var(--color-accent);
    border-bottom: 2px solid var(--color-accent);
}

.small-print {
    color: var(--color-secondary);
}

.page-numbers {
    color: var(--color-secondary);
}
"""
        
        # Styles conditionnels selon les options
        if styles.table_border:
            css += """
.items-table {
    border: var(--border-width) solid var(--border-color);
}
"""
        
        if styles.table_striped:
            css += """
.items-table tr:nth-child(even) {
    background-color: #f8f9fa;
}
"""
        
        return css
    
    def _generate_overrides_css(self, overrides: Dict[str, Any]) -> str:
        """Génère les CSS d'override personnalisés"""
        css = "\n/* Overrides personnalisés */\n"
        
        for selector, properties in overrides.items():
            css += f"{selector} {{\n"
            for prop, value in properties.items():
                css += f"    {prop}: {value};\n"
            css += "}\n"
        
        return css
    
    def _get_fallback_css(self) -> str:
        """CSS de fallback minimal"""
        return """
/* CSS de fallback minimal */
@page {
    size: A4;
    margin: 20mm;
}

* {
    margin: 0;
    padding: 0;
    box-sizing: border-box;
}

body {
    font-family: Arial, sans-serif;
    font-size: 12px;
    line-height: 1.4;
    color: #1f2937;
}

table {
    width: 100%;
    border-collapse: collapse;
    margin-bottom: 15px;
}

th, td {
    padding: 8px;
    text-align: left;
    border: 1px solid #d1d5db;
}

th {
    background-color: #f9fafb;
    font-weight: bold;
}

.document-title {
    font-size: 24px;
    font-weight: bold;
    margin-bottom: 20px;
}

.totals-summary {
    float: right;
    width: 40%;
}
"""
    
    def generate_component_specific_css(self, component_type: str, props: Dict[str, Any]) -> str:
        """
        Génère du CSS spécifique pour un type de composant
        
        Args:
            component_type: Type de composant
            props: Propriétés du composant
            
        Returns:
            CSS spécifique au composant
        """
        css = ""
        
        if component_type == "Logo":
            max_height = props.get('maxHeight', 60)
            css = f"""
.logo-container img {{
    max-height: {max_height}px;
    max-width: 200px;
    height: auto;
}}
"""
        
        elif component_type == "Title":
            font_size = props.get('fontSize', 24)
            color = props.get('color', '#1f2937')
            align = props.get('align', 'left')
            css = f"""
.document-title {{
    font-size: {font_size}px;
    color: {color};
    text-align: {align};
}}
"""
        
        elif component_type == "ItemsTable":
            if props.get('bordered', True):
                css += """
.items-table,
.items-table th,
.items-table td {
    border: 1px solid #d1d5db;
}
"""
            
            if props.get('striped', True):
                css += """
.items-table tr:nth-child(even) {
    background-color: #f8f9fa;
}
"""
        
        elif component_type == "TotalsSummary":
            width = props.get('width', '40%')
            align = props.get('align', 'right')
            css = f"""
.totals-summary {{
    width: {width};
    margin-left: {'auto' if align == 'right' else '0'};
    margin-right: {'auto' if align == 'center' else '0'};
}}
"""
        
        return css
    
    def optimize_css_for_pdf(self, css: str) -> str:
        """
        Optimise le CSS pour la génération PDF
        
        Args:
            css: CSS à optimiser
            
        Returns:
            CSS optimisé
        """
        try:
            # Supprimer les commentaires multi-lignes
            import re
            css = re.sub(r'/\*.*?\*/', '', css, flags=re.DOTALL)
            
            # Supprimer les lignes vides multiples
            css = re.sub(r'\n\s*\n', '\n', css)
            
            # Supprimer les espaces en début/fin de ligne
            css = '\n'.join(line.strip() for line in css.split('\n') if line.strip())
            
            # Ajouter des optimisations spécifiques PDF
            pdf_optimizations = """
/* Optimisations PDF */
* {
    -webkit-print-color-adjust: exact;
    color-adjust: exact;
}

img {
    image-rendering: -webkit-optimize-contrast;
    image-rendering: crisp-edges;
}
"""
            
            css = pdf_optimizations + "\n" + css
            
            logger.debug(f"CSS optimisé: {len(css)} caractères")
            return css
            
        except Exception as e:
            logger.error(f"Erreur optimisation CSS: {e}")
            return css


# Instance globale
css_generator = CSSGenerator()


# Fonctions utilitaires

def generate_css_for_template(styles: TemplateStyles,
                            page_settings: PageSettings, 
                            custom_overrides: Dict[str, Any] = None) -> str:
    """
    Fonction utilitaire pour générer le CSS d'un template
    
    Args:
        styles: Styles du template
        page_settings: Paramètres de page
        custom_overrides: Overrides personnalisés
        
    Returns:
        CSS complet
    """
    return css_generator.generate_css_from_template_styles(
        styles, page_settings, custom_overrides
    )


def optimize_css(css: str) -> str:
    """
    Fonction utilitaire pour optimiser du CSS pour PDF
    
    Args:
        css: CSS à optimiser
        
    Returns:
        CSS optimisé
    """
    return css_generator.optimize_css_for_pdf(css)