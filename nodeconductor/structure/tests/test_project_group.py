from __future__ import unicode_literals

from itertools import chain

from django.core.urlresolvers import reverse
from django.test import TransactionTestCase
from mock_django import mock_signal_receiver
from rest_framework import status
from rest_framework import test

from nodeconductor.structure import signals
from nodeconductor.structure.models import CustomerRole, ProjectGroup, ProjectRole, ProjectGroupRole
from nodeconductor.structure.tests import factories


class ProjectGroupTest(TransactionTestCase):
    def setUp(self):
        self.project_group = factories.ProjectGroupFactory()
        self.user = factories.UserFactory()

    def test_add_user_returns_created_if_grant_didnt_exist_before(self):
        _, created = self.project_group.add_user(self.user, ProjectGroupRole.MANAGER)

        self.assertTrue(created, 'Project permission should have been reported as created')

    def test_add_user_returns_not_created_if_grant_existed_before(self):
        self.project_group.add_user(self.user, ProjectGroupRole.MANAGER)
        _, created = self.project_group.add_user(self.user, ProjectGroupRole.MANAGER)

        self.assertFalse(created, 'Project permission should have been reported as not created')

    def test_add_user_returns_membership(self):
        membership, _ = self.project_group.add_user(self.user, ProjectGroupRole.MANAGER)

        self.assertEqual(membership.user, self.user)
        self.assertEqual(membership.group.projectgrouprole.project_group, self.project_group)

    def test_add_user_returns_same_membership_for_consequent_calls_with_same_arguments(self):
        membership1, _ = self.project_group.add_user(self.user, ProjectGroupRole.MANAGER)
        membership2, _ = self.project_group.add_user(self.user, ProjectGroupRole.MANAGER)

        self.assertEqual(membership1, membership2)

    def test_add_user_emits_structure_role_granted_if_grant_didnt_exist_before(self):
        with mock_signal_receiver(signals.structure_role_granted) as receiver:
            self.project_group.add_user(self.user, ProjectGroupRole.MANAGER)

        receiver.assert_called_once_with(
            structure=self.project_group,
            user=self.user,
            role=ProjectGroupRole.MANAGER,

            sender=ProjectGroup,
            signal=signals.structure_role_granted,
        )

    def test_add_user_doesnt_emit_structure_role_granted_if_grant_existed_before(self):
        self.project_group.add_user(self.user, ProjectGroupRole.MANAGER)

        with mock_signal_receiver(signals.structure_role_granted) as receiver:
            self.project_group.add_user(self.user, ProjectGroupRole.MANAGER)

        self.assertFalse(receiver.called, 'structure_role_granted should not be emitted')

    def test_remove_user_emits_structure_role_revoked_if_grant_existed_before(self):
        self.project_group.add_user(self.user, ProjectGroupRole.MANAGER)

        with mock_signal_receiver(signals.structure_role_revoked) as receiver:
            self.project_group.remove_user(self.user, ProjectGroupRole.MANAGER)

        receiver.assert_called_once_with(
            structure=self.project_group,
            user=self.user,
            role=ProjectGroupRole.MANAGER,

            sender=ProjectGroup,
            signal=signals.structure_role_revoked,
        )

    def test_remove_user_doesnt_emit_structure_role_revoked_if_grant_didnt_exist_before(self):
        with mock_signal_receiver(signals.structure_role_revoked) as receiver:
            self.project_group.remove_user(self.user, ProjectGroupRole.MANAGER)

        self.assertFalse(receiver.called, 'structure_role_remove should not be emitted')


# noinspection PyMethodMayBeStatic
class UrlResolverMixin(object):
    def _get_customer_url(self, customer):
        return 'http://testserver' + reverse('customer-detail', kwargs={'uuid': customer.uuid})

    def _get_project_url(self, project):
        return 'http://testserver' + reverse('project-detail', kwargs={'uuid': project.uuid})

    def _get_project_group_url(self, project_group):
        return 'http://testserver' + reverse('projectgroup-detail', kwargs={'uuid': project_group.uuid})

    def _get_membership_url(self, membership):
        return 'http://testserver' + reverse('projectgroup_membership-detail', kwargs={'pk': membership.pk})


class ProjectGroupApiPermissionTest(UrlResolverMixin, test.APISimpleTestCase):
    def setUp(self):
        self.users = {
            'owner': factories.UserFactory(),
            'admin': factories.UserFactory(),
            'manager': factories.UserFactory(),
            'group_manager': factories.UserFactory(),
            'no_role': factories.UserFactory(),
        }

        self.customer = factories.CustomerFactory()
        self.customer.add_user(self.users['owner'], CustomerRole.OWNER)

        project_groups = factories.ProjectGroupFactory.create_batch(3, customer=self.customer)
        project_groups.append(factories.ProjectGroupFactory())

        self.project_groups = {
            'owner': project_groups[:-1],
            'admin': project_groups[0:2],
            'manager': project_groups[1:3],
            'group_manager': project_groups[2:3],
            'inaccessible': project_groups[-1:],
        }
        project_groups[2].add_user(self.users['group_manager'], ProjectGroupRole.MANAGER)

        admined_project = factories.ProjectFactory(customer=self.customer)
        admined_project.add_user(self.users['admin'], ProjectGroupRole.MANAGER)
        admined_project.project_groups.add(*self.project_groups['admin'])

        managed_project = factories.ProjectFactory(customer=self.customer)
        managed_project.add_user(self.users['manager'], ProjectRole.MANAGER)
        managed_project.project_groups.add(*self.project_groups['manager'])

    # Creation tests
    def test_anonymous_user_cannot_create_project_groups(self):
        response = self.client.post(reverse('projectgroup-list'), self._get_valid_payload())
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_user_can_create_project_group_belonging_to_customer_he_owns(self):
        self.client.force_authenticate(user=self.users['owner'])

        payload = self._get_valid_payload(factories.ProjectGroupFactory(customer=self.customer))

        response = self.client.post(reverse('projectgroup-list'), payload)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    def test_user_cannot_create_project_group_belonging_to_customer_he_doesnt_own(self):
        self.client.force_authenticate(user=self.users['owner'])

        payload = self._get_valid_payload()

        response = self.client.post(reverse('projectgroup-list'), payload)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertDictContainsSubset({'customer': ['Invalid hyperlink - Object does not exist.']}, response.data)

    # Deletion tests
    def test_anonymous_user_cannot_delete_project_groups(self):
        for project_group in set(chain(*self.project_groups.values())):
            response = self.client.delete(self._get_project_group_url(project_group))
            self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_user_can_delete_project_group_belonging_to_customer_he_owns(self):
        owner = factories.UserFactory()
        customer = factories.CustomerFactory()
        customer.add_user(owner, CustomerRole.OWNER)
        project_group = factories.ProjectGroupFactory(customer=customer)

        self.client.force_authenticate(user=owner)
        response = self.client.delete(self._get_project_group_url(project_group))
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)

    def test_user_cannot_delete_project_group_belonging_to_customer_he_owns_with_projects(self):
        owner = factories.UserFactory()
        customer = factories.CustomerFactory()
        customer.add_user(owner, CustomerRole.OWNER)
        project_group = factories.ProjectGroupFactory(customer=customer)
        project = factories.ProjectFactory()
        project.project_groups.add(project_group)

        self.client.force_authenticate(user=owner)
        response = self.client.delete(self._get_project_group_url(project_group))
        self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)
        self.assertDictContainsSubset({'detail': 'Cannot delete project group with existing projects'},
                                      response.data)

    def test_user_cannot_delete_project_group_belonging_to_customer_he_doesnt_own(self):
        self.client.force_authenticate(user=self.users['owner'])

        for project_group in self.project_groups['inaccessible']:
            response = self.client.delete(self._get_project_group_url(project_group))
            self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    # Mutation tests
    def test_anonymous_user_cannot_change_project_groups(self):
        for project_group in set(chain(*self.project_groups.values())):
            response = self.client.put(self._get_project_group_url(project_group),
                                       self._get_valid_payload(project_group))
            self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_user_can_change_name_of_project_group_belonging_to_customer_he_owns(self):
        self.client.force_authenticate(user=self.users['owner'])

        for project_group in self.project_groups['owner']:
            payload = self._get_valid_payload(project_group)
            payload['name'] = (factories.ProjectGroupFactory()).name

            response = self.client.put(self._get_project_group_url(project_group), payload)
            self.assertEqual(response.status_code, status.HTTP_200_OK)

            updated_project_group = ProjectGroup.objects.get(pk=project_group.pk)
            self.assertEqual(updated_project_group.name, payload['name'])

    def test_user_cannot_change_customer_of_project_group_belonging_to_customer_he_owns(self):
        user = self.users['owner']
        self.client.force_authenticate(user=user)

        new_not_owned_customer = (factories.ProjectGroupFactory()).customer

        new_owned_customer = (factories.ProjectGroupFactory()).customer
        new_owned_customer.add_user(user, CustomerRole.OWNER)

        for project_group in self.project_groups['owner']:
            payload = self._get_valid_payload(project_group)

            # Testing owner that can be accessed
            payload['customer'] = self._get_customer_url(new_owned_customer)

            # TODO: Instead of just ignoring the field, we should have forbidden the update
            # see NC-73 for explanation of similar issue
            response = self.client.put(self._get_project_group_url(project_group), payload)
            self.assertEqual(response.status_code, status.HTTP_200_OK)

            updated_project_group = ProjectGroup.objects.get(pk=project_group.pk)
            self.assertEqual(updated_project_group.customer, project_group.customer,
                             'Customer should have stayed intact')

            # Testing owner that cannot be accessed
            payload['customer'] = self._get_customer_url(new_not_owned_customer)
            response = self.client.put(self._get_project_group_url(project_group), payload)
            self.assertEqual(response.status_code, status.HTTP_200_OK)

            updated_project_group = ProjectGroup.objects.get(pk=project_group.pk)
            self.assertEqual(updated_project_group.customer, project_group.customer,
                             'Customer should have stayed intact')

    def test_user_cannot_change_name_of_project_group_belonging_to_customer_he_doesnt_own(self):
        self.client.force_authenticate(user=self.users['owner'])

        for project_group in self.project_groups['inaccessible']:
            payload = self._get_valid_payload(project_group)
            payload['name'] = (factories.ProjectGroupFactory()).name

            response = self.client.put(self._get_project_group_url(project_group), payload)
            self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_user_can_change_name_of_project_group_he_is_project_group_manager_of(self):
        self.client.force_authenticate(user=self.users['group_manager'])

        for project_group in self.project_groups['group_manager']:
            payload = self._get_valid_payload(project_group)
            payload['name'] = (factories.ProjectGroupFactory()).name

            response = self.client.put(self._get_project_group_url(project_group), payload)
            self.assertEqual(response.status_code, status.HTTP_200_OK)

    # List filtration tests
    def test_anonymous_user_cannot_list_project_groups(self):
        response = self.client.get(reverse('projectgroup-list'))
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_user_can_list_project_groups_of_customers_he_is_owner_of(self):
        self._ensure_list_access_allowed('owner')

    def test_user_can_list_project_groups_including_projects_he_is_administrator_of(self):
        self._ensure_list_access_allowed('admin')

    def test_user_can_list_project_groups_including_projects_he_is_manager_of(self):
        self._ensure_list_access_allowed('manager')

    def test_user_can_list_project_groups_where_he_is_manager(self):
        self._ensure_list_access_allowed('group_manager')

    def test_user_cannot_list_project_groups_he_has_no_role_in(self):
        self._ensure_list_access_forbidden('owner')
        self._ensure_list_access_forbidden('admin')
        self._ensure_list_access_forbidden('manager')
        self._ensure_list_access_forbidden('group_manager')

    # Direct instance access tests
    def test_anonymous_user_cannot_access_project_group(self):
        project_group = factories.ProjectGroupFactory()
        response = self.client.get(self._get_project_group_url(project_group))
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_user_can_access_project_groups_of_customers_he_is_owner_of(self):
        self._ensure_direct_access_allowed('owner')

    def test_user_can_access_project_groups_including_projects_he_is_administrator_of(self):
        self._ensure_direct_access_allowed('admin')

    def test_user_can_access_project_groups_including_projects_he_is_manager_of(self):
        self._ensure_direct_access_allowed('manager')

    def test_user_can_access_project_groups_where_he_is_manager(self):
        self._ensure_direct_access_allowed('group_manager')

    def test_user_cannot_access_project_groups_he_has_no_role_in(self):
        self._ensure_direct_access_forbidden('owner')
        self._ensure_direct_access_forbidden('admin')
        self._ensure_direct_access_forbidden('manager')
        self._ensure_direct_access_forbidden('group_manager')

    # Helper methods
    def _ensure_list_access_allowed(self, user_role):
        self.client.force_authenticate(user=self.users[user_role])

        response = self.client.get(reverse('projectgroup-list'))
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        urls = set([instance['url'] for instance in response.data])
        for project_group in self.project_groups[user_role]:
            url = self._get_project_group_url(project_group)

            self.assertIn(url, urls)

    def _ensure_direct_access_allowed(self, user_role):
        self.client.force_authenticate(user=self.users[user_role])
        for project_group in self.project_groups[user_role]:
            url = self._get_project_group_url(project_group)

            response = self.client.get(url)
            self.assertEqual(response.status_code, status.HTTP_200_OK)

    def _ensure_list_access_forbidden(self, user_role):
        self.client.force_authenticate(user=self.users[user_role])

        response = self.client.get(reverse('project-list'))
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        urls = set([instance['url'] for instance in response.data])
        for project_group in self.project_groups['inaccessible']:
            url = self._get_project_group_url(project_group)

            self.assertNotIn(url, urls)

    def _ensure_direct_access_forbidden(self, user_role):
        self.client.force_authenticate(user=self.users[user_role])
        for project_group in self.project_groups['inaccessible']:
            response = self.client.get(self._get_project_group_url(project_group))
            # 404 is used instead of 403 to hide the fact that the resource exists at all
            self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def _get_valid_payload(self, resource=None):
        resource = resource or factories.ProjectGroupFactory()

        return {
            'name': resource.name,
            'customer': self._get_customer_url(resource.customer),
        }


ProjectGroupMembership = ProjectGroup.projects.through


class ProjectGroupMembershipApiPermissionTest(UrlResolverMixin, test.APISimpleTestCase):
    def setUp(self):
        self.users = {
            'owner': factories.UserFactory(),
            'no_role': factories.UserFactory(),
        }

        self.project_groups = {}
        self.projects = {}
        self.memberships = {}
        self.customers = {}

        for i in ('owner', 'inaccessible'):
            customer = factories.CustomerFactory()

            self.customers[i] = customer
            self.projects[i] = factories.ProjectFactory.create_batch(2, customer=customer)
            self.project_groups[i] = factories.ProjectGroupFactory.create_batch(2, customer=customer)

            project = self.projects[i][0]
            project_group = self.project_groups[i][0]

            project_group.projects.add(project)

            membership = ProjectGroupMembership.objects.get(project=project, projectgroup=project_group)
            self.memberships[i] = membership

        self.customers['owner'].add_user(self.users['owner'], CustomerRole.OWNER)

    # Creation tests
    def test_anonymous_user_cannot_create_project_group_membership(self):
        from itertools import product

        project_groups = chain.from_iterable(self.project_groups.values())
        projects = chain.from_iterable(self.projects.values())

        for project_group, project in product(project_groups, projects):
            membership = ProjectGroupMembership(project=project, projectgroup=project_group)

            response = self.client.post(reverse('projectgroup_membership-list'),
                                        self._get_valid_payload(membership))
            self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_user_cannot_create_project_group_membership_within_project_group_he_doesnt_own(self):
        self.client.force_authenticate(user=self.users['owner'])

        project_group = self.project_groups['inaccessible'][0]
        project = self.projects['owner'][0]

        membership = ProjectGroupMembership(project=project, projectgroup=project_group)

        response = self.client.post(reverse('projectgroup_membership-list'),
                                    self._get_valid_payload(membership))
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertDictContainsSubset(
            {'project_group': ['Invalid hyperlink - Object does not exist.']}, response.data)

    def test_user_cannot_create_project_group_membership_within_project_he_doesnt_own(self):
        self.client.force_authenticate(user=self.users['owner'])

        project_group = self.project_groups['owner'][0]
        project = self.projects['inaccessible'][0]

        membership = ProjectGroupMembership(project=project, projectgroup=project_group)

        response = self.client.post(reverse('projectgroup_membership-list'),
                                    self._get_valid_payload(membership))
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertDictContainsSubset(
            {'project': ['Invalid hyperlink - Object does not exist.']}, response.data)

    # TODO: return 409 CONFLICT or 304 NOT MODIFIED instead of 400 BAD REQUEST for already existing links

    def test_user_can_add_project_to_project_group_given_they_belong_to_the_same_customer_he_owns(self):
        self.client.force_authenticate(user=self.users['owner'])

        project_groups = self.project_groups['owner']
        projects = self.projects['owner']

        for project_group_index, project_index in (
                (0, 1),
                (1, 0),
                (1, 1),
        ):
            project_group = project_groups[project_group_index]
            project = projects[project_index]

            membership = ProjectGroupMembership(project=project, projectgroup=project_group)

            response = self.client.post(reverse('projectgroup_membership-list'),
                                        self._get_valid_payload(membership))
            self.assertEqual(response.status_code, status.HTTP_201_CREATED)

            self.assertIn(project, project_group.projects.all())

    # Mutation tests
    def test_anonymous_user_cannot_change_project_group_membership(self):
        for i in ('owner', 'inaccessible'):
            project_group, project = self.project_groups[i][0], self.projects[i][0]

            membership = ProjectGroupMembership.objects.get(project=project, projectgroup=project_group)

            response = self.client.put(self._get_membership_url(membership),
                                       self._get_valid_payload(membership))
            self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_user_cannot_change_project_group_membership(self):
        self.client.force_authenticate(user=self.users['owner'])

        membership = self.memberships['owner']

        response = self.client.put(self._get_membership_url(membership),
                                   self._get_valid_payload(membership))
        self.assertEqual(response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)

    # Deletion tests
    def test_anonymous_user_cannot_delete_project_group_membership(self):
        for membership in self.memberships.values():
            response = self.client.delete(self._get_membership_url(membership))
            self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_user_can_delete_project_group_membership_he_owns(self):
        self.client.force_authenticate(user=self.users['owner'])

        membership = self.memberships['owner']

        response = self.client.delete(self._get_membership_url(membership))
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)

        project_group = self.project_groups['owner'][0]
        project = self.projects['owner'][0]
        self.assertNotIn(project, project_group.projects.all())

    def test_user_cannot_delete_project_group_membership_he_doesnt_own(self):
        self.client.force_authenticate(user=self.users['owner'])

        membership = self.memberships['inaccessible']

        response = self.client.delete(self._get_membership_url(membership))
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

        project_group = self.project_groups['inaccessible'][0]
        project = self.projects['inaccessible'][0]
        self.assertIn(project, project_group.projects.all())

    # List filtration tests
    def test_anonymous_user_cannot_list_project_group_membership(self):
        response = self.client.get(reverse('projectgroup_membership-list'))
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_user_can_list_membership_of_project_groups_of_customer_he_owns(self):
        self.client.force_authenticate(user=self.users['owner'])

        response = self.client.get(reverse('projectgroup_membership-list'))
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        urls = set([instance['url'] for instance in response.data])
        url = self._get_membership_url(self.memberships['owner'])

        self.assertIn(url, urls)

    def test_user_cannot_list_membership_of_project_groups_of_customer_he_doesnt_own(self):
        self.client.force_authenticate(user=self.users['owner'])

        response = self.client.get(reverse('projectgroup_membership-list'))
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        urls = set([instance['url'] for instance in response.data])
        url = self._get_membership_url(self.memberships['inaccessible'])

        self.assertNotIn(url, urls)

    # Helper methods
    def _get_valid_payload(self, resource=None, include_url=False):
        payload = {
            'project': self._get_project_url(resource.project),
            'project_group': self._get_project_group_url(resource.projectgroup),
        }

        if include_url:
            payload['url'] = self._get_membership_url(resource)

        return payload


class ProjectGroupMembershipApiFiltrationTest(UrlResolverMixin, test.APISimpleTestCase):
    def setUp(self):
        user = factories.UserFactory(is_staff=True)
        self.client.force_authenticate(user=user)

        customer = factories.CustomerFactory()

        self.projects = {
            'group1': factories.ProjectFactory.create_batch(2, customer=customer),
            'group2': factories.ProjectFactory.create_batch(2, customer=customer),
        }
        self.project_groups = {
            'group1': factories.ProjectGroupFactory(customer=customer),
            'group2': factories.ProjectGroupFactory(customer=customer),
        }

        for group_name in self.project_groups:
            for project in self.projects[group_name]:
                self.project_groups[group_name].projects.add(project)

    def test_user_can_filter_memberships_by_project_group_uuid(self):
        response = self.client.get(reverse('projectgroup_membership-list'))
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        data = {'project_group': self.project_groups['group1'].uuid}

        response = self.client.get(reverse('projectgroup_membership-list'), data=data)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        for membership in response.data:
            self.assertEqual(membership['project_group'], self._get_project_group_url(self.project_groups['group1']))

    def test_user_can_filter_memberships_by_project_group_name(self):
        self._ensure_can_filter_memberships_by_name('project_group_name', self.project_groups['group1'].name)

    def test_user_can_filter_memberships_by_project_uuid(self):
        response = self.client.get(reverse('projectgroup_membership-list'))
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        data = {'project': self.projects['group1'][0].uuid}

        response = self.client.get(reverse('projectgroup_membership-list'), data=data)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        for membership in response.data:
            self.assertEqual(membership['project'], self._get_project_url(self.projects['group1'][0]))

    def test_user_can_filter_memberships_by_project_name(self):
        self._ensure_can_filter_memberships_by_name('project_name', self.projects['group1'][0].name)

    # Helper methods
    def _ensure_can_filter_memberships_by_name(self, field, value):
        response = self.client.get(reverse('projectgroup_membership-list'))
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        response = self.client.get(reverse('projectgroup_membership-list'), data={field: value})
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        for membership in response.data:
            self.assertEqual(membership[field], value)
