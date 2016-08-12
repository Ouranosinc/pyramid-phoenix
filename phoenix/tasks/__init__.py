from pyramid_celery import celery_app as app

from owslib.wps import WebProcessingService, ComplexDataInput
from owslib.util import build_get_url
import json
import yaml
import uuid
import urllib
from datetime import datetime

from phoenix.db import mongodb
from phoenix.security import generate_access_token
from phoenix.events import JobFinished

from celery.utils.log import get_task_logger
logger = get_task_logger(__name__)


def task_result(task_id):
    return app.AsyncResult(task_id)


def log(job):
    log_msg = '{0:3d}%: {1}'.format(job.get('progress'), job.get('status_message'))
    if 'log' not in job:
        job['log'] = []
    # skip same log messages
    if len(job['log']) == 0 or job['log'][-1] != log_msg:
        job['log'].append(log_msg)
        logger.info(log_msg)


def log_error(job, error):
    log_msg = 'ERROR: {0.text} - code={0.code} - locator={0.locator}'.format(error)
    if 'log' not in job:
        job['log'] = []
    # skip same log messages
    if len(job['log']) == 0 or job['log'][-1] != log_msg:
        job['log'].append(log_msg)
        logger.error(log_msg)


def add_job(db, userid, task_id, service, title, abstract, status_location, is_workflow=False, caption=None):
    tags = ['dev']
    if is_workflow:
        tags.append('workflow')
    else:
        tags.append('single')
    job = dict(
        identifier=uuid.uuid4().get_hex(),
        task_id=task_id,
        userid=userid,
        is_workflow=is_workflow,
        service=service,
        title=title,
        abstract=abstract,
        status_location=status_location,
        created=datetime.now(),
        tags=tags,
        caption=caption,
        status="ProcessAccepted",
        )
    db.jobs.insert(job)
    return job


def get_access_token(userid):
    registry = app.conf['PYRAMID_REGISTRY']
    db = mongodb(registry)

    # update access token
    generate_access_token(registry, userid)
    
    user = db.users.find_one(dict(identifier=userid))
    return user.get('twitcher_token')


def wps_headers(userid):
    headers = {}
    if userid:
        access_token = get_access_token(userid)
        if access_token is not None:
            headers['Access-Token'] = access_token
    return headers


@app.task(bind=True)
def execute_workflow(self, userid, url, workflow, caption=None):
    registry = app.conf['PYRAMID_REGISTRY']
    db = mongodb(registry)

    # generate and run dispel workflow
    # TODO: fix owslib wps for unicode/yaml parameters
    logger.debug('workflow=%s', workflow)
    headers=wps_headers(userid)
    # TODO: handle access token in workflow
    workflow['worker']['url'] = build_get_url(workflow['worker']['url'], {'access_token': headers.get('Access-Token', '') })
    logger.debug('workflow_mod=%s', workflow)
    inputs=[('workflow', ComplexDataInput(json.dumps(workflow), mimeType="text/yaml", encoding="UTF-8") )]
    logger.debug('inputs=%s', inputs)
    outputs=[('output', True), ('logfile', True)]
    
    wps = WebProcessingService(url=url, skip_caps=True, verify=False, headers=headers)
    worker_wps = WebProcessingService(url=workflow['worker']['url'], skip_caps=False, verify=False)
    execution = wps.execute(identifier='workflow', inputs=inputs, output=outputs, lineage=True)
    
    job = add_job(db, userid,
                  task_id=self.request.id,
                  is_workflow=True,
                  service=worker_wps.identification.title,
                  title=workflow['worker']['identifier'],
                  abstract='',
                  caption=caption,
                  status_location=execution.statusLocation)

    while execution.isNotComplete():
        try:
            execution.checkStatus(sleepSecs=3)
            job['status'] = execution.getStatus()
            job['status_message'] = execution.statusMessage
            job['progress'] = execution.percentCompleted
            duration = datetime.now() - job.get('created', datetime.now())
            job['duration'] = str(duration).split('.')[0]
            if execution.isComplete():
                job['finished'] = datetime.now()
                if execution.isSucceded():
                    for output in execution.processOutputs:
                        if 'output' == output.identifier:
                            result = yaml.load(urllib.urlopen(output.reference))
                            job['worker_status_location'] = result['worker']['status_location']
                    job['progress'] = 100
                    log(job)
                else:
                    job['status_message'] = '\n'.join(error.text for error in execution.errors)
                    for error in execution.errors:
                        log_error(job, error)
            else:
                log(job)
        except:
            logger.exception("Could not read status xml document.")
        else:
            db.jobs.update({'identifier': job['identifier']}, job)
    registry.notify(JobFinished(job))
    return execution.getStatus()




