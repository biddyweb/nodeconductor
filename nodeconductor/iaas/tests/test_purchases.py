from rest_framework import test
from rest_framework import status
from rest_framework.reverse import reverse

from nodeconductor.iaas.tests import factories as iaas_factories
from nodeconductor.structure.models import Role
from nodeconductor.structure.tests import factories as structure_factories


class PurchasePermissionTest(test.APISimpleTestCase):
    def setUp(self):
        self.user = structure_factories.UserFactory.create()
        self.client.force_authenticate(user=self.user)

        admined_project = structure_factories.ProjectFactory()
        managed_project = structure_factories.ProjectFactory()
        inaccessible_project = structure_factories.ProjectFactory()

        admined_project.add_user(self.user, Role.ADMINISTRATOR)
        managed_project.add_user(self.user, Role.MANAGER)

        self.admined_purchase = iaas_factories.PurchaseFactory(project=admined_project)
        self.managed_purchase = iaas_factories.PurchaseFactory(project=managed_project)
        self.inaccessible_purchase = iaas_factories.PurchaseFactory(project=inaccessible_project)

    # List filtration tests
    def test_user_can_list_purchase_history_of_project_he_is_administrator_of(self):
        response = self.client.get(reverse('purchase-list'))
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        purchase_url = self._get_purchase_url(self.admined_purchase)
        self.assertIn(purchase_url, [purchase['url'] for purchase in response.data])

    def test_user_can_list_purchase_history_of_project_he_is_manager_of(self):
        response = self.client.get(reverse('purchase-list'))
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        purchase_url = self._get_purchase_url(self.managed_purchase)
        self.assertIn(purchase_url, [purchase['url'] for purchase in response.data])

    def test_user_cannot_list_purchase_history_of_project_he_has_no_role_in(self):
        response = self.client.get(reverse('purchase-list'))
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        purchase_url = self._get_purchase_url(self.inaccessible_purchase)
        self.assertNotIn(purchase_url, [purchase['url'] for purchase in response.data])

    def test_user_cannot_list_purchases_not_allowed_for_any_project(self):
        inaccessible_purchase = iaas_factories.PurchaseFactory()

        response = self.client.get(reverse('purchase-list'))
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        purchase_url = self._get_purchase_url(inaccessible_purchase)
        self.assertNotIn(purchase_url, [instance['url'] for instance in response.data])

    # Helper methods
    def _get_purchase_url(self, purchase):
        return 'http://testserver' + reverse('purchase-detail', kwargs={'uuid': purchase.uuid})