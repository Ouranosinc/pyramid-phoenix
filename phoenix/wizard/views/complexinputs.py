from pyramid.view import view_config
import colander
import deform

from owslib.wps import WebProcessingService

from phoenix.utils import wps_describe_url
from phoenix.wizard.views import Wizard


def includeme(config):
    config.add_route('wizard_complex_inputs', '/wizard/complex_inputs')
    config.add_view('phoenix.wizard.views.complexinputs.ComplexInputs',
                    route_name='wizard_complex_inputs',
                    attr='view',
                    renderer='../templates/wizard/inputs.pt')


@colander.deferred
def deferred_widget(node, kw):
    process = kw.get('process', [])

    choices = []
    for data_input in process.dataInputs:
        if data_input.dataType == 'ComplexData':
            title = data_input.title
            abstract = getattr(data_input, 'abstract', 'No summary')
            if abstract is None:
                abstract = 'No summary'
            mime_types = ', '.join([value.mimeType for value in data_input.supportedValues])
            description = "{0} - {1} ({2})".format(title, abstract, mime_types)
            choices.append((data_input.identifier, description))
    return deform.widget.RadioChoiceWidget(values=choices)


class Schema(colander.MappingSchema):
    identifier = colander.SchemaNode(
        colander.String(),
        title="Input Parameter",
        widget=deferred_widget)


class ComplexInputs(Wizard):
    def __init__(self, request):
        super(ComplexInputs, self).__init__(
            request, name='wizard_complex_inputs',
            title="Choose Input Parameter")
        self.wps = WebProcessingService(
            url=request.route_url('owsproxy', service_name=self.wizard_state.get('wizard_wps')['identifier']),
            verify=False, skip_caps=True)
        self.process = self.wps.describeprocess(self.wizard_state.get('wizard_process')['identifier'])
        self.title = "Choose Input Parameter of {0}".format(self.process.title)

    def breadcrumbs(self):
        breadcrumbs = super(ComplexInputs, self).breadcrumbs()
        breadcrumbs.append(dict(route_path=self.request.route_path(self.name), title=self.title))
        return breadcrumbs

    def schema(self):
        return Schema().bind(process=self.process)

    def success(self, appstruct):
        for inp in self.process.dataInputs:
            if inp.identifier == appstruct.get('identifier'):
                appstruct['mime_types'] = [value.mimeType for value in inp.supportedValues]
        super(ComplexInputs, self).success(appstruct)

    def next_success(self, appstruct):
        self.success(appstruct)
        return self.next('wizard_source')

    def view(self):
        return super(ComplexInputs, self).view()

    def custom_view(self):
        return dict(
            summary_title=self.process.title,
            summary=getattr(self.process, 'abstract', 'No summary'),
            url=wps_describe_url(self.wps.url, self.process.identifier),
            metadata=self.process.metadata)
