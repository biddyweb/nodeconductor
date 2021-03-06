import logging

from nodeconductor.core.permissions import SAFE_METHODS
from nodeconductor.core.permissions import IsAdminOrReadOnly
from nodeconductor.structure.models import Customer

logger = logging.getLogger(__name__)


def _can_manage_organization(candidate_user, approving_user):
    if candidate_user.organization == "":
        return False

    # TODO: this will fail validation if more than one customer with a particular abbreviation exists
    try:
        organization = Customer.objects.get(abbreviation=candidate_user.organization)
        if organization.has_user(approving_user):
            return True
    except Customer.DoesNotExist:
        logging.warning('Approval was attempted for a Customer with abbreviation %s that does not exist.',
                        candidate_user.organization)
    except Customer.MultipleObjectsReturned:
        logging.error('More than one Customer with abbreviation %s exists. Breaks approval flow.',
                      candidate_user.organization)

    return False


# TODO: this is a temporary permission filter.
class IsAdminOrOwnerOrOrganizationManager(IsAdminOrReadOnly):
    """
    Allows access to admin users or account's owner for modifications.
    Allow access for approving/rejecting/removing organization for connected customer owners.
    For other users read-only access.
    """

    def has_permission(self, request, view):
        user = request.user

        if user.is_staff or request.method in SAFE_METHODS:
            return True
        elif request.method == 'POST' and view.action_map.get('post') in \
                ['approve_organization', 'reject_organization', 'remove_organization']:
                return _can_manage_organization(view.get_object(), user)
        elif view.suffix == 'List' or request.method == 'DELETE':
            return False

        return user == view.get_object()
