"""
Services communs pour les documents
"""
# from .pdf_service import DocumentPDFService  # SUPPRIMÉ
from .calculation_service import CalculationService
from .workflow_service import WorkflowService
from .number_service import DocumentNumberService

__all__ = [
    # 'DocumentPDFService',  # SUPPRIMÉ
    'CalculationService', 
    'WorkflowService',
    'DocumentNumberService'
] 