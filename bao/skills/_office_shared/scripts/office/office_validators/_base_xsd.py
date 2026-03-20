"""XSD validation helpers for BaseSchemaValidator."""

from __future__ import annotations

import re
import tempfile
import zipfile
from pathlib import Path

import lxml.etree


def validate_file_against_xsd(self, xml_file, verbose=False):
    xml_file = Path(xml_file).resolve()
    unpacked_dir = self.unpacked_dir.resolve()
    is_valid, current_errors = self._validate_single_file_xsd(xml_file, unpacked_dir)
    if is_valid is None:
        return None, set()
    if is_valid:
        return True, set()
    original_errors = self._get_original_file_errors(xml_file)
    assert current_errors is not None
    new_errors = {
        error
        for error in current_errors - original_errors
        if not any(pattern in error for pattern in self.IGNORED_VALIDATION_ERRORS)
    }
    if new_errors:
        if verbose:
            relative_path = xml_file.relative_to(unpacked_dir)
            print(f"FAILED - {relative_path}: {len(new_errors)} new error(s)")
            for error in list(new_errors)[:3]:
                truncated = error[:250] + "..." if len(error) > 250 else error
                print(f"  - {truncated}")
        return False, new_errors
    if verbose:
        print(f"PASSED - No new errors (original had {len(current_errors)} errors)")
    return True, set()


def validate_against_xsd(self):
    new_errors = []
    original_error_count = 0
    valid_count = 0
    skipped_count = 0
    for xml_file in self.xml_files:
        relative_path = str(xml_file.relative_to(self.unpacked_dir))
        is_valid, new_file_errors = self.validate_file_against_xsd(xml_file, verbose=False)
        if is_valid is None:
            skipped_count += 1
            continue
        if is_valid and not new_file_errors:
            valid_count += 1
            continue
        if is_valid:
            original_error_count += 1
            valid_count += 1
            continue
        new_errors.append(f"  {relative_path}: {len(new_file_errors)} new error(s)")
        for error in list(new_file_errors)[:3]:
            new_errors.append(f"    - {error[:250]}..." if len(error) > 250 else f"    - {error}")
    if self.verbose:
        _print_xsd_summary(self, valid_count, skipped_count, original_error_count, new_errors)
    if new_errors:
        print("\nFAILED - Found NEW validation errors:")
        for error in new_errors:
            print(error)
        return False
    if self.verbose:
        print("\nPASSED - No new XSD validation errors introduced")
    return True


def _get_schema_path(self, xml_file):
    if xml_file.name in self.SCHEMA_MAPPINGS:
        return self.schemas_dir / self.SCHEMA_MAPPINGS[xml_file.name]
    if xml_file.suffix == ".rels":
        return self.schemas_dir / self.SCHEMA_MAPPINGS[".rels"]
    if "charts/" in str(xml_file) and xml_file.name.startswith("chart"):
        return self.schemas_dir / self.SCHEMA_MAPPINGS["chart"]
    if "theme/" in str(xml_file) and xml_file.name.startswith("theme"):
        return self.schemas_dir / self.SCHEMA_MAPPINGS["theme"]
    if xml_file.parent.name in self.MAIN_CONTENT_FOLDERS:
        return self.schemas_dir / self.SCHEMA_MAPPINGS[xml_file.parent.name]
    return None


def _clean_ignorable_namespaces(self, xml_doc):
    xml_copy = lxml.etree.fromstring(lxml.etree.tostring(xml_doc, encoding="unicode"))
    for elem in xml_copy.iter():
        attrs_to_remove = []
        for attr in elem.attrib:
            if "{" in attr and attr.split("}")[0][1:] not in self.OOXML_NAMESPACES:
                attrs_to_remove.append(attr)
        for attr in attrs_to_remove:
            del elem.attrib[attr]
    self._remove_ignorable_elements(xml_copy)
    return lxml.etree.ElementTree(xml_copy)


def _remove_ignorable_elements(self, root):
    elements_to_remove = []
    for elem in list(root):
        if not hasattr(elem, "tag") or callable(elem.tag):
            continue
        tag_str = str(elem.tag)
        if tag_str.startswith("{"):
            namespace = tag_str.split("}")[0][1:]
            if namespace not in self.OOXML_NAMESPACES:
                elements_to_remove.append(elem)
                continue
        self._remove_ignorable_elements(elem)
    for elem in elements_to_remove:
        root.remove(elem)


def _preprocess_for_mc_ignorable(self, xml_doc):
    root = xml_doc.getroot()
    ignorable_attr = f"{{{self.MC_NAMESPACE}}}Ignorable"
    if ignorable_attr in root.attrib:
        del root.attrib[ignorable_attr]
    return xml_doc


def _validate_single_file_xsd(self, xml_file, base_path):
    schema_path = self._get_schema_path(xml_file)
    if not schema_path:
        return None, None
    try:
        with open(schema_path, "rb") as xsd_file:
            parser = lxml.etree.XMLParser()
            xsd_doc = lxml.etree.parse(xsd_file, parser=parser, base_url=str(schema_path))
            schema = lxml.etree.XMLSchema(xsd_doc)
        with open(xml_file, "r") as xml_handle:
            xml_doc = lxml.etree.parse(xml_handle)
        xml_doc, _ = self._remove_template_tags_from_text_nodes(xml_doc)
        xml_doc = self._preprocess_for_mc_ignorable(xml_doc)
        relative_path = xml_file.relative_to(base_path)
        if relative_path.parts and relative_path.parts[0] in self.MAIN_CONTENT_FOLDERS:
            xml_doc = self._clean_ignorable_namespaces(xml_doc)
        if schema.validate(xml_doc):
            return True, set()
        return False, {error.message for error in schema.error_log}
    except Exception as exc:
        return False, {str(exc)}


def _get_original_file_errors(self, xml_file):
    if self.original_file is None:
        return set()
    xml_file = Path(xml_file).resolve()
    relative_path = xml_file.relative_to(self.unpacked_dir.resolve())
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        with zipfile.ZipFile(self.original_file, "r") as zip_ref:
            zip_ref.extractall(temp_path)
        original_xml_file = temp_path / relative_path
        if not original_xml_file.exists():
            return set()
        _, errors = self._validate_single_file_xsd(original_xml_file, temp_path)
        return errors if errors else set()


def _remove_template_tags_from_text_nodes(self, xml_doc):
    warnings = []
    template_pattern = re.compile(r"\{\{[^}]*\}\}")
    xml_copy = lxml.etree.fromstring(lxml.etree.tostring(xml_doc, encoding="unicode"))
    for elem in xml_copy.iter():
        if not hasattr(elem, "tag") or callable(elem.tag):
            continue
        tag_str = str(elem.tag)
        if tag_str.endswith("}t") or tag_str == "t":
            continue
        elem.text = _strip_template_tags(template_pattern, warnings, elem.text, "text content")
        elem.tail = _strip_template_tags(template_pattern, warnings, elem.tail, "tail content")
    return lxml.etree.ElementTree(xml_copy), warnings


def _print_xsd_summary(self, valid_count, skipped_count, original_error_count, new_errors):
    print(f"Validated {len(self.xml_files)} files:")
    print(f"  - Valid: {valid_count}")
    print(f"  - Skipped (no schema): {skipped_count}")
    if original_error_count:
        print(f"  - With original errors (ignored): {original_error_count}")
    total_new = len([error for error in new_errors if not error.startswith('    ')]) if new_errors else 0
    print(f"  - With NEW errors: {total_new}")


def _strip_template_tags(pattern, warnings, text, content_type):
    if not text:
        return text
    matches = list(pattern.finditer(text))
    if matches:
        for match in matches:
            warnings.append(f"Found template tag in {content_type}: {match.group()}")
        return pattern.sub("", text)
    return text
