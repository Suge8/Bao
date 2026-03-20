import importlib
from pathlib import Path
from xml.dom import minidom as _stdlib_minidom

from . import _base_core, _base_relationships, _base_xsd

try:
    _minidom = importlib.import_module("defusedxml.minidom")
except ModuleNotFoundError:
    _minidom = _stdlib_minidom


class BaseSchemaValidator:
    IGNORED_VALIDATION_ERRORS = [
        "hyphenationZone",
        "purl.org/dc/terms",
    ]

    UNIQUE_ID_REQUIREMENTS = {
        "comment": ("id", "file"),
        "commentrangestart": ("id", "file"),
        "commentrangeend": ("id", "file"),
        "bookmarkstart": ("id", "file"),
        "bookmarkend": ("id", "file"),
        "sldid": ("id", "file"),
        "sldmasterid": ("id", "global"),
        "sldlayoutid": ("id", "global"),
        "cm": ("authorid", "file"),
        "sheet": ("sheetid", "file"),
        "definedname": ("id", "file"),
        "cxnsp": ("id", "file"),
        "sp": ("id", "file"),
        "pic": ("id", "file"),
        "grpsp": ("id", "file"),
    }

    EXCLUDED_ID_CONTAINERS = {
        "sectionlst",
    }

    ELEMENT_RELATIONSHIP_TYPES = {}

    SCHEMA_MAPPINGS = {
        "word": "ISO-IEC29500-4_2016/wml.xsd",
        "ppt": "ISO-IEC29500-4_2016/pml.xsd",
        "xl": "ISO-IEC29500-4_2016/sml.xsd",
        "[Content_Types].xml": "ecma/fouth-edition/opc-contentTypes.xsd",
        "app.xml": "ISO-IEC29500-4_2016/shared-documentPropertiesExtended.xsd",
        "core.xml": "ecma/fouth-edition/opc-coreProperties.xsd",
        "custom.xml": "ISO-IEC29500-4_2016/shared-documentPropertiesCustom.xsd",
        ".rels": "ecma/fouth-edition/opc-relationships.xsd",
        "people.xml": "microsoft/wml-2012.xsd",
        "commentsIds.xml": "microsoft/wml-cid-2016.xsd",
        "commentsExtensible.xml": "microsoft/wml-cex-2018.xsd",
        "commentsExtended.xml": "microsoft/wml-2012.xsd",
        "chart": "ISO-IEC29500-4_2016/dml-chart.xsd",
        "theme": "ISO-IEC29500-4_2016/dml-main.xsd",
        "drawing": "ISO-IEC29500-4_2016/dml-main.xsd",
    }

    MC_NAMESPACE = "http://schemas.openxmlformats.org/markup-compatibility/2006"
    XML_NAMESPACE = "http://www.w3.org/XML/1998/namespace"

    PACKAGE_RELATIONSHIPS_NAMESPACE = "http://schemas.openxmlformats.org/package/2006/relationships"
    OFFICE_RELATIONSHIPS_NAMESPACE = (
        "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
    )
    CONTENT_TYPES_NAMESPACE = "http://schemas.openxmlformats.org/package/2006/content-types"

    MAIN_CONTENT_FOLDERS = {"word", "ppt", "xl"}

    OOXML_NAMESPACES = {
        "http://schemas.openxmlformats.org/officeDocument/2006/math",
        "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
        "http://schemas.openxmlformats.org/schemaLibrary/2006/main",
        "http://schemas.openxmlformats.org/drawingml/2006/main",
        "http://schemas.openxmlformats.org/drawingml/2006/chart",
        "http://schemas.openxmlformats.org/drawingml/2006/chartDrawing",
        "http://schemas.openxmlformats.org/drawingml/2006/diagram",
        "http://schemas.openxmlformats.org/drawingml/2006/picture",
        "http://schemas.openxmlformats.org/drawingml/2006/spreadsheetDrawing",
        "http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing",
        "http://schemas.openxmlformats.org/wordprocessingml/2006/main",
        "http://schemas.openxmlformats.org/presentationml/2006/main",
        "http://schemas.openxmlformats.org/spreadsheetml/2006/main",
        "http://schemas.openxmlformats.org/officeDocument/2006/sharedTypes",
        "http://www.w3.org/XML/1998/namespace",
    }

    def __init__(self, unpacked_dir, original_file=None, verbose=False):
        self.unpacked_dir = Path(unpacked_dir).resolve()
        self.original_file = Path(original_file) if original_file else None
        self.verbose = verbose
        self._minidom = _minidom

        self.schemas_dir = Path(__file__).parent.parent / "schemas"

        patterns = ["*.xml", "*.rels"]
        self.xml_files = [f for pattern in patterns for f in self.unpacked_dir.rglob(pattern)]

        if not self.xml_files:
            print(f"Warning: No XML files found in {self.unpacked_dir}")

    def validate(self):
        raise NotImplementedError("Subclasses must implement the validate method")

    def repair(self) -> int:
        return self.repair_whitespace_preservation()


BaseSchemaValidator.repair_whitespace_preservation = _base_core.repair_whitespace_preservation
BaseSchemaValidator.validate_xml = _base_core.validate_xml
BaseSchemaValidator.validate_namespaces = _base_core.validate_namespaces
BaseSchemaValidator.validate_unique_ids = _base_relationships.validate_unique_ids
BaseSchemaValidator.validate_file_references = _base_relationships.validate_file_references
BaseSchemaValidator.validate_all_relationship_ids = _base_relationships.validate_all_relationship_ids
BaseSchemaValidator._get_expected_relationship_type = _base_relationships._get_expected_relationship_type
BaseSchemaValidator.validate_content_types = _base_relationships.validate_content_types
BaseSchemaValidator.validate_file_against_xsd = _base_xsd.validate_file_against_xsd
BaseSchemaValidator.validate_against_xsd = _base_xsd.validate_against_xsd
BaseSchemaValidator._get_schema_path = _base_xsd._get_schema_path
BaseSchemaValidator._clean_ignorable_namespaces = _base_xsd._clean_ignorable_namespaces
BaseSchemaValidator._remove_ignorable_elements = _base_xsd._remove_ignorable_elements
BaseSchemaValidator._preprocess_for_mc_ignorable = _base_xsd._preprocess_for_mc_ignorable
BaseSchemaValidator._validate_single_file_xsd = _base_xsd._validate_single_file_xsd
BaseSchemaValidator._get_original_file_errors = _base_xsd._get_original_file_errors
BaseSchemaValidator._remove_template_tags_from_text_nodes = _base_xsd._remove_template_tags_from_text_nodes


if __name__ == "__main__":
    raise RuntimeError("This module should not be run directly.")
