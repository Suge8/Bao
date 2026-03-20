from __future__ import annotations

import lxml.etree


def validate(self):
    checks = [
        self.validate_xml,
        self.validate_namespaces,
        self.validate_unique_ids,
        self.validate_file_references,
        self.validate_content_types,
        self.validate_against_xsd,
        self.validate_whitespace_preservation,
        self.validate_deletions,
        self.validate_insertions,
        self.validate_all_relationship_ids,
        self.validate_id_constraints,
        self.validate_comment_markers,
    ]
    all_valid = True
    for check in checks:
        if not check():
            all_valid = False
    self.compare_paragraph_counts()
    return all_valid


def validate_whitespace_preservation(self):
    errors = []
    for xml_file in self.xml_files:
        if xml_file.name != "document.xml":
            continue
        try:
            root = lxml.etree.parse(str(xml_file)).getroot()
            for elem in root.iter(f"{{{self.WORD_2006_NAMESPACE}}}t"):
                if not elem.text:
                    continue
                text = elem.text
                if not (_has_edge_whitespace(text)):
                    continue
                xml_space_attr = f"{{{self.XML_NAMESPACE}}}space"
                if elem.attrib.get(xml_space_attr) == "preserve":
                    continue
                text_preview = repr(text)[:50] + "..." if len(repr(text)) > 50 else repr(text)
                errors.append(
                    f"  {xml_file.relative_to(self.unpacked_dir)}: Line {elem.sourceline}: "
                    f"w:t element with whitespace missing xml:space='preserve': {text_preview}"
                )
        except (lxml.etree.XMLSyntaxError, Exception) as exc:
            errors.append(f"  {xml_file.relative_to(self.unpacked_dir)}: Error: {exc}")
    return _report(self, errors, "whitespace preservation", "All whitespace is properly preserved")


def validate_deletions(self):
    errors = []
    for xml_file in self.xml_files:
        if xml_file.name != "document.xml":
            continue
        try:
            root = lxml.etree.parse(str(xml_file)).getroot()
            namespaces = {"w": self.WORD_2006_NAMESPACE}
            for t_elem in root.xpath(".//w:del//w:t", namespaces=namespaces):
                if t_elem.text:
                    errors.append(
                        f"  {xml_file.relative_to(self.unpacked_dir)}: Line {t_elem.sourceline}: <w:t> found within <w:del>: {_preview(t_elem.text)}"
                    )
            for instr_elem in root.xpath(".//w:del//w:instrText", namespaces=namespaces):
                errors.append(
                    f"  {xml_file.relative_to(self.unpacked_dir)}: Line {instr_elem.sourceline}: <w:instrText> found within <w:del> (use <w:delInstrText>): {_preview(instr_elem.text or '')}"
                )
        except (lxml.etree.XMLSyntaxError, Exception) as exc:
            errors.append(f"  {xml_file.relative_to(self.unpacked_dir)}: Error: {exc}")
    return _report(self, errors, "deletion validation", "No w:t elements found within w:del elements")


def count_paragraphs_in_unpacked(self):
    return _count_document_paragraphs(self, self.xml_files, self.unpacked_dir)


def count_paragraphs_in_original(self):
    return _count_original_paragraphs(self)


def validate_insertions(self):
    errors = []
    for xml_file in self.xml_files:
        if xml_file.name != "document.xml":
            continue
        try:
            root = lxml.etree.parse(str(xml_file)).getroot()
            namespaces = {"w": self.WORD_2006_NAMESPACE}
            invalid_elements = root.xpath(".//w:ins//w:delText[not(ancestor::w:del)]", namespaces=namespaces)
            for elem in invalid_elements:
                errors.append(
                    f"  {xml_file.relative_to(self.unpacked_dir)}: Line {elem.sourceline}: <w:delText> within <w:ins>: {_preview(elem.text or '')}"
                )
        except (lxml.etree.XMLSyntaxError, Exception) as exc:
            errors.append(f"  {xml_file.relative_to(self.unpacked_dir)}: Error: {exc}")
    return _report(self, errors, "insertion validation", "No w:delText elements within w:ins elements")


def compare_paragraph_counts(self):
    original_count = self.count_paragraphs_in_original()
    new_count = self.count_paragraphs_in_unpacked()
    diff = new_count - original_count
    diff_str = f"+{diff}" if diff > 0 else str(diff)
    print(f"\nParagraphs: {original_count} → {new_count} ({diff_str})")


def _parse_id_value(self, val: str, base: int = 16) -> int:
    return int(val, base)


def _has_edge_whitespace(text: str) -> bool:
    return text[:1] in {" ", "\t", "\n", "\r"} or text[-1:] in {" ", "\t", "\n", "\r"}


def _preview(text: str) -> str:
    rendered = repr(text)
    return rendered[:50] + "..." if len(rendered) > 50 else rendered


def _report(self, errors: list[str], label: str, success_message: str) -> bool:
    if errors:
        print(f"FAILED - Found {len(errors)} {label} violations:")
        for error in errors:
            print(error)
        return False
    if self.verbose:
        print(f"PASSED - {success_message}")
    return True


def _count_document_paragraphs(self, xml_files, unpacked_dir) -> int:
    count = 0
    for xml_file in xml_files:
        if xml_file.name != "document.xml":
            continue
        try:
            root = lxml.etree.parse(str(xml_file)).getroot()
            count = len(root.findall(f".//{{{self.WORD_2006_NAMESPACE}}}p"))
        except Exception as exc:
            print(f"Error counting paragraphs in unpacked document: {exc}")
    return count


def _count_original_paragraphs(self) -> int:
    import tempfile
    import zipfile

    if self.original_file is None:
        return 0
    try:
        with tempfile.TemporaryDirectory() as temp_dir:
            with zipfile.ZipFile(self.original_file, "r") as zip_ref:
                zip_ref.extractall(temp_dir)
            root = lxml.etree.parse(temp_dir + "/word/document.xml").getroot()
            return len(root.findall(f".//{{{self.WORD_2006_NAMESPACE}}}p"))
    except Exception as exc:
        print(f"Error counting paragraphs in original document: {exc}")
        return 0
