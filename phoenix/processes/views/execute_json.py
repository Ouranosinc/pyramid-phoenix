import types
from pyramid.view import view_config, view_defaults

from owslib.wps import ComplexData

from phoenix.utils import wps_describe_url

from phoenix.processes.views.execute import ExecuteProcess
from phoenix.wps import appstruct_to_inputs

import logging
logger = logging.getLogger(__name__)

@view_defaults(permission='view', layout='default')
class ExecuteProcessJson(ExecuteProcess):
    def __init__(self, request):
        self.exception = None
        try:
            ExecuteProcess.__init__(self, request)
        except Exception as e:
            #Cannot initialized the process specified in the request
            self.exception = e

    def jsonify(self, value):
        # ComplexData type
        if isinstance(value, ComplexData):
            return {'mimeType': value.mimeType, 'encoding': value.encoding, 'schema': value.schema}
        # other type
        else:
            return value

    @view_config(route_name='processes_execute', request_method='POST', renderer='json', accept='application/json')
    def execute(self):
        inputs = []
        async = True
        try:
            if self.exception:
                raise self.exception

            if 'submit' in self.request.POST:
                form = self.generate_form()
                controls = self.request.POST.items()
                controls = [control for control in controls if 'qqfile' not in control[0]]
                logger.debug("before validate %s", controls)
                try:
                    appstruct = form.validate(controls)
                except Exception as e:
                    raise Exception(str(form.error))

                logger.debug("before execute %s", appstruct)
                inputs = appstruct_to_inputs(self.request, appstruct)
                async = appstruct.get('_async_check', True)
            elif self.request.content_type == 'application/json':
                for key, values in self.request.json_body.items():
                    if not isinstance(values, types.ListType):
                        values = [values]
                    for value in values:
                        inputs.append((key, value))
            else:
                raise Exception('Request content type must be form-data or application/json')

            task_id = ExecuteProcess.execute(self, inputs=inputs, async=async)
        except Exception as e:
            logger.exception('validation of execute view failed.')
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

    @view_config(route_name='processes_execute', request_method='GET', renderer='json', accept='application/json')
    def get_capabilities(self):
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
