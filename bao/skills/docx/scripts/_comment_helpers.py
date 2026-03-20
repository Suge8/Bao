from __future__ import annotations

import importlib
import random
import shutil
from datetime import datetime, timezone
from pathlib import Path
from xml.dom import minidom as _stdlib_minidom

try:
    _minidom = importlib.import_module("defusedxml.minidom")
except ModuleNotFoundError:
    _minidom = _stdlib_minidom

TEMPLATE_DIR = Path(__file__).parent / "templates"
NS = {
    "w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main",
    "w14": "http://schemas.microsoft.com/office/word/2010/wordml",
    "w15": "http://schemas.microsoft.com/office/word/2012/wordml",
    "w16cid": "http://schemas.microsoft.com/office/word/2016/wordml/cid",
    "w16cex": "http://schemas.microsoft.com/office/word/2018/wordml/cex",
}

COMMENT_XML = """\
<w:comment w:id="{id}" w:author="{author}" w:date="{date}" w:initials="{initials}">
  <w:p w14:paraId="{para_id}" w14:textId="77777777">
    <w:r>
      <w:rPr><w:rStyle w:val="CommentReference"/></w:rPr>
      <w:annotationRef/>
    </w:r>
    <w:r>
      <w:rPr>
        <w:color w:val="000000"/>
        <w:sz w:val="20"/>
        <w:szCs w:val="20"/>
      </w:rPr>
      <w:t>{text}</w:t>
    </w:r>
  </w:p>
</w:comment>"""

COMMENT_MARKER_TEMPLATE = """
Add to document.xml (markers must be direct children of w:p, never inside w:r):
  <w:commentRangeStart w:id="{cid}"/>
  <w:r>...</w:r>
  <w:commentRangeEnd w:id="{cid}"/>
  <w:r><w:rPr><w:rStyle w:val="CommentReference"/></w:rPr><w:commentReference w:id="{cid}"/></w:r>"""

REPLY_MARKER_TEMPLATE = """
Nest markers inside parent {pid}'s markers (markers must be direct children of w:p, never inside w:r):
  <w:commentRangeStart w:id="{pid}"/><w:commentRangeStart w:id="{cid}"/>
  <w:r>...</w:r>
  <w:commentRangeEnd w:id="{cid}"/><w:commentRangeEnd w:id="{pid}"/>
  <w:r><w:rPr><w:rStyle w:val="CommentReference"/></w:rPr><w:commentReference w:id="{pid}"/></w:r>
  <w:r><w:rPr><w:rStyle w:val="CommentReference"/></w:rPr><w:commentReference w:id="{cid}"/></w:r>"""

SMART_QUOTE_ENTITIES = {
    "\u201c": "&#x201C;",
    "\u201d": "&#x201D;",
    "\u2018": "&#x2018;",
    "\u2019": "&#x2019;",
}

COMMENT_RELATIONSHIPS = [
    ("http://schemas.openxmlformats.org/officeDocument/2006/relationships/comments", "comments.xml"),
    ("http://schemas.microsoft.com/office/2011/relationships/commentsExtended", "commentsExtended.xml"),
    ("http://schemas.microsoft.com/office/2016/09/relationships/commentsIds", "commentsIds.xml"),
    ("http://schemas.microsoft.com/office/2018/08/relationships/commentsExtensible", "commentsExtensible.xml"),
]

COMMENT_CONTENT_OVERRIDES = [
    ("/word/comments.xml", "application/vnd.openxmlformats-officedocument.wordprocessingml.comments+xml"),
    ("/word/commentsExtended.xml", "application/vnd.openxmlformats-officedocument.wordprocessingml.commentsExtended+xml"),
    ("/word/commentsIds.xml", "application/vnd.openxmlformats-officedocument.wordprocessingml.commentsIds+xml"),
    ("/word/commentsExtensible.xml", "application/vnd.openxmlformats-officedocument.wordprocessingml.commentsExtensible+xml"),
]


def generate_hex_id() -> str:
    return f"{random.randint(0, 0x7FFFFFFE):08X}"


def encode_smart_quotes(text: str) -> str:
    for char, entity in SMART_QUOTE_ENTITIES.items():
        text = text.replace(char, entity)
    return text


def append_xml(xml_path: Path, root_tag: str, content: str) -> None:
    dom = _minidom.parseString(xml_path.read_text(encoding="utf-8"))
    root = dom.getElementsByTagName(root_tag)[0]
    ns_attrs = " ".join(f'xmlns:{key}="{value}"' for key, value in NS.items())
    wrapper_dom = _minidom.parseString(f"<root {ns_attrs}>{content}</root>")
    for child in wrapper_dom.documentElement.childNodes:
        if child.nodeType == child.ELEMENT_NODE:
            root.appendChild(dom.importNode(child, True))
    xml_path.write_text(encode_smart_quotes(dom.toxml(encoding="UTF-8").decode("utf-8")), encoding="utf-8")


def find_para_id(comments_path: Path, comment_id: int) -> str | None:
    dom = _minidom.parseString(comments_path.read_text(encoding="utf-8"))
    for comment in dom.getElementsByTagName("w:comment"):
        if comment.getAttribute("w:id") != str(comment_id):
            continue
        for para in comment.getElementsByTagName("w:p"):
            if para_id := para.getAttribute("w14:paraId"):
                return para_id
    return None


def get_next_rid(rels_path: Path) -> int:
    dom = _minidom.parseString(rels_path.read_text(encoding="utf-8"))
    max_rid = 0
    for rel in dom.getElementsByTagName("Relationship"):
        rid = rel.getAttribute("Id")
        if rid.startswith("rId"):
            try:
                max_rid = max(max_rid, int(rid[3:]))
            except ValueError:
                pass
    return max_rid + 1


def has_relationship(rels_path: Path, target: str) -> bool:
    dom = _minidom.parseString(rels_path.read_text(encoding="utf-8"))
    return any(rel.getAttribute("Target") == target for rel in dom.getElementsByTagName("Relationship"))


def has_content_type(ct_path: Path, part_name: str) -> bool:
    dom = _minidom.parseString(ct_path.read_text(encoding="utf-8"))
    return any(override.getAttribute("PartName") == part_name for override in dom.getElementsByTagName("Override"))


def ensure_comment_relationships(unpacked_dir: Path) -> None:
    rels_path = unpacked_dir / "word" / "_rels" / "document.xml.rels"
    if not rels_path.exists() or has_relationship(rels_path, "comments.xml"):
        return
    dom = _minidom.parseString(rels_path.read_text(encoding="utf-8"))
    root = dom.documentElement
    next_rid = get_next_rid(rels_path)
    for rel_type, target in COMMENT_RELATIONSHIPS:
        rel = dom.createElement("Relationship")
        rel.setAttribute("Id", f"rId{next_rid}")
        rel.setAttribute("Type", rel_type)
        rel.setAttribute("Target", target)
        root.appendChild(rel)
        next_rid += 1
    rels_path.write_bytes(dom.toxml(encoding="UTF-8"))


def ensure_comment_content_types(unpacked_dir: Path) -> None:
    ct_path = unpacked_dir / "[Content_Types].xml"
    if not ct_path.exists() or has_content_type(ct_path, "/word/comments.xml"):
        return
    dom = _minidom.parseString(ct_path.read_text(encoding="utf-8"))
    root = dom.documentElement
    for part_name, content_type in COMMENT_CONTENT_OVERRIDES:
        override = dom.createElement("Override")
        override.setAttribute("PartName", part_name)
        override.setAttribute("ContentType", content_type)
        root.appendChild(override)
    ct_path.write_bytes(dom.toxml(encoding="UTF-8"))


def ensure_template_copy(target: Path, template_name: str) -> None:
    if not target.exists():
        shutil.copy(TEMPLATE_DIR / template_name, target)


def timestamp_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
