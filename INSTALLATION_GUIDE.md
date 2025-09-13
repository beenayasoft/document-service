# Guide d'installation - Génération PDF (Phase 2)

## 🎯 Installation rapide

### Windows (Recommandé)
```batch
# Méthode 1 : Script automatique
.\install_pdf_windows.bat

# Méthode 2 : Installation manuelle
pip install -r requirements_pdf_minimal.txt
```

### Linux (Ubuntu/Debian)
```bash
# 1. Installer les dépendances système
sudo apt-get update
sudo apt-get install build-essential python3-dev python3-pip python3-setuptools python3-wheel python3-cffi libcairo2 libpango-1.0-0 libpangocairo-1.0-0 libgdk-pixbuf2.0-0 libffi-dev shared-mime-info

# 2. Installer les dépendances Python
pip install -r requirements_pdf.txt
```

### macOS
```bash
# 1. Installer les dépendances système avec Homebrew
brew install cairo pango gdk-pixbuf libffi

# 2. Installer les dépendances Python  
pip install -r requirements_pdf.txt
```

## 🔧 Dépendances principales

### WeasyPrint (Recommandé)
- **Avantages** : Meilleure qualité PDF, support CSS avancé
- **Inconvénients** : Plus difficile à installer sur Windows

### Playwright (Fallback)
- **Avantages** : Installation facile, compatible tous OS
- **Inconvénients** : Qualité PDF moindre, plus lent

## 🚨 Résolution de problèmes

### Erreur WeasyPrint sur Windows
```
ERROR: Microsoft Visual C++ 14.0 is required
```

**Solutions :**
1. Installer Visual Studio Build Tools
2. Ou utiliser uniquement Playwright :
   ```batch
   pip install playwright>=1.40.0
   playwright install chromium
   ```

### Erreur fontconfig
```
ERROR: Could not find fontconfig>=1.0.0
```

**Solution :** Utiliser `requirements_pdf_minimal.txt` au lieu de `requirements_pdf.txt`

### Erreur de dépendances système (Linux)
```
ERROR: Failed building wheel for cairocffi
```

**Solution :** Installer les paquets système requis :
```bash
sudo apt-get install libcairo2-dev libpango1.0-dev libgdk-pixbuf2.0-dev libffi-dev
```

## ✅ Tests d'installation

### Vérifier l'installation
```bash
cd soa/services/document-service
python test_pdf_generation.py
```

### Vérification rapide
```python
# Test dans le shell Django
python manage.py shell

from documents.services.pdf_generator import get_pdf_service_status
status = get_pdf_service_status()
print(status)
```

## 📋 Configurations recommandées

### Production (Linux)
- ✅ WeasyPrint (principal)
- ✅ Playwright (fallback) 
- ✅ Redis cache activé
- ✅ Monitoring psutil

### Développement (Windows)
- ✅ Playwright (principal)
- ⚠️ WeasyPrint (si possible)
- ✅ Cache local
- ✅ Mode debug

### CI/CD (Docker)
```dockerfile
# Utiliser image avec dépendances pré-installées
FROM python:3.11-slim

# Installer dépendances système
RUN apt-get update && apt-get install -y \
    libcairo2 libpango-1.0-0 libpangocairo-1.0-0 \
    libgdk-pixbuf2.0-0 libffi-dev shared-mime-info

# Installer dépendances Python
COPY requirements_pdf.txt .
RUN pip install -r requirements_pdf.txt
```

## 🎨 Optimisations optionnelles

### Polices personnalisées
```bash
# Copier les polices dans documents/static/fonts/
cp your-font.ttf soa/services/document-service/documents/static/fonts/
```

### ImageMagick (optionnel)
```bash
# Pour traitement d'images avancé
sudo apt-get install imagemagick libmagickwand-dev
pip install wand>=0.6.13
```

### Optimisation mémoire
```bash
# Pour monitoring avancé
pip install psutil>=5.9.0
```

## 🔄 Mise à jour

### Mettre à jour WeasyPrint
```bash
pip install --upgrade weasyprint
```

### Mettre à jour Playwright
```bash
pip install --upgrade playwright
playwright install chromium
```

## 📞 Support

En cas de problème :

1. **Vérifier** que Django démarre sans erreur
2. **Tester** l'API basic : `/api/health/`
3. **Consulter** les logs : `logs/document-service.log`
4. **Lancer** les tests : `python test_pdf_generation.py`

La Phase 2 peut fonctionner avec Playwright seul si WeasyPrint ne s'installe pas.