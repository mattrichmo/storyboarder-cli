"""Versioned document primitives shared by format adapters and storage."""
from dataclasses import dataclass, field
import hashlib
import json
import math
from typing import Any

from .errors import StoryboardError
from .models import dumps

MAX_DOCUMENT_BYTES = 20 * 1024 * 1024
MAX_DOCUMENT_NODES = 100_000
MAX_DOCUMENT_DEPTH = 64


def decode_document(raw: bytes) -> dict:
    if not isinstance(raw, bytes) or not raw or len(raw) > MAX_DOCUMENT_BYTES:
        raise StoryboardError('Use a nonempty UTF-8 document no larger than 20 MiB.')
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError(f'Duplicate JSON property: {key}')
            result[key] = value
        return result
    try:
        data = json.loads(raw.decode('utf-8-sig'), object_pairs_hook=pairs,
                          parse_constant=lambda value: (_ for _ in ()).throw(ValueError(f'Non-finite JSON value: {value}')))
        if not isinstance(data, dict):
            raise ValueError('The document root must be an object.')
        stack = [(data, 0)]
        visited = 0
        while stack:
            value, depth = stack.pop()
            visited += 1
            if depth > MAX_DOCUMENT_DEPTH or visited > 2_000_000:
                raise ValueError('Document structure exceeds the supported depth or size.')
            if isinstance(value, dict):
                if any('\x00' in key for key in value):
                    raise ValueError('JSON property names cannot contain NUL bytes.')
                stack.extend((child, depth + 1) for child in value.values())
            elif isinstance(value, list):
                stack.extend((child, depth + 1) for child in value)
            elif isinstance(value, str) and ('\x00' in value or len(value) > 1_000_000):
                raise ValueError('Document text contains NUL bytes or exceeds one million characters.')
            elif isinstance(value, float) and not math.isfinite(value):
                raise ValueError('Numbers must be finite.')
        return data
    except (UnicodeError, ValueError, RecursionError) as exc:
        raise StoryboardError(f'Invalid document JSON: {exc}') from exc


def content_hash(value: Any) -> str:
    return hashlib.sha256(dumps(value).encode('utf-8')).hexdigest()


def pointer_get(document: dict, pointer: str):
    current = document
    for raw in pointer.split('/')[1:] if pointer else ():
        key = raw.replace('~1', '/').replace('~0', '~')
        current = current[int(key)] if isinstance(current, list) else current[key]
    return current


@dataclass(frozen=True)
class NodeDraft:
    logical_id: str
    parent_logical_id: str | None
    node_type: str
    position: int
    title: str
    text: str
    pointer: str
    payload: dict
    identity: str = 'explicit'


@dataclass
class ParsedDocument:
    kind: str
    format: str
    format_version: str
    title: str
    external_id: str | None
    payload: dict
    nodes: list[NodeDraft]
    warnings: list[dict] = field(default_factory=list)

    def check(self):
        if not self.nodes or len(self.nodes) > MAX_DOCUMENT_NODES:
            raise StoryboardError('A document must have between 1 and 100,000 structural nodes.')
        seen = set()
        for node in self.nodes:
            if node.logical_id in seen:
                raise StoryboardError(f'Duplicate document identity: {node.logical_id}')
            if node.parent_logical_id is not None and node.parent_logical_id not in seen:
                raise StoryboardError('Document nodes must have an earlier parent in the same document.')
            seen.add(node.logical_id)
        return self
