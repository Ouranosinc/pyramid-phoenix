from pyramid.view import view_config, view_defaults

from owslib.wps import ComplexData

from deform import ValidationFailure

from phoenix.utils import wps_describe_url

from phoenix.processes.views.execute import ExecuteProcess

import logging
logger = logging.getLogger(__name__)

@view_defaults(permission='view', layout='default')
class ExecuteProcessJson(ExecuteProcess):
    def __init__(self, request):
        ExecuteProcess.__init__(self, request)

    def jsonify(self, value):
        # ComplexData type
        if isinstance(value, ComplexData):
            return {'mimeType': value.mimeType, 'encoding': value.encoding, 'schema': value.schema}
        # other type
        else:
            return value

    def process_form(self, form):
        controls = self.request.POST.items()
        try:
            # TODO: uploader puts qqfile in controls
            controls = [control for control in controls if 'qqfile' not in control[0]]
            logger.debug("before validate %s", controls)
            appstruct = form.validate(controls)
            logger.debug("before execute %s", appstruct)
            task_id = self.execute(appstruct)
        except Exception as e:
            logger.exception('validation of exectue view failed.')
            return dict(
                status=520,
                message=str(e),
                task_id=None
            )
        return dict(
            status=200,
            message='OK',
            task_id=task_id
        )

    @view_config(route_name='processes_execute', renderer='json', accept='application/json')
    def view(self):
        if 'submit' in self.request.POST:
            form = self.generate_form()
            return self.process_form(form)




        dataInputs = getattr(self.process, 'dataInputs', [])
        json_inputs = [{'dataType': data_input.dataType,
                        'name': getattr(data_input, 'identifier', ''),
                        'title': getattr(data_input, 'title', ''),
                        'description': getattr(data_input, 'abstract', ''),
                        'defaultValue': self.jsonify(getattr(data_input, 'defaultValue', None)),
                        'minOccurs': getattr(data_input, 'minOccurs', 0),
                        'maxOccurs': getattr(data_input, 'maxOccurs', 0),
                        'allowedValues': [self.jsonify(value) for value in getattr(data_input, 'allowedValues', [])],
                        'supportedValues': [self.jsonify(value) for value in getattr(data_input, 'supportedValues', [])]
                        } for data_input in dataInputs]
        return dict(
            description=getattr(self.process, 'abstract', ''),
            url=wps_describe_url(self.wps.url, self.processid),
            inputs=json_inputs)
