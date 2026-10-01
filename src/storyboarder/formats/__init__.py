"""Format adapters never execute embedded content or resolve remote media."""
from storyboarder.domain.documents import decode_document
from storyboarder.domain.errors import StoryboardError


def parse(raw: bytes, format: str):
    payload = decode_document(raw)
    if format == 'screenjson':
        from .screenjson import parse_screenjson
        return parse_screenjson(payload).check()
    if format == 'otio':
        from .otio import parse_otio
        return parse_otio(payload).check()
    raise StoryboardError('Choose the screenjson or otio JSON format.')
