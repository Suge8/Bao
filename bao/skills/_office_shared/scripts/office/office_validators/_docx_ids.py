from __future__ import annotations

from dataclasses import dataclass

import lxml.etree


def validate_id_constraints(self):
    errors = []
    para_id_attr = f"{{{self.W14_NAMESPACE}}}paraId"
    durable_id_attr = f"{{{self.W16CID_NAMESPACE}}}durableId"
    for xml_file in self.xml_files:
        try:
            for elem in lxml.etree.parse(str(xml_file)).iter():
                if val := elem.get(para_id_attr):
                    if self._parse_id_value(val, base=16) >= 0x80000000:
                        errors.append(f"  {xml_file.name}:{elem.sourceline}: paraId={val} >= 0x80000000")
                if val := elem.get(durable_id_attr):
                    _validate_durable_id(self, DurableIdContext(xml_file=xml_file, elem=elem, value=val, errors=errors))
        except Exception:
            pass
    if errors:
        print(f"FAILED - {len(errors)} ID constraint violations:")
        for error in errors:
            print(error)
    elif self.verbose:
        print("PASSED - All paraId/durableId values within constraints")
    return not errors


def validate_comment_markers(self):
    errors = []
    document_xml, comments_xml = _find_comment_files(self.xml_files)
    if not document_xml:
        if self.verbose:
            print("PASSED - No document.xml found (skipping comment validation)")
        return True
    try:
        doc_root = lxml.etree.parse(str(document_xml)).getroot()
        namespaces = {"w": self.WORD_2006_NAMESPACE}
        range_starts = _collect_ids(IdCollectionContext(root=doc_root, xpath=".//w:commentRangeStart", namespaces=namespaces, namespace=self.WORD_2006_NAMESPACE))
        range_ends = _collect_ids(IdCollectionContext(root=doc_root, xpath=".//w:commentRangeEnd", namespaces=namespaces, namespace=self.WORD_2006_NAMESPACE))
        references = _collect_ids(IdCollectionContext(root=doc_root, xpath=".//w:commentReference", namespaces=namespaces, namespace=self.WORD_2006_NAMESPACE))
        _append_orphan_errors(OrphanErrorContext(errors=errors, label="commentRangeEnd", ids=range_ends - range_starts, counterpart="commentRangeStart"))
        _append_orphan_errors(OrphanErrorContext(errors=errors, label="commentRangeStart", ids=range_starts - range_ends, counterpart="commentRangeEnd"))
        if comments_xml and comments_xml.exists():
            comment_ids = _collect_comment_ids(comments_xml, namespaces, self.WORD_2006_NAMESPACE)
            invalid_refs = (range_starts | range_ends | references) - comment_ids
            for comment_id in sorted(invalid_refs, key=_sort_key):
                if comment_id:
                    errors.append(f'  document.xml: marker id="{comment_id}" references non-existent comment')
    except (lxml.etree.XMLSyntaxError, Exception) as exc:
        errors.append(f"  Error parsing XML: {exc}")
    if errors:
        print(f"FAILED - {len(errors)} comment marker violations:")
        for error in errors:
            print(error)
        return False
    if self.verbose:
        print("PASSED - All comment markers properly paired")
    return True


def repair(self) -> int:
    repairs = super(type(self), self).repair()
    repairs += self.repair_durable_id()
    return repairs


def repair_durable_id(self) -> int:
    repairs = 0
    for xml_file in self.xml_files:
        try:
            content = xml_file.read_text(encoding="utf-8")
            dom = self._minidom.parseString(content)
            modified = False
            for elem in dom.getElementsByTagName("*"):
                if not elem.hasAttribute("w16cid:durableId"):
                    continue
                durable_id = elem.getAttribute("w16cid:durableId")
                needs_repair = _needs_durable_repair(self, xml_file.name, durable_id)
                if not needs_repair:
                    continue
                value = __import__("random").randint(1, 0x7FFFFFFE)
                new_id = str(value) if xml_file.name == "numbering.xml" else f"{value:08X}"
                elem.setAttribute("w16cid:durableId", new_id)
                print(f"  Repaired: {xml_file.name}: durableId {durable_id} → {new_id}")
                repairs += 1
                modified = True
            if modified:
                xml_file.write_bytes(dom.toxml(encoding="UTF-8"))
        except Exception:
            pass
    return repairs


@dataclass(slots=True)
class DurableIdContext:
    xml_file: object
    elem: object
    value: str
    errors: list[str]


@dataclass(slots=True)
class IdCollectionContext:
    root: object
    xpath: str
    namespaces: dict[str, str]
    namespace: str


@dataclass(slots=True)
class OrphanErrorContext:
    errors: list[str]
    label: str
    ids: set[str | None]
    counterpart: str


def _validate_durable_id(self, context: DurableIdContext):
    xml_file = context.xml_file
    elem = context.elem
    val = context.value
    errors = context.errors
    if getattr(xml_file, "name", "") == "numbering.xml":
        try:
            if self._parse_id_value(val, base=10) >= 0x7FFFFFFF:
                errors.append(f"  {xml_file.name}:{elem.sourceline}: durableId={val} >= 0x7FFFFFFF")
        except ValueError:
            errors.append(f"  {xml_file.name}:{elem.sourceline}: durableId={val} must be decimal in numbering.xml")
        return
    if self._parse_id_value(val, base=16) >= 0x7FFFFFFF:
        errors.append(f"  {xml_file.name}:{elem.sourceline}: durableId={val} >= 0x7FFFFFFF")


def _find_comment_files(xml_files):
    document_xml = None
    comments_xml = None
    for xml_file in xml_files:
        if xml_file.name == "document.xml" and "word" in str(xml_file):
            document_xml = xml_file
        elif xml_file.name == "comments.xml":
            comments_xml = xml_file
    return document_xml, comments_xml


def _collect_ids(context: IdCollectionContext):
    return {
        elem.get(f"{{{context.namespace}}}id")
        for elem in context.root.xpath(context.xpath, namespaces=context.namespaces)
    }


def _collect_comment_ids(comments_xml, namespaces, namespace):
    comments_root = lxml.etree.parse(str(comments_xml)).getroot()
    return {elem.get(f"{{{namespace}}}id") for elem in comments_root.xpath(".//w:comment", namespaces=namespaces)}


def _append_orphan_errors(context: OrphanErrorContext):
    for comment_id in sorted(context.ids, key=_sort_key):
        context.errors.append(
            f'  document.xml: {context.label} id="{comment_id}" has no matching {context.counterpart}'
        )


def _sort_key(value):
    return int(value) if value and value.isdigit() else 0


def _needs_durable_repair(self, filename: str, durable_id: str) -> bool:
    if filename == "numbering.xml":
        try:
            return self._parse_id_value(durable_id, base=10) >= 0x7FFFFFFF
        except ValueError:
            return True
    try:
        return self._parse_id_value(durable_id, base=16) >= 0x7FFFFFFF
    except ValueError:
        return True
