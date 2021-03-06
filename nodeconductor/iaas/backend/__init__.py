
class CloudBackendError(Exception):
    """
    Base exception for errors occurring during backend communication.
    """
    pass


class CloudBackendInternalError(Exception):
    """
    Exception for errors in helpers.

    This exception will be raised if error happens, but cloud client
    did not raise any exception. It has be caught by public methods.
    """
    pass


class AbstractCloudBackend(object):
    """
    TODO: Document me
    """
    # CloudAccount related methods
    def push_cloud_account(self, cloud_account):
        raise NotImplementedError()

    # CloudProjectMembership related methods
    def push_membership(self, membership):
        raise NotImplementedError()

    def push_ssh_public_key(self, membership, public_key):
        raise NotImplementedError()

    def pull_flavors(self, membership):
        raise NotImplementedError()
