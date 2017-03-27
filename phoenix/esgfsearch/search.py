import datetime

from pyramid.settings import asbool

from pyesgf.search import SearchConnection
from pyesgf.search.consts import TYPE_DATASET, TYPE_AGGREGATION, TYPE_FILE
from pyesgf.multidict import MultiDict

import logging
LOGGER = logging.getLogger(__name__)


def date_from_filename(filename):
    """Example cordex:
    tas_EUR-44i_ECMWF-ERAINT_evaluation_r1i1p1_HMS-ALADIN52_v1_mon_200101-200812.nc
    """
    LOGGER.debug('filename=%s', filename)
    result = None
    value = filename.split('.')
    value.pop()  # remove .nc
    value = value[-1]  # part with date
    value = value.split('_')[-1]  # only date part
    LOGGER.debug('date part = %s', value)
    if value != 'fx':
        value = value.split('-')  # split start-end
        start_year = int(value[0][:4])  # keep only the year
        end_year = int(value[1][:4])
        result = (start_year, end_year)
    return result


def variable_filter(constraints, variables):
    """return True if variable fulfills contraints"""
    var_types = [u'variable', u'cf_standard_name', u'variable_long_name']

    success = True
    # check different types of variables
    for var_type in var_types:
        # is there a constrain for this variable type?
        if var_type in constraints:
            # at least one variable constraint must be fulfilled
            success = False
            # do we have this variable type?
            if var_type in variables:
                # do we have an allowed value?
                allowed_values = constraints.getall(var_type)
                for var in variables[var_type]:
                    if var in allowed_values:
                        # if one variable matches then we are ok
                        return True
    return success


def temporal_filter(filename, start=None, end=None):
    """return True if file is in timerange start/end"""
    # TODO: keep fixed fields fx ... see esgsearch.js
    """
    // fixed fields are always in time range
    if ($.inArray("fx", doc.time_frequency) >= 0) {
    return true;
    }
    """

    LOGGER.debug('filename=%s, start_date=%s, end_date=%s', filename, start, end)

    if start is None or end is None:
        return True
    start_end = date_from_filename(filename)
    if start_end is None:  # fixed field
        return True
    start_year = start_end[0]
    end_year = start_end[1]
    if end and start_year > end:
        LOGGER.debug('skip: %s > %s', start_year, end)
        return False
    if start and end_year < start:
        LOGGER.debug('skip: %s < %s', end_year, start)
        return False
    LOGGER.debug("pass: %s", filename)
    return True


def query_params_from_appstruct(appstruct):
    LOGGER.debug("query from appstruct = %s", appstruct)
    if not appstruct:
        return None
    return dict(
        query=appstruct.get('query', ''),
        selected=appstruct.get('selected', 'project'),
        distrib=str(appstruct.get('distrib', False)).lower(),
        replica=str(appstruct.get('replica', False)).lower(),
        latest=str(appstruct.get('latest', True)).lower(),
        temporal=str(appstruct.get('temporal', True)).lower(),
        start=appstruct.get('start', datetime.date(2001, 1, 1)).year,
        end=appstruct.get('end', datetime.date(2005, 12, 31)).year,
        constraints=appstruct.get('constraints'),
    )


class ESGFSearch(object):
    def __init__(self, request):
        self.request = request
        self.parse_params()
        settings = self.request.registry.settings
        self.conn = SearchConnection(settings.get('esgfsearch.url'), distrib=self.distrib)

    def parse_params(self):
        self.query = self.request.params.get('query', '')
        self.selected = self.request.params.get('selected', 'project')
        self.limit = int(self.request.params.get('limit', '0'))
        self.distrib = asbool(self.request.params.get('distrib', 'false'))
        self.latest = self._latest = asbool(self.request.params.get('latest', 'true'))
        self.temporal = asbool(self.request.params.get('temporal', 'true'))
        if self.latest is False:
            self._latest = None  # all versions
        self.replica = self._replica = asbool(self.request.params.get('replica', 'false'))
        if self.replica is True:
            self._replica = None  # master + replica
        self.start = self._start = int(self.request.params.get('start', '2001'))
        self.end = self._end = int(self.request.params.get('end', '2005'))
        if not self.temporal:
            self._start = None
            self._end = None
        self.constraints = self.request.params.get('constraints')
        self._constraints = MultiDict()
        if self.constraints:
            for constrain in self.constraints.split(','):
                if constrain.strip():
                    key, value = constrain.split(':', 1)
                    self._constraints.add(key, value)

    def query_params(self):
        return dict(
            query=self.query,
            selected=self.selected,
            distrib=str(self.distrib).lower(),
            replica=str(self.replica).lower(),
            latest=str(self.latest).lower(),
            temporal=str(self.temporal).lower(),
            start=self.start,
            end=self.end,
            constraints=self.constraints,
        )

    def params(self):
        params = dict(
            distrib=self.distrib,
            replica=self.replica,
            latest=self.latest,
            temporal=self.temporal,
            constraints=self.constraints,
        )
        if self.query:
            params['query'] = self.query
        if self.start and self.end:
            params['start'] = datetime.date(int(self.start), 1, 1)
            params['end'] = datetime.date(int(self.end), 12, 31)
        return params

    def search_items(self):
        dataset_id = self.request.params.get('dataset_id')
        items = []
        items.extend(self._run_search_items(dataset_id, search_type=TYPE_AGGREGATION))
        items.extend(self._run_search_items(dataset_id, search_type=TYPE_FILE))
        return dict(items=items)

    def _run_search_items(self, dataset_id, search_type):
        if not dataset_id:
            return []
        ctx = self.conn.new_context(search_type=search_type, latest=self._latest, replica=self._replica)
        ctx = ctx.constrain(dataset_id=dataset_id)
        items = []
        LOGGER.debug("hit_count: %s", ctx.hit_count)
        for result in ctx.search():
            if search_type == TYPE_FILE and not temporal_filter(result.filename, self._start, self._end):
                continue
            if not variable_filter(self._constraints, variables=result.json):
                continue
            items.append(dict(
                title=result.json.get('title'),
                type=result.json.get('type'),
                download_url=result.download_url,
                opendap_url=result.opendap_url,
                cart_available=result.opendap_url is not None,
                is_in_cart=result.opendap_url in self.request.cart,
            ))
        return items

    def search_datasets(self):
        ctx = self.conn.new_context(search_type=TYPE_DATASET, latest=self._latest, replica=self._replica)
        ctx = ctx.constrain(**self._constraints.mixed())
        if self.query:
            ctx = ctx.constrain(query=self.query)
        if self.temporal:
            ctx = ctx.constrain(
                from_timestamp="{}-01-01T12:00:00Z".format(self.start),
                to_timestamp="{}-12-31T12:00:00Z".format(self.end))
        results = ctx.search(batch_size=5, ignore_facet_check=False)
        categories = sorted([tag for tag in ctx.facet_counts if len(ctx.facet_counts[tag]) > 1])
        keywords = sorted(ctx.facet_counts[self.selected].keys())
        pinned_facets = []
        for facet in ctx.facet_counts:
            if facet not in self._constraints and len(ctx.facet_counts[facet]) == 1:
                pinned_facets.append("{}:{}".format(facet, ctx.facet_counts[facet].keys()[0]))
        pinned_facets = sorted(pinned_facets)
        paged_results = []
        for i in range(0, min(5, ctx.hit_count)):
            paged_results.append(dict(
                id=results[i].json['master_id'],
                title=results[i].json['title'],
                dataset_id=results[i].dataset_id,
                number_of_files=results[i].number_of_files,
                catalog_url=results[i].urls['THREDDS'][0][0]))
        return dict(
            hit_count=ctx.hit_count,
            categories=','.join(categories),
            keywords=','.join(keywords),
            pinned_facets=','.join(pinned_facets),
            results=paged_results)