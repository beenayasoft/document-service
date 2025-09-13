@echo off
echo Installation des dependances PDF pour Windows - Phase 2

echo.
echo [1/3] Installation des dependances Python de base...
pip install --upgrade pip

echo.
echo [2/3] Tentative d'installation WeasyPrint...
pip install weasyprint>=60.0
if %ERRORLEVEL% NEQ 0 (
    echo ATTENTION: WeasyPrint a echoue. Installation de Playwright comme fallback...
    pip install playwright>=1.40.0
    echo Installation du navigateur Chromium...
    playwright install chromium
    echo.
    echo WeasyPrint non disponible - Seul Playwright sera utilise pour la generation PDF
) else (
    echo WeasyPrint installe avec succes !
    echo Installation de Playwright comme fallback...
    pip install playwright>=1.40.0
    playwright install chromium
)

echo.
echo [3/3] Installation des dependances optionnelles...
pip install psutil>=5.9.0

echo.
echo Installation terminee !
echo.
echo Pour tester la generation PDF :
echo cd soa/services/document-service
echo python test_pdf_generation.py
echo.
pause