"""Core XML validation helpers for BaseSchemaValidator."""

from __future__ import annotations

import lxml.etree


def repair_whitespace_preservation(self) -> int:
    repairs = 0
    for xml_file in self.xml_files:
        try:
            content = xml_file.read_text(encoding="utf-8")
            dom = self._minidom.parseString(content)
            modified = False
            for elem in dom.getElementsByTagName("*"):
                if elem.tagName.endswith(":t") and elem.firstChild:
                    text = elem.firstChild.nodeValue
                    if not text or not (text.startswith((" ", "\t")) or text.endswith((" ", "\t"))):
                        continue
                    if elem.getAttribute("xml:space") == "preserve":
                        continue
                    elem.setAttribute("xml:space", "preserve")
                    text_preview = repr(text[:30]) + "..." if len(text) > 30 else repr(text)
                    print(
                        f"  Repaired: {xml_file.name}: Added xml:space='preserve' to {elem.tagName}: {text_preview}"
                    )
                    repairs += 1
                    modified = True
            if modified:
                xml_file.write_bytes(dom.toxml(encoding="UTF-8"))
        except Exception:
            pass
    return repairs


def validate_xml(self):
    errors = []
    for xml_file in self.xml_files:
        try:
            lxml.etree.parse(str(xml_file))
        except lxml.etree.XMLSyntaxError as exc:
            errors.append(f"  {xml_file.relative_to(self.unpacked_dir)}: Line {exc.lineno}: {exc.msg}")
        except Exception as exc:
            errors.append(f"  {xml_file.relative_to(self.unpacked_dir)}: Unexpected error: {exc}")
    if errors:
        print(f"FAILED - Found {len(errors)} XML violations:")
        for error in errors:
            print(error)
        return False
    if self.verbose:
        print("PASSED - All XML files are well-formed")
    return True


def validate_namespaces(self):
    errors = []
    for xml_file in self.xml_files:
        try:
            root = lxml.etree.parse(str(xml_file)).getroot()
            declared = set(root.nsmap.keys()) - {None}
            for attr_val in [value for key, value in root.attrib.items() if key.endswith("Ignorable")]:
                undeclared = set(attr_val.split()) - declared
                errors.extend(
                    f"  {xml_file.relative_to(self.unpacked_dir)}: Namespace '{ns}' in Ignorable but not declared"
                    for ns in undeclared
                )
        except lxml.etree.XMLSyntaxError:
            continue
    if errors:
        print(f"FAILED - {len(errors)} namespace issues:")
        for error in errors:
            print(error)
        return False
    if self.verbose:
        print("PASSED - All namespace prefixes properly declared")
    return True
