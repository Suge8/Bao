"""
Validator for Word document XML files against XSD schemas.
"""

import importlib
from xml.dom import minidom as _stdlib_minidom

from . import _docx_checks, _docx_ids
from .base import BaseSchemaValidator

try:
    _minidom = importlib.import_module("defusedxml.minidom")
except ModuleNotFoundError:
    _minidom = _stdlib_minidom


class DOCXSchemaValidator(BaseSchemaValidator):
    WORD_2006_NAMESPACE = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
    W14_NAMESPACE = "http://schemas.microsoft.com/office/word/2010/wordml"
    W16CID_NAMESPACE = "http://schemas.microsoft.com/office/word/2016/wordml/cid"

    ELEMENT_RELATIONSHIP_TYPES = {}

if __name__ == "__main__":
    raise RuntimeError("This module should not be run directly.")


DOCXSchemaValidator.validate = _docx_checks.validate
DOCXSchemaValidator.validate_whitespace_preservation = _docx_checks.validate_whitespace_preservation
DOCXSchemaValidator.validate_deletions = _docx_checks.validate_deletions
DOCXSchemaValidator.count_paragraphs_in_unpacked = _docx_checks.count_paragraphs_in_unpacked
DOCXSchemaValidator.count_paragraphs_in_original = _docx_checks.count_paragraphs_in_original
DOCXSchemaValidator.validate_insertions = _docx_checks.validate_insertions
DOCXSchemaValidator.compare_paragraph_counts = _docx_checks.compare_paragraph_counts
DOCXSchemaValidator._parse_id_value = _docx_checks._parse_id_value
DOCXSchemaValidator.validate_id_constraints = _docx_ids.validate_id_constraints
DOCXSchemaValidator.validate_comment_markers = _docx_ids.validate_comment_markers
DOCXSchemaValidator.repair = _docx_ids.repair
DOCXSchemaValidator.repair_durable_id = _docx_ids.repair_durable_id
