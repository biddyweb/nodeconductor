from __future__ import unicode_literals

import logging

from django.conf import settings
from elasticsearch import Elasticsearch


logger = logging.getLogger(__name__)


class ElasticsearchError(Exception):
    pass


class ElasticsearchClientError(ElasticsearchError):
    pass


class ElasticsearchResultListError(ElasticsearchError):
    pass


class ElasticsearchResultList(object):

    def __init__(self, user, event_types=None, search_text=None, sort='-@timestamp'):
        self.client = ElasticsearchClient()
        self.user = user
        self.event_types = event_types
        self.sort = sort
        self.search_text = search_text

    def _get_events(self, from_, size):
        return self.client.get_user_events(
            user=self.user,
            event_types=self.event_types,
            search_text=self.search_text,
            from_=from_,
            size=size,
            sort=self.sort
        )

    def __len__(self):
        if not hasattr(self, 'total'):
            self.total = self._get_events(0, 1)['total']
        return self.total

    def __getitem__(self, key):
        if isinstance(key, slice):
            if key.step is not None and key.step != 1:
                raise ElasticsearchResultListError('ElasticsearchResultList can be iterated only with step 1')
            start = key.start if key.start is not None else 0
            events_and_total = self._get_events(start, key.stop - start)
        else:
            events_and_total = self._get_events(key, 1)
        self.total = events_and_total['total']
        return events_and_total['events']


class ElasticsearchClient(object):

    FTS_FIELDS = (
        'message', 'customer_abbreviation', 'importance', 'project_group_name', 'cloud_account_name', 'project_name')

    def __init__(self):
        self.client = self._get_client()

    def get_user_events(
            self, user, event_types=None, search_text=None, sort='-@timestamp', index='_all', from_=0, size=10):
        """
        Return events filtered for given user and total count of available for user events
        """
        sort = sort[1:] + ':desc' if sort.startswith('-') else sort + ':asc'
        body = self._get_search_body(user, event_types, search_text)
        search_results = self.client.search(index=index, body=body, from_=from_, size=size, sort=sort)
        return {
            'events': [r['_source'] for r in search_results['hits']['hits']],
            'total': search_results['hits']['total'],
        }

    def _get_elastisearch_settings(self):
        try:
            return settings.NODECONDUCTOR['ELASTICSEARCH']
        except (KeyError, AttributeError):
            raise ElasticsearchClientError(
                'Can not get elasticsearch settings. ELASTICSEARCH item in settings.NODECONDUCTOR has'
                'to be defined. Or enable dummy elasticsearch mode.')

    def _get_client(self):
        # TODO return dummy client here
        elasticsearch_settings = self._get_elastisearch_settings()
        path = '%(protocol)s://%(username)s:%(password)s@%(host)s:%(port)s' % elasticsearch_settings
        return Elasticsearch(
            [path],
            use_ssl=elasticsearch_settings.get('use_ssl', False),
            verify_certs=elasticsearch_settings.get('verify_certs', False),
        )

    def _get_permitted_objects_uuids(self, user):
        """
        Return list object available UUIDs for user
        """
        # XXX: this method has to be refactored, because it adds dependencies from iaas and structure apps
        from nodeconductor.structure import models as structure_models
        from nodeconductor.structure.filters import filter_queryset_for_user

        return {
            'user_uuid': [user.uuid.hex],
            'project_uuid': filter_queryset_for_user(
                structure_models.Project.objects.all(), user).values_list('uuid', flat=True),
            'project_group_uuid': filter_queryset_for_user(
                structure_models.ProjectGroup.objects.all(), user).values_list('uuid', flat=True),
            'customer_uuid': filter_queryset_for_user(
                structure_models.Customer.objects.all(), user).values_list('uuid', flat=True),
        }

    def _escape_elasticsearch_field_value(self, field_value):
        """
        Remove double quotes from field value

        Elasticsearch receives string query where all user input is strings in double quotes.
        But if input itself contains double quotes - elastic treat them as end of string, so we have to remove double
        quotes from search string.
        """
        return field_value.replace('\"', '')

    def _format_to_elasticsearch_field_filter(self, field_name, field_values):
        """
        Return string '<field_name>:("<field_value1>", "<field_value2>"...)'
        """
        excaped_field_values = [self._escape_elasticsearch_field_value(value) for value in field_values]
        return '%s:("%s")' % (field_name, '", "'.join(excaped_field_values))

    def _get_search_body(self, user, event_types=None, search_text=None):
        permitted_objects_uuids = self._get_permitted_objects_uuids(user)
        # Create query for user-related events
        query = ' OR '.join([
            self._format_to_elasticsearch_field_filter(item, uuids)
            for item, uuids in permitted_objects_uuids.items()
        ])
        query = '(' + query + ')'
        # Filter it by event types
        if event_types:
            query += ' AND ' + self._format_to_elasticsearch_field_filter('event_type', event_types)
        # Add FTS to query
        if search_text:
            search_query = ' OR '.join(
                [self._format_to_elasticsearch_field_filter(field, [search_text]) for field in self.FTS_FIELDS])
            query += ' AND (' + search_query + ')'
        logger.debug('Getting elasticsearch results for user: "%s" with query: %s', user, query)
        return {"query": {"query_string": {"query": query}}}
