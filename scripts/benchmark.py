#!/usr/bin/env python3
"""Measure a disposable metadata workload. Never runs against a user's project."""
from pathlib import Path
from tempfile import TemporaryDirectory
from time import perf_counter
import argparse
import json
from storyboarder.application.projects import Project
from storyboarder.application.service import Service

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--shots',type=int,default=1000)
    args=parser.parse_args()
    if not 1<=args.shots<=10000:
        raise SystemExit('Use 1–10000 disposable shots.')
    with TemporaryDirectory(prefix='storyboarder-benchmark-') as temporary:
        service=Service(Project.create(Path(temporary)/'project','Disposable benchmark'))
        sequence=service.create_entity('sequence','Sequence')
        scene=service.create_entity('scene','Scene',sequence['id'])
        start=perf_counter()
        for i in range(args.shots):
            service.create_entity('shot',f'Shot {i+1:05}',scene['id'],fields={'action':f'Authored action {i+1}'})
        creation=perf_counter()-start
        start=perf_counter();state=service.state();snapshot=perf_counter()-start
        start=perf_counter();graph=service.graph('story',limit=250);view=perf_counter()-start
        start=perf_counter();filtered=service.graph('story',query=f'Shot {args.shots:05}',limit=250);search=perf_counter()-start
        assert len(graph['nodes'])<=250
        assert len(state['entities'])==args.shots+3
        print(json.dumps({'shots':args.shots,'metadata_records':len(state['entities']),'create_seconds':creation,
                          'snapshot_seconds':snapshot,'graph_seconds':view,'search_seconds':search,
                          'graph_nodes':len(graph['nodes']),'graph_truncated':graph['truncated'],
                          'filtered_nodes':len(filtered['nodes']),'includes_original_image_loading':False},indent=2))
