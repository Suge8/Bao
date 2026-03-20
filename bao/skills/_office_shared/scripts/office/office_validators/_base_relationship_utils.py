"""Small shared utilities for relationship validation helpers."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True, frozen=True)
class IdRecord:
    xml_path: object
    line: int | None
    tag: str


@dataclass(slots=True, frozen=True)
class DuplicateIdContext:
    xml_path: object
    line: int | None
    tag: str
    attr_name: str


def find_id_value(elem, attr_name):
    for attr, value in elem.attrib.items():
        attr_local = attr.split("}")[-1].lower() if "}" in attr else attr.lower()
        if attr_local == attr_name:
            return value
    return None


def record_global_id(errors, global_ids, id_value, context: IdRecord):
    if id_value in global_ids:
        prev = global_ids[id_value]
        errors.append(
            f"  {context.xml_path}: Line {context.line}: Global ID '{id_value}' in <{context.tag}> "
            f"already used in {prev.xml_path} at line {prev.line} in <{prev.tag}>"
        )
        return
    global_ids[id_value] = context


def record_file_id(errors, file_ids, id_value, context: DuplicateIdContext):
    key = (context.tag, context.attr_name)
    if key not in file_ids:
        file_ids[key] = {}
    if id_value in file_ids[key]:
        prev_line = file_ids[key][id_value]
        errors.append(
            f"  {context.xml_path}: Line {context.line}: Duplicate {context.attr_name}='{id_value}' in <{context.tag}> "
            f"(first occurrence at line {prev_line})"
        )
        return
    file_ids[key][id_value] = context.line
