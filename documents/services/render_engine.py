"""
Moteur de rendu PDF pour les templates de documents
Architecture complète : Template → HTML → CSS → PDF
"""
import os
import io
import logging
from typing import Dict, Any, Optional, List, Tuple, Union
from pathlib import Path
from datetime import datetime
from django.conf import settings
from django.template.loader import get_template
from django.template import Context, Template as DjangoTemplate
from django.utils import timezone
import base64
import hashlib

from ..schemas.document_template_schema import (
    DocumentTemplate, TemplateComponent, ComponentType, TemplateStyles
)
from .variable_resolver import VariableResolver

logger = logging.getLogger(__name__)


class RenderEngineConfig:
    """Configuration du moteur de rendu"""
    
    # Chemins et répertoires
    TEMPLATES_DIR = Path(__file__).parent.parent / 'templates' / 'pdf'
    STATIC_DIR = Path(__file__).parent.parent / 'static' / 'pdf'
    FONTS_DIR = STATIC_DIR / 'fonts'
    CSS_DIR = STATIC_DIR / 'css'
    
    # Cache
    ENABLE_CACHE = True
    CACHE_TTL = 3600  # 1 heure
    
    # PDF Settings
    DEFAULT_DPI = 300
    DEFAULT_PAGE_SIZE = 'A4'
    DEFAULT_MARGINS = {'top': 20, 'right': 20, 'bottom': 20, 'left': 20}
    
    # Performance
    MAX_CONCURRENT_RENDERS = 5
    RENDER_TIMEOUT = 30  # secondes
    
    # Fallbacks
    USE_CHROMIUM_FALLBACK = False
    CHROMIUM_TIMEOUT = 10


class ComponentRenderer:
    """Renderer pour les composants individuels de templates"""
    
    def __init__(self, variables: Dict[str, Any], styles: TemplateStyles):
        self.variables = variables
        self.styles = styles
        self.resolver = None  # Sera défini par le RenderEngine
    
    def render_component(self, component: TemplateComponent) -> str:
        """
        Rend un composant en HTML
        
        Args:
            component: Composant à rendre
            
        Returns:
            HTML du composant
        """
        try:
            renderer_method = getattr(
                self, 
                f'_render_{component.type.value.lower()}',
                self._render_generic
            )
            
            return renderer_method(component)
            
        except Exception as e:
            logger.error(f"Erreur rendu composant {component.type.value}: {e}")
            return f'<!-- Erreur rendu composant {component.type.value}: {e} -->'
    
    def _render_logo(self, component: TemplateComponent) -> str:
        """Rend un composant Logo"""
        props = component.props.props
        
        # Récupérer les données du logo
        logo_base64 = self._get_variable(props.get('sourceVar', 'tenant.logo_base64'))
        logo_url = self._get_variable('tenant.logo_url')
        max_height = props.get('maxHeight', 60)
        fallback_text = self._get_variable(props.get('fallbackText', 'tenant.name'))
        
        if logo_base64:
            return f'''
            <div class="logo-container" style="max-height: {max_height}px;">
                <img src="data:image/png;base64,{logo_base64}" 
                     alt="Logo" 
                     style="max-height: {max_height}px; max-width: 200px; height: auto;" />
            </div>
            '''
        elif logo_url:
            return f'''
            <div class="logo-container" style="max-height: {max_height}px;">
                <img src="{logo_url}" 
                     alt="Logo" 
                     style="max-height: {max_height}px; max-width: 200px; height: auto;" />
            </div>
            '''
        elif fallback_text:
            return f'''
            <div class="logo-fallback" style="font-size: {max_height//3}px; font-weight: bold; color: {self.styles.primary_color};">
                {fallback_text}
            </div>
            '''
        else:
            return '<!-- Logo non disponible -->'
    
    def _render_title(self, component: TemplateComponent) -> str:
        """Rend un composant Title"""
        props = component.props.props
        
        text = props.get('text', 'TITRE')
        font_size = props.get('fontSize', self.styles.font_size_title)
        color = props.get('color', 'primary')
        align = props.get('align', 'left')
        
        # Résoudre la couleur
        color_value = getattr(self.styles, f'{color}_color', color) if hasattr(self.styles, f'{color}_color') else color
        
        return f'''
        <h1 class="document-title" style="
            font-size: {font_size}px; 
            color: {color_value}; 
            text-align: {align};
            margin: 0;
            font-weight: bold;
        ">{text}</h1>
        '''
    
    def _render_text(self, component: TemplateComponent) -> str:
        """Rend un composant Text"""
        props = component.props.props
        
        text_var = props.get('textVar')
        title = props.get('title')
        font_size = props.get('fontSize', self.styles.font_size_base)
        
        # Récupérer le texte
        text_content = ""
        if text_var:
            text_content = self._get_variable(text_var)
        
        if not text_content:
            return ""
        
        html = ""
        if title:
            html += f'<h3 class="text-title" style="margin-bottom: 8px; font-size: {font_size + 2}px;">{title}</h3>'
        
        html += f'''
        <div class="text-content" style="
            font-size: {font_size}px;
            line-height: 1.4;
            margin-bottom: 10px;
        ">{text_content}</div>
        '''
        
        return html
    
    def _render_address_block(self, component: TemplateComponent) -> str:
        """Rend un bloc d'adresse"""
        props = component.props.props
        
        title = props.get('title', 'Adresse')
        source_context = props.get('sourceContext', 'client')
        fields = props.get('fields', ['name', 'address'])
        
        # Construire l'adresse
        address_lines = []
        for field in fields:
            var_path = f'{source_context}.{field}'
            value = self._get_variable(var_path)
            if value:
                address_lines.append(str(value))
        
        if not address_lines:
            return ""
        
        address_html = "<br>".join(address_lines)
        
        return f'''
        <div class="address-block" style="margin-bottom: 15px;">
            <div class="address-title" style="
                font-weight: bold; 
                margin-bottom: 5px;
                font-size: {self.styles.font_size_base + 1}px;
            ">{title}</div>
            <div class="address-content" style="
                line-height: 1.3;
                font-size: {self.styles.font_size_base}px;
            ">{address_html}</div>
        </div>
        '''
    
    def _render_meta_grid(self, component: TemplateComponent) -> str:
        """Rend une grille de métadonnées"""
        props = component.props.props
        
        items = props.get('items', [])
        columns = props.get('columns', 2)
        align = props.get('align', 'left')
        
        if not items:
            return ""
        
        # Construire le HTML de la grille
        html = f'<div class="meta-grid" style="text-align: {align}; margin-bottom: 15px;">'
        html += '<table style="border-collapse: collapse; margin: 0;">'
        
        for item in items:
            if len(item) >= 2:
                label = item[0]
                value_var = item[1]
                value = self._get_variable(value_var) if value_var else ""
                
                # Formater la valeur si c'est une date
                if isinstance(value, datetime):
                    value = value.strftime('%d/%m/%Y')
                elif hasattr(value, 'date'):  # datetime object
                    value = value.date().strftime('%d/%m/%Y')
                
                html += f'''
                <tr>
                    <td style="
                        padding: 2px 15px 2px 0; 
                        font-weight: bold;
                        vertical-align: top;
                        font-size: {self.styles.font_size_base}px;
                    ">{label}:</td>
                    <td style="
                        padding: 2px 0;
                        vertical-align: top;
                        font-size: {self.styles.font_size_base}px;
                    ">{value}</td>
                </tr>
                '''
        
        html += '</table></div>'
        return html
    
    def _render_items_table(self, component: TemplateComponent) -> str:
        """Rend le tableau des articles"""
        props = component.props.props
        
        columns = props.get('columns', [])
        show_headers = props.get('showHeaders', True)
        striped = props.get('striped', True)
        bordered = props.get('bordered', True)
        
        # Récupérer les items
        items = self._get_variable('items.list') or []
        
        if not items or not columns:
            return '<p>Aucun article</p>'
        
        # Style du tableau
        table_style = f'''
            width: 100%;
            border-collapse: collapse;
            margin-bottom: 15px;
            font-size: {self.styles.font_size_base}px;
        '''
        
        if bordered:
            table_style += f'border: {self.styles.border_width}px solid {self.styles.border_color};'
        
        html = f'<table style="{table_style}">'
        
        # En-têtes
        if show_headers:
            html += '<thead><tr style="background-color: ' + (self.styles.table_header_bg or '#f9fafb') + ';">'
            for col in columns:
                width_style = f'width: {col.get("width", "auto")};' if col.get("width") else ""
                html += f'''
                <th style="
                    padding: {self.styles.table_padding}px;
                    text-align: {col.get('align', 'left')};
                    font-weight: bold;
                    {width_style}
                    {'border: ' + str(self.styles.border_width) + 'px solid ' + self.styles.border_color + ';' if bordered else ''}
                ">{col.get('label', col.get('key', ''))}</th>
                '''
            html += '</tr></thead>'
        
        # Corps du tableau
        html += '<tbody>'
        for i, item in enumerate(items):
            # Style de ligne (striped)
            row_style = ""
            if striped and i % 2 == 1:
                row_style = "background-color: #f8f9fa;"
            
            # Ignorer les chapitres/sections pour l'affichage tableau
            if item.get('type') in ['chapter', 'section']:
                # Afficher comme ligne de titre
                html += f'''
                <tr style="{row_style} font-weight: bold;">
                    <td colspan="{len(columns)}" style="
                        padding: {self.styles.table_padding + 2}px;
                        font-weight: bold;
                        background-color: #e9ecef;
                        {'border: ' + str(self.styles.border_width) + 'px solid ' + self.styles.border_color + ';' if bordered else ''}
                    ">{item.get('designation', '')}</td>
                </tr>
                '''
                continue
            
            html += f'<tr style="{row_style}">'
            
            for col in columns:
                key = col.get('key')
                value = item.get(key, '')
                
                # Formatage spécial selon le type de colonne
                if key in ['unit_price', 'total_ht', 'total_ttc'] and isinstance(value, (int, float)):
                    value = f"{value:.2f} €"
                elif key == 'discount' and isinstance(value, (int, float)):
                    value = f"{value}%" if value > 0 else ""
                elif key == 'quantity' and isinstance(value, (int, float)):
                    value = f"{value:.2f}" if value != int(value) else str(int(value))
                
                cell_style = f'''
                    padding: {self.styles.table_padding}px;
                    text-align: {col.get('align', 'left')};
                    {'border: ' + str(self.styles.border_width) + 'px solid ' + self.styles.border_color + ';' if bordered else ''}
                '''
                
                html += f'<td style="{cell_style}">{value}</td>'
            
            html += '</tr>'
        
        html += '</tbody></table>'
        return html
    
    def _render_totals_summary(self, component: TemplateComponent) -> str:
        """Rend le résumé des totaux"""
        props = component.props.props
        
        align = props.get('align', 'right')
        width = props.get('width', '40%')
        show_vat_breakdown = props.get('showVatBreakdown', True)
        currency = self._get_variable('totals.currency') or '€'
        
        # Récupérer les totaux
        total_ht = self._get_variable('totals.total_ht') or 0
        total_vat = self._get_variable('totals.total_vat') or 0
        total_ttc = self._get_variable('totals.total_ttc') or 0
        
        html = f'''
        <div class="totals-summary" style="
            width: {width};
            margin-left: {'auto' if align == 'right' else '0'};
            margin-right: {'auto' if align == 'center' else '0'};
            margin-bottom: 15px;
        ">
            <table style="
                width: 100%;
                border-collapse: collapse;
                font-size: {self.styles.font_size_base}px;
            ">
        '''
        
        # Ligne Total HT
        html += f'''
        <tr>
            <td style="
                padding: 5px 10px;
                text-align: right;
                font-weight: bold;
                border-top: 1px solid {self.styles.border_color};
            ">Total HT:</td>
            <td style="
                padding: 5px 10px;
                text-align: right;
                border-top: 1px solid {self.styles.border_color};
                font-weight: bold;
                min-width: 80px;
            ">{total_ht:.2f} {currency}</td>
        </tr>
        '''
        
        # Ligne TVA
        if show_vat_breakdown and total_vat > 0:
            html += f'''
            <tr>
                <td style="padding: 5px 10px; text-align: right;">TVA:</td>
                <td style="padding: 5px 10px; text-align: right; min-width: 80px;">{total_vat:.2f} {currency}</td>
            </tr>
            '''
        
        # Ligne Total TTC
        html += f'''
        <tr>
            <td style="
                padding: 8px 10px;
                text-align: right;
                font-weight: bold;
                font-size: {self.styles.font_size_base + 2}px;
                border-top: 2px solid {self.styles.primary_color};
                background-color: #f8f9fa;
            ">Total TTC:</td>
            <td style="
                padding: 8px 10px;
                text-align: right;
                font-weight: bold;
                font-size: {self.styles.font_size_base + 2}px;
                border-top: 2px solid {self.styles.primary_color};
                background-color: #f8f9fa;
                min-width: 80px;
            ">{total_ttc:.2f} {currency}</td>
        </tr>
        '''
        
        html += '</table></div>'
        return html
    
    def _render_two_cols(self, component: TemplateComponent) -> str:
        """Rend un layout à deux colonnes"""
        props = component.props.props
        left_width = props.get('leftWidth', '50%')
        right_width = props.get('rightWidth', '50%')
        spacing = props.get('spacing', 10)
        
        html = f'''
        <div class="two-cols" style="
            display: table;
            width: 100%;
            margin-bottom: {spacing}px;
        ">
            <div class="col-left" style="
                display: table-cell;
                width: {left_width};
                vertical-align: top;
                padding-right: {spacing}px;
            ">
        '''
        
        # Rendre les enfants de gauche
        if len(component.children) > 0:
            html += self.render_component(component.children[0])
        
        html += f'''
            </div>
            <div class="col-right" style="
                display: table-cell;
                width: {right_width};
                vertical-align: top;
            ">
        '''
        
        # Rendre les enfants de droite  
        if len(component.children) > 1:
            html += self.render_component(component.children[1])
        
        html += '</div></div>'
        return html
    
    def _render_spacer(self, component: TemplateComponent) -> str:
        """Rend un espaceur"""
        props = component.props.props
        height = props.get('height', 10)
        
        return f'<div class="spacer" style="height: {height}px;"></div>'
    
    def _render_small_print(self, component: TemplateComponent) -> str:
        """Rend du texte en petits caractères (footer)"""
        props = component.props.props
        
        text_var = props.get('textVar')
        font_size = props.get('fontSize', self.styles.font_size_small)
        align = props.get('align', 'left')
        
        text_content = self._get_variable(text_var) if text_var else ""
        
        if not text_content:
            return ""
        
        return f'''
        <div class="small-print" style="
            font-size: {font_size}px;
            text-align: {align};
            line-height: 1.2;
            color: {self.styles.secondary_color};
            margin-bottom: 5px;
        ">{text_content}</div>
        '''
    
    def _render_page_x_of_y(self, component: TemplateComponent) -> str:
        """Rend la numérotation de page"""
        props = component.props.props
        
        align = props.get('align', 'center')
        font_size = props.get('fontSize', self.styles.font_size_small)
        
        return f'''
        <div class="page-numbers" style="
            font-size: {font_size}px;
            text-align: {align};
            color: {self.styles.secondary_color};
        ">Page <span class="page-number"></span> sur <span class="page-count"></span></div>
        '''
    
    def _render_generic(self, component: TemplateComponent) -> str:
        """Rendu générique pour composants non implémentés"""
        return f'<!-- Composant {component.type.value} non implémenté -->'
    
    def _get_variable(self, var_path: str) -> Any:
        """Récupère une variable depuis les données résolues"""
        if not var_path:
            return ""
        
        return self.variables.get(var_path, "")


class HTMLRenderer:
    """Générateur HTML complet depuis un template"""
    
    def __init__(self, config: RenderEngineConfig = None):
        self.config = config or RenderEngineConfig()
    
    def render_template_to_html(self, 
                               template: DocumentTemplate,
                               variables: Dict[str, Any],
                               custom_css: str = None) -> str:
        """
        Génère le HTML complet d'un template avec variables résolues
        
        Args:
            template: Template à rendre
            variables: Variables résolues
            custom_css: CSS personnalisé optionnel
            
        Returns:
            HTML complet prêt pour PDF
        """
        try:
            # Créer le renderer de composants
            component_renderer = ComponentRenderer(variables, template.styles)
            
            # Générer le CSS
            css = self._generate_css(template.styles, template.page_settings, custom_css)
            
            # Générer le HTML de chaque région
            regions_html = {}
            for region_name, region in template.regions.items():
                region_html = ""
                for component in region.components:
                    region_html += component_renderer.render_component(component)
                regions_html[region_name] = region_html
            
            # Construire le document HTML complet
            html = self._build_complete_html(
                template=template,
                regions_html=regions_html,
                css=css,
                variables=variables
            )
            
            return html
            
        except Exception as e:
            logger.error(f"Erreur rendu HTML template {template.id}: {e}")
            raise
    
    def _generate_css(self, 
                     styles: TemplateStyles, 
                     page_settings,
                     custom_css: str = None) -> str:
        """Génère le CSS complet pour le document"""
        
        css = f'''
        /* CSS généré automatiquement pour template */
        @page {{
            size: {page_settings.size or 'A4'};
            margin-top: {page_settings.margins.get('top', 20)}mm;
            margin-right: {page_settings.margins.get('right', 20)}mm;
            margin-bottom: {page_settings.margins.get('bottom', 20)}mm;
            margin-left: {page_settings.margins.get('left', 20)}mm;
            
            @top-center {{
                content: "";
            }}
            
            @bottom-center {{
                content: counter(page) " / " counter(pages);
                font-size: {styles.font_size_small}px;
                color: {styles.secondary_color};
            }}
        }}
        
        * {{
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }}
        
        body {{
            font-family: {styles.font_family};
            font-size: {styles.font_size_base}px;
            line-height: 1.4;
            color: {styles.primary_color};
        }}
        
        .document-container {{
            width: 100%;
            max-width: 100%;
        }}
        
        .page-break {{
            page-break-before: always;
        }}
        
        .no-break {{
            page-break-inside: avoid;
        }}
        
        table {{
            border-collapse: collapse;
            width: 100%;
        }}
        
        .header {{
            margin-bottom: 20px;
        }}
        
        .body {{
            min-height: 400px;
        }}
        
        .footer {{
            margin-top: 20px;
        }}
        
        /* Styles responsive pour impression */
        @media print {{
            body {{ margin: 0; }}
            .document-container {{ max-width: none; }}
        }}
        '''
        
        # Ajouter le CSS personnalisé si fourni
        if custom_css:
            css += f"\n/* CSS personnalisé */\n{custom_css}\n"
        
        return css
    
    def _build_complete_html(self,
                           template: DocumentTemplate,
                           regions_html: Dict[str, str],
                           css: str,
                           variables: Dict[str, Any]) -> str:
        """Construit le document HTML complet"""
        
        # Métadonnées du document
        doc_title = f"{template.name} - {variables.get('document.number', 'Document')}"
        doc_subject = f"Document généré par Beenaya - {template.document_type}"
        
        html = f'''<!DOCTYPE html>
<html lang="fr">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{doc_title}</title>
    <meta name="subject" content="{doc_subject}">
    <meta name="creator" content="Beenaya Document Service">
    <meta name="producer" content="WeasyPrint">
    <meta name="creation-date" content="{timezone.now().isoformat()}">
    
    <style>
        {css}
    </style>
</head>
<body>
    <div class="document-container">
        <!-- En-tête -->
        <div class="header">
            {regions_html.get('header', '')}
        </div>
        
        <!-- Corps du document -->
        <div class="body">
            {regions_html.get('body', '')}
        </div>
        
        <!-- Pied de page -->
        <div class="footer">
            {regions_html.get('footer', '')}
        </div>
    </div>
</body>
</html>'''
        
        return html


# Configuration et utilitaires

def create_render_engine_config() -> RenderEngineConfig:
    """Crée une configuration par défaut du moteur de rendu"""
    config = RenderEngineConfig()
    
    # Créer les répertoires nécessaires s'ils n'existent pas
    config.TEMPLATES_DIR.mkdir(parents=True, exist_ok=True)
    config.STATIC_DIR.mkdir(parents=True, exist_ok=True)
    config.FONTS_DIR.mkdir(parents=True, exist_ok=True)
    config.CSS_DIR.mkdir(parents=True, exist_ok=True)
    
    return config


def render_template_to_html(template: DocumentTemplate, 
                           variables: Dict[str, Any],
                           custom_css: str = None) -> str:
    """
    Fonction utilitaire pour rendre un template en HTML
    
    Args:
        template: Template à rendre
        variables: Variables résolues
        custom_css: CSS personnalisé optionnel
        
    Returns:
        HTML complet
    """
    config = create_render_engine_config()
    renderer = HTMLRenderer(config)
    
    return renderer.render_template_to_html(template, variables, custom_css)