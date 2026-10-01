"""Bounded source-document routes inside the existing launch grant/token boundary."""
from fastapi import UploadFile, File, Form, Query
from fastapi.responses import Response
from starlette.concurrency import run_in_threadpool

from storyboarder.application.documents import Documents
from storyboarder.application.source_workflows import SourceWorkflows
from storyboarder.application.provenance import Provenance
from storyboarder.domain.documents import MAX_DOCUMENT_BYTES
from storyboarder.domain.errors import StoryboardError


def install_document_routes(app, launch):
    prefix = '/api/v1/projects/{project_id}'

    @app.get(prefix+'/documents')
    def documents(project_id: str, kind: str | None = None, query: str = '', archived: bool = False,
                  limit: int = Query(100, ge=1, le=1000), offset: int = Query(0, ge=0)):
        return Documents(launch.service(project_id)).list(kind, query, archived, limit, offset)

    @app.post(prefix+'/documents/upload', status_code=201)
    async def upload_document(project_id: str, file: UploadFile = File(...), format: str = Form(...),
                              document_id: str = Form(''), revision: int | None = Form(None), label: str = Form('Imported draft')):
        service = launch.service(project_id)
        try:
            raw = await file.read(MAX_DOCUMENT_BYTES+1)
            if len(raw) > MAX_DOCUMENT_BYTES:
                raise StoryboardError('A source document must be no larger than 20 MiB.')
            return await run_in_threadpool(Documents(service).import_bytes, raw, file.filename or 'source.json',
                                           format, document_id or None, revision, label)
        finally:
            await file.close()

    @app.get(prefix+'/documents/{document_id}')
    def document(project_id: str, document_id: str):
        return Documents(launch.service(project_id)).show(document_id)

    @app.get(prefix+'/documents/{document_id}/versions')
    def versions(project_id: str, document_id: str, limit: int = Query(100, ge=1, le=1000), offset: int = Query(0, ge=0)):
        return Documents(launch.service(project_id)).versions(document_id, limit, offset)

    @app.get(prefix+'/documents/{document_id}/tree')
    def tree(project_id: str, document_id: str, version_id: str | None = None, query: str = '',
             limit: int = Query(100, ge=1, le=1000), offset: int = Query(0, ge=0)):
        return SourceWorkflows(launch.service(project_id)).tree(document_id, version_id, limit, offset, query)

    @app.get(prefix+'/versions/{version_id}')
    def version(project_id: str, version_id: str):
        return Documents(launch.service(project_id)).version(version_id)

    @app.get(prefix+'/versions/{version_id}/children')
    def children(project_id: str, version_id: str, parent_id: str | None = None,
                 limit: int = Query(100, ge=1, le=1000), offset: int = Query(0, ge=0)):
        return Documents(launch.service(project_id)).children(version_id, parent_id, limit, offset)

    @app.get(prefix+'/versions/{version_id}/source')
    def source(project_id: str, version_id: str):
        raw = Documents(launch.service(project_id)).source_bytes(version_id)
        return Response(raw, media_type='application/json', headers={'Content-Disposition': 'attachment; filename="source.json"'})

    @app.get(prefix+'/nodes/{node_id}')
    def node(project_id: str, node_id: str):
        return Documents(launch.service(project_id)).node(node_id)

    @app.get(prefix+'/provenance/{endpoint_type}/{endpoint_id}')
    def provenance(project_id: str, endpoint_type: str, endpoint_id: str, direction: str = 'both',
                   max_depth: int = Query(6, ge=1, le=20), limit: int = Query(100, ge=1, le=500)):
        return Provenance(launch.service(project_id)).trace(endpoint_type, endpoint_id, direction, max_depth, limit)

    @app.get(prefix+'/annotations/{endpoint_type}/{endpoint_id}')
    def annotations(project_id: str, endpoint_type: str, endpoint_id: str,
                    limit: int = Query(100, ge=1, le=1000), offset: int = Query(0, ge=0)):
        return Provenance(launch.service(project_id)).annotations(endpoint_type, endpoint_id, limit, offset)

    @app.get(prefix+'/coverage')
    def coverage(project_id: str, limit: int = Query(100, ge=1, le=1000)):
        return Provenance(launch.service(project_id)).coverage(limit)
