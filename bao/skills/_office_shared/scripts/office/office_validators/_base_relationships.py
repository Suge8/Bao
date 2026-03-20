"""Relationship and content-type helpers for BaseSchemaValidator."""

from __future__ import annotations

import lxml.etree

from ._base_relationship_utils import (
    DuplicateIdContext,
    IdRecord,
    find_id_value,
    record_file_id,
    record_global_id,
)


def validate_unique_ids(self):
    errors = []
    global_ids = {}
    for xml_file in self.xml_files:
        try:
            root = lxml.etree.parse(str(xml_file)).getroot()
            file_ids = {}
            mc_elements = root.xpath(".//mc:AlternateContent", namespaces={"mc": self.MC_NAMESPACE})
            for elem in mc_elements:
                elem.getparent().remove(elem)
            for elem in root.iter():
                tag = elem.tag.split("}")[-1].lower() if "}" in elem.tag else elem.tag.lower()
                if tag not in self.UNIQUE_ID_REQUIREMENTS:
                    continue
                in_excluded_container = any(
                    ancestor.tag.split("}")[-1].lower() in self.EXCLUDED_ID_CONTAINERS
                    for ancestor in elem.iterancestors()
                )
                if in_excluded_container:
                    continue
                attr_name, scope = self.UNIQUE_ID_REQUIREMENTS[tag]
                id_value = find_id_value(elem, attr_name)
                if id_value is None:
                    continue
                xml_rel_path = xml_file.relative_to(self.unpacked_dir)
                if scope == "global":
                    record_global_id(
                        errors,
                        global_ids,
                        id_value,
                        IdRecord(xml_path=xml_rel_path, line=elem.sourceline, tag=tag),
                    )
                    continue
                record_file_id(
                    errors,
                    file_ids,
                    id_value,
                    DuplicateIdContext(
                        xml_path=xml_rel_path,
                        line=elem.sourceline,
                        tag=tag,
                        attr_name=attr_name,
                    ),
                )
        except (lxml.etree.XMLSyntaxError, Exception) as exc:
            errors.append(f"  {xml_file.relative_to(self.unpacked_dir)}: Error: {exc}")
    if errors:
        print(f"FAILED - Found {len(errors)} ID uniqueness violations:")
        for error in errors:
            print(error)
        return False
    if self.verbose:
        print("PASSED - All required IDs are unique")
    return True


def validate_file_references(self):
    errors = []
    rels_files = list(self.unpacked_dir.rglob("*.rels"))
    if not rels_files:
        if self.verbose:
            print("PASSED - No .rels files found")
        return True

    all_files = [
        path.resolve()
        for path in self.unpacked_dir.rglob("*")
        if path.is_file() and path.name != "[Content_Types].xml" and not path.name.endswith(".rels")
    ]
    all_referenced_files = set()
    if self.verbose:
        print(f"Found {len(rels_files)} .rels files and {len(all_files)} target files")

    for rels_file in rels_files:
        try:
            rels_root = lxml.etree.parse(str(rels_file)).getroot()
            referenced_files, broken_refs = _collect_relationship_targets(self, rels_root, rels_file)
            all_referenced_files.update(referenced_files)
            if broken_refs:
                rel_path = rels_file.relative_to(self.unpacked_dir)
                for broken_ref, line_num in broken_refs:
                    errors.append(f"  {rel_path}: Line {line_num}: Broken reference to {broken_ref}")
        except Exception as exc:
            rel_path = rels_file.relative_to(self.unpacked_dir)
            errors.append(f"  Error parsing {rel_path}: {exc}")

    for unref_file in sorted(set(all_files) - all_referenced_files):
        errors.append(f"  Unreferenced file: {unref_file.relative_to(self.unpacked_dir)}")

    if errors:
        print(f"FAILED - Found {len(errors)} relationship validation errors:")
        for error in errors:
            print(error)
        print(
            "CRITICAL: These errors will cause the document to appear corrupt. "
            + "Broken references MUST be fixed, and unreferenced files MUST be referenced or removed."
        )
        return False
    if self.verbose:
        print("PASSED - All references are valid and all files are properly referenced")
    return True


def validate_all_relationship_ids(self):
    errors = []
    for xml_file in self.xml_files:
        if xml_file.suffix == ".rels":
            continue
        rels_file = xml_file.parent / "_rels" / f"{xml_file.name}.rels"
        if not rels_file.exists():
            continue
        try:
            rid_to_type = _load_relationship_types(self, rels_file, errors)
            xml_root = lxml.etree.parse(str(xml_file)).getroot()
            _validate_relationship_refs(self, xml_file, xml_root, rid_to_type, errors)
        except Exception as exc:
            errors.append(f"  Error processing {xml_file.relative_to(self.unpacked_dir)}: {exc}")
    if errors:
        print(f"FAILED - Found {len(errors)} relationship ID reference errors:")
        for error in errors:
            print(error)
        print("\nThese ID mismatches will cause the document to appear corrupt!")
        return False
    if self.verbose:
        print("PASSED - All relationship ID references are valid")
    return True


def _get_expected_relationship_type(self, element_name):
    elem_lower = element_name.lower()
    if elem_lower in self.ELEMENT_RELATIONSHIP_TYPES:
        return self.ELEMENT_RELATIONSHIP_TYPES[elem_lower]
    if elem_lower.endswith("id") and len(elem_lower) > 2:
        prefix = elem_lower[:-2]
        if prefix.endswith(("master", "layout")):
            return prefix.lower()
        return "slide" if prefix == "sld" else prefix.lower()
    if elem_lower.endswith("reference") and len(elem_lower) > 9:
        return elem_lower[:-9].lower()
    return None


def validate_content_types(self):
    errors = []
    content_types_file = self.unpacked_dir / "[Content_Types].xml"
    if not content_types_file.exists():
        print("FAILED - [Content_Types].xml file not found")
        return False
    try:
        root = lxml.etree.parse(str(content_types_file)).getroot()
        declared_parts = {
            part_name.lstrip("/")
            for override in root.findall(f".//{{{self.CONTENT_TYPES_NAMESPACE}}}Override")
            if (part_name := override.get("PartName")) is not None
        }
        declared_extensions = {
            extension.lower()
            for default in root.findall(f".//{{{self.CONTENT_TYPES_NAMESPACE}}}Default")
            if (extension := default.get("Extension")) is not None
        }
        _validate_declared_xml_parts(self, declared_parts, errors)
        _validate_binary_extensions(self, declared_extensions, errors)
    except Exception as exc:
        errors.append(f"  Error parsing [Content_Types].xml: {exc}")
    if errors:
        print(f"FAILED - Found {len(errors)} content type declaration errors:")
        for error in errors:
            print(error)
        return False
    if self.verbose:
        print("PASSED - All content files are properly declared in [Content_Types].xml")
    return True
def _collect_relationship_targets(validator, rels_root, rels_file):
    rels_dir = rels_file.parent
    referenced_files = set()
    broken_refs = []
    for rel in rels_root.findall(".//ns:Relationship", namespaces={"ns": validator.PACKAGE_RELATIONSHIPS_NAMESPACE}):
        target = rel.get("Target")
        if not target or target.startswith(("http", "mailto:")):
            continue
        target_path = _resolve_target_path(validator, rels_file, rels_dir, target)
        try:
            target_path = target_path.resolve()
            if target_path.exists() and target_path.is_file():
                referenced_files.add(target_path)
            else:
                broken_refs.append((target, rel.sourceline))
        except (OSError, ValueError):
            broken_refs.append((target, rel.sourceline))
    return referenced_files, broken_refs


def _resolve_target_path(validator, rels_file, rels_dir, target):
    if target.startswith("/"):
        return validator.unpacked_dir / target.lstrip("/")
    if rels_file.name == ".rels":
        return validator.unpacked_dir / target
    return rels_dir.parent / target


def _load_relationship_types(validator, rels_file, errors):
    rels_root = lxml.etree.parse(str(rels_file)).getroot()
    rid_to_type = {}
    for rel in rels_root.findall(f".//{{{validator.PACKAGE_RELATIONSHIPS_NAMESPACE}}}Relationship"):
        rid = rel.get("Id")
        rel_type = rel.get("Type", "")
        if not rid:
            continue
        if rid in rid_to_type:
            errors.append(
                f"  {rels_file.relative_to(validator.unpacked_dir)}: Line {rel.sourceline}: "
                f"Duplicate relationship ID '{rid}' (IDs must be unique)"
            )
        rid_to_type[rid] = rel_type.split("/")[-1] if "/" in rel_type else rel_type
    return rid_to_type


def _validate_relationship_refs(validator, xml_file, xml_root, rid_to_type, errors):
    rel_path = xml_file.relative_to(validator.unpacked_dir)
    for elem in xml_root.iter():
        elem_name = elem.tag.split("}")[-1] if "}" in elem.tag else elem.tag
        for attr_name in ("id", "embed", "link"):
            rid_attr = elem.get(f"{{{validator.OFFICE_RELATIONSHIPS_NAMESPACE}}}{attr_name}")
            if not rid_attr:
                continue
            if rid_attr not in rid_to_type:
                sample = ", ".join(sorted(rid_to_type.keys())[:5])
                suffix = "..." if len(rid_to_type) > 5 else ""
                errors.append(
                    f"  {rel_path}: Line {elem.sourceline}: <{elem_name}> r:{attr_name} references non-existent relationship '{rid_attr}' "
                    f"(valid IDs: {sample}{suffix})"
                )
                continue
            if attr_name != "id" or not validator.ELEMENT_RELATIONSHIP_TYPES:
                continue
            expected_type = validator._get_expected_relationship_type(elem_name)
            actual_type = rid_to_type[rid_attr]
            if expected_type and expected_type not in actual_type.lower():
                errors.append(
                    f"  {rel_path}: Line {elem.sourceline}: <{elem_name}> references '{rid_attr}' which points to '{actual_type}' "
                    f"but should point to a '{expected_type}' relationship"
                )


def _validate_declared_xml_parts(validator, declared_parts, errors):
    declarable_roots = {"sld", "sldLayout", "sldMaster", "presentation", "document", "workbook", "worksheet", "theme"}
    for xml_file in validator.xml_files:
        path_str = str(xml_file.relative_to(validator.unpacked_dir)).replace("\\", "/")
        if any(skip in path_str for skip in [".rels", "[Content_Types]", "docProps/", "_rels/"]):
            continue
        try:
            root_tag = lxml.etree.parse(str(xml_file)).getroot().tag
        except Exception:
            continue
        root_name = root_tag.split("}")[-1] if "}" in root_tag else root_tag
        if root_name in declarable_roots and path_str not in declared_parts:
            errors.append(f"  {path_str}: File with <{root_name}> root not declared in [Content_Types].xml")


def _validate_binary_extensions(validator, declared_extensions, errors):
    media_extensions = {
        "png": "image/png",
        "jpg": "image/jpeg",
        "jpeg": "image/jpeg",
        "gif": "image/gif",
        "bmp": "image/bmp",
        "tiff": "image/tiff",
        "wmf": "image/x-wmf",
        "emf": "image/x-emf",
    }
    for file_path in [path for path in validator.unpacked_dir.rglob("*") if path.is_file()]:
        if file_path.suffix.lower() in {".xml", ".rels"} or file_path.name == "[Content_Types].xml":
            continue
        if "_rels" in file_path.parts or "docProps" in file_path.parts:
            continue
        extension = file_path.suffix.lstrip(".").lower()
        if extension and extension not in declared_extensions and extension in media_extensions:
            relative_path = file_path.relative_to(validator.unpacked_dir)
            errors.append(
                f'  {relative_path}: File with extension \'{extension}\' not declared in [Content_Types].xml - should add: <Default Extension="{extension}" ContentType="{media_extensions[extension]}"/>'
            )
