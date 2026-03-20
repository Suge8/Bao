"""Add comments to DOCX documents.

Usage:
    python comment.py unpacked/ 0 "Comment text"
    python comment.py unpacked/ 1 "Reply text" --parent 0

Text should be pre-escaped XML (e.g., &amp; for &, &#x2019; for smart quotes).

After running, add markers to document.xml:
  <w:commentRangeStart w:id="0"/>
  ... commented content ...
  <w:commentRangeEnd w:id="0"/>
  <w:r><w:rPr><w:rStyle w:val="CommentReference"/></w:rPr><w:commentReference w:id="0"/></w:r>
"""

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path

from ._comment_helpers import (
    COMMENT_MARKER_TEMPLATE,
    COMMENT_XML,
    REPLY_MARKER_TEMPLATE,
    append_xml,
    ensure_comment_content_types,
    ensure_comment_relationships,
    ensure_template_copy,
    find_para_id,
    generate_hex_id,
    timestamp_utc,
)


@dataclass(slots=True, frozen=True)
class CommentRequest:
    unpacked_dir: str
    comment_id: int
    text: str
    author: str
    initials: str
    parent_id: int | None


def add_comment(*args, **kwargs) -> tuple[str, str]:
    if args and isinstance(args[0], CommentRequest):
        return _add_comment(args[0])
    unpacked_dir = kwargs.pop("unpacked_dir", args[0] if len(args) > 0 else "")
    comment_id = kwargs.pop("comment_id", args[1] if len(args) > 1 else 0)
    text = kwargs.pop("text", args[2] if len(args) > 2 else "")
    author = kwargs.pop("author", args[3] if len(args) > 3 else "Claude")
    initials = kwargs.pop("initials", args[4] if len(args) > 4 else "C")
    parent_id = kwargs.pop("parent_id", args[5] if len(args) > 5 else None)
    return _add_comment(
        CommentRequest(
            unpacked_dir=unpacked_dir,
            comment_id=comment_id,
            text=text,
            author=author,
            initials=initials,
            parent_id=parent_id,
        )
    )


def _add_comment(request: CommentRequest) -> tuple[str, str]:
    word = Path(request.unpacked_dir) / "word"
    if not word.exists():
        return "", f"Error: {word} not found"

    para_id, durable_id = generate_hex_id(), generate_hex_id()
    ts = timestamp_utc()

    comments = word / "comments.xml"
    first_comment = not comments.exists()
    if first_comment:
        ensure_template_copy(comments, "comments.xml")
        ensure_comment_relationships(Path(request.unpacked_dir))
        ensure_comment_content_types(Path(request.unpacked_dir))
    append_xml(
        comments,
        "w:comments",
        COMMENT_XML.format(
            id=request.comment_id,
            author=request.author,
            date=ts,
            initials=request.initials,
            para_id=para_id,
            text=request.text,
        ),
    )

    ext = word / "commentsExtended.xml"
    ensure_template_copy(ext, "commentsExtended.xml")
    if request.parent_id is not None:
        parent_para = find_para_id(comments, request.parent_id)
        if not parent_para:
            return "", f"Error: Parent comment {request.parent_id} not found"
        append_xml(
            ext,
            "w15:commentsEx",
            f'<w15:commentEx w15:paraId="{para_id}" w15:paraIdParent="{parent_para}" w15:done="0"/>',
        )
    else:
        append_xml(
            ext,
            "w15:commentsEx",
            f'<w15:commentEx w15:paraId="{para_id}" w15:done="0"/>',
        )

    ids = word / "commentsIds.xml"
    ensure_template_copy(ids, "commentsIds.xml")
    append_xml(
        ids,
        "w16cid:commentsIds",
        f'<w16cid:commentId w16cid:paraId="{para_id}" w16cid:durableId="{durable_id}"/>',
    )

    extensible = word / "commentsExtensible.xml"
    ensure_template_copy(extensible, "commentsExtensible.xml")
    append_xml(
        extensible,
        "w16cex:commentsExtensible",
        f'<w16cex:commentExtensible w16cex:durableId="{durable_id}" w16cex:dateUtc="{ts}"/>',
    )

    action = "reply" if request.parent_id is not None else "comment"
    return para_id, f"Added {action} {request.comment_id} (para_id={para_id})"


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="Add comments to DOCX documents")
    p.add_argument("unpacked_dir", help="Unpacked DOCX directory")
    p.add_argument("comment_id", type=int, help="Comment ID (must be unique)")
    p.add_argument("text", help="Comment text")
    p.add_argument("--author", default="Claude", help="Author name")
    p.add_argument("--initials", default="C", help="Author initials")
    p.add_argument("--parent", type=int, help="Parent comment ID (for replies)")
    args = p.parse_args()

    para_id, msg = add_comment(
        args.unpacked_dir,
        args.comment_id,
        args.text,
        args.author,
        args.initials,
        args.parent,
    )
    print(msg)
    if "Error" in msg:
        sys.exit(1)
    cid = args.comment_id
    if args.parent is not None:
        print(REPLY_MARKER_TEMPLATE.format(pid=args.parent, cid=cid))
    else:
        print(COMMENT_MARKER_TEMPLATE.format(cid=cid))
