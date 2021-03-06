from decimal import Decimal
from random import randint

from django.core.urlresolvers import reverse
from django.utils import timezone
import factory
import factory.fuzzy

from nodeconductor.iaas import models
from nodeconductor.core import models as core_models
from nodeconductor.structure.tests import factories as structure_factories
from nodeconductor.template.tests import factories as template_factories


class CloudFactory(factory.DjangoModelFactory):
    class Meta(object):
        model = models.Cloud

    name = factory.Sequence(lambda n: 'cloud%s' % n)
    customer = factory.SubFactory(structure_factories.CustomerFactory)
    auth_url = 'http://example.com:5000/v2'

    @classmethod
    def get_url(self, cloud=None):
        if cloud is None:
            cloud = CloudFactory()
        return 'http://testserver' + reverse('cloud-detail', kwargs={'uuid': cloud.uuid})

    @classmethod
    def get_list_url(cls):
        return 'http://testserver' + reverse('cloud-list')


class FlavorFactory(factory.DjangoModelFactory):
    class Meta(object):
        model = models.Flavor

    name = factory.Sequence(lambda n: 'flavor%s' % n)
    cloud = factory.SubFactory(CloudFactory)

    cores = 2
    ram = 2 * 1024
    disk = 10 * 1024

    backend_id = factory.Sequence(lambda n: 'flavor-id%s' % n)

    @classmethod
    def get_url(cls, flavor=None):
        if flavor is None:
            flavor = FlavorFactory()
        return 'http://testserver' + reverse('flavor-detail', kwargs={'uuid': flavor.uuid})

    @classmethod
    def get_list_url(cls):
        return 'http://testserver' + reverse('flavor-list')


class CloudProjectMembershipFactory(factory.DjangoModelFactory):
    class Meta(object):
        model = models.CloudProjectMembership

    cloud = factory.SubFactory(CloudFactory)
    project = factory.SubFactory(structure_factories.ProjectFactory)
    tenant_id = factory.Sequence(lambda n: 'tenant_id_%s' % n)

    @classmethod
    def get_url(cls, membership=None, action=None):
        if membership is None:
            membership = CloudProjectMembershipFactory()
        url = 'http://testserver' + reverse('cloudproject_membership-detail', kwargs={'pk': membership.pk})
        return url if action is None else url + action + '/'

    @classmethod
    def get_list_url(cls):
        return 'http://testserver' + reverse('cloudproject_membership-list')

    @factory.post_generation
    def quotas(self, create, extracted, **kwargs):
        if create:
            if extracted:
                for quota in extracted:
                    if 'limit' in quota:
                        self.set_quota_limit(quota['name'], quota['limit'])
                    if 'usage' in quota:
                        self.set_quota_usage(quota['name'], quota['usage'])
            else:
                self.set_quota_limit('storage', 10 * 1024 * 1024)
                self.set_quota_limit('vcpu', 20)
                self.set_quota_limit('max_instances', 10)
                self.set_quota_limit('ram', 20 * 1024)


class SecurityGroupFactory(factory.DjangoModelFactory):
    class Meta(object):
        model = models.SecurityGroup

    cloud_project_membership = factory.SubFactory(CloudProjectMembershipFactory)
    name = factory.Sequence(lambda n: 'group%s' % n)
    description = factory.Sequence(lambda n: 'very good group %s' % n)

    @classmethod
    def get_url(cls, security_group=None):
        if security_group is None:
            security_group = CloudProjectMembershipFactory()
        return 'http://testserver' + reverse('security_group-detail', kwargs={'uuid': security_group.uuid})


class SecurityGroupRuleFactory(factory.DjangoModelFactory):
    class Meta(object):
        model = models.SecurityGroupRule

    security_group = factory.SubFactory(SecurityGroupFactory)
    protocol = models.SecurityGroupRule.tcp
    from_port = factory.fuzzy.FuzzyInteger(1, 65535)
    to_port = factory.fuzzy.FuzzyInteger(1, 65535)
    cidr = factory.LazyAttribute(lambda o: '.'.join('%s' % randint(1, 255) for i in range(4)) + '/24')


class IpMappingFactory(factory.DjangoModelFactory):
    class Meta(object):
        model = models.IpMapping

    public_ip = factory.LazyAttribute(lambda o: '84.%s' % '.'.join(
        '%s' % randint(0, 255) for _ in range(3)))
    private_ip = factory.LazyAttribute(lambda o: '10.%s' % '.'.join(
        '%s' % randint(0, 255) for _ in range(3)))
    project = factory.SubFactory(structure_factories.ProjectFactory)

    @classmethod
    def get_url(cls, ip_mapping=None):
        ip_mapping = ip_mapping or IpMappingFactory()

        return 'http://testserver' + reverse('ip_mapping-detail', kwargs={'uuid': ip_mapping.uuid})

    @classmethod
    def get_list_url(cls):
        return 'http://testserver' + reverse('ip_mapping-list')


class TemplateFactory(factory.DjangoModelFactory):
    class Meta(object):
        model = models.Template

    name = factory.Sequence(lambda n: 'template%s' % n)
    description = factory.Sequence(lambda n: 'description %d' % n)
    icon_url = factory.Sequence(lambda n: 'http://example.com/%d.png' % n)
    is_active = True
    sla_level = factory.LazyAttribute(lambda o: Decimal('99.9'))
    setup_fee = factory.fuzzy.FuzzyDecimal(10.0, 50.0, 3)
    monthly_fee = factory.fuzzy.FuzzyDecimal(0.5, 20.0, 3)

    @classmethod
    def get_url(cls, template=None):
        template = template or TemplateFactory()

        return 'http://testserver' + reverse('iaastemplate-detail', kwargs={'uuid': template.uuid})

    @classmethod
    def get_list_url(cls):
        return 'http://testserver' + reverse('iaastemplate-list')


class TemplateMappingFactory(factory.DjangoModelFactory):
    class Meta(object):
        model = models.TemplateMapping

    template = factory.SubFactory(TemplateFactory)
    backend_image_id = factory.Sequence(lambda n: 'image-id-%s' % n)


class TemplateLicenseFactory(factory.DjangoModelFactory):
    class Meta(object):
        model = models.TemplateLicense

    name = factory.Sequence(lambda n: 'License%s' % n)
    license_type = factory.Sequence(lambda n: 'LicenseType%s' % n)
    service_type = models.TemplateLicense.Services.IAAS
    setup_fee = factory.fuzzy.FuzzyDecimal(10.0, 50.0, 3)
    monthly_fee = factory.fuzzy.FuzzyDecimal(0.5, 20.0, 3)

    @factory.post_generation
    def templates(self, create, extracted, **kwargs):
        if not create:
            # Simple build, do nothing.
            return

        if extracted:
            for template in extracted:
                self.templates.add(template)


class ImageFactory(factory.DjangoModelFactory):
    class Meta(object):
        model = models.Image

    cloud = factory.SubFactory(CloudFactory)
    template = factory.SubFactory(TemplateFactory)
    backend_id = factory.Sequence(lambda n: 'id%s' % n)


class SshPublicKeyFactory(factory.DjangoModelFactory):
    class Meta(object):
        model = core_models.SshPublicKey

    user = factory.SubFactory(structure_factories.UserFactory)
    name = factory.Sequence(lambda n: 'ssh_public_key%s' % n)
    public_key = (
        "ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAABAQDDURXDP5YhOQUYoDuTxJ84DuzqMJYJqJ8+SZT28"
        "TtLm5yBDRLKAERqtlbH2gkrQ3US58gd2r8H9jAmQOydfvgwauxuJUE4eDpaMWupqquMYsYLB5f+vVGhdZbbzfc6DTQ2rY"
        "dknWoMoArlG7MvRMA/xQ0ye1muTv+mYMipnd7Z+WH0uVArYI9QBpqC/gpZRRIouQ4VIQIVWGoT6M4Kat5ZBXEa9yP+9du"
        "D2C05GX3gumoSAVyAcDHn/xgej9pYRXGha4l+LKkFdGwAoXdV1z79EG1+9ns7wXuqMJFHM2KDpxAizV0GkZcojISvDwuh"
        "vEAFdOJcqjyyH4FOGYa8usP1 test"
    )

    @classmethod
    def get_url(self, key):
        if key is None:
            key = SshPublicKeyFactory()
        return 'http://testserver' + reverse('sshpublickey-detail', kwargs={'uuid': str(key.uuid)})

    @classmethod
    def get_list_url(self):
        return 'http://testserver' + reverse('sshpublickey-list')


class InstanceFactory(factory.DjangoModelFactory):
    class Meta(object):
        model = models.Instance

    name = factory.Sequence(lambda n: 'host%s' % n)
    template = factory.SubFactory(TemplateFactory)

    start_time = factory.LazyAttribute(lambda o: timezone.now())
    external_ips = factory.LazyAttribute(lambda o: '.'.join(
        '%s' % randint(0, 255) for _ in range(4)))
    internal_ips = factory.LazyAttribute(lambda o: '.'.join(
        '%s' % randint(0, 255) for _ in range(4)))

    cores = factory.Sequence(lambda n: n)
    ram = factory.Sequence(lambda n: n)
    cloud_project_membership = factory.SubFactory(CloudProjectMembershipFactory)

    key_name = factory.Sequence(lambda n: 'instance key%s' % n)
    key_fingerprint = factory.Sequence(lambda n: 'instance key fingerprint%s' % n)

    system_volume_id = factory.Sequence(lambda n: 'sys-vol-id-%s' % n)
    system_volume_size = 10 * 1024
    data_volume_id = factory.Sequence(lambda n: 'dat-vol-id-%s' % n)
    data_volume_size = 20 * 1024

    backend_id = factory.Sequence(lambda n: 'instance-id%s' % n)

    agreed_sla = Decimal('99.9')

    @classmethod
    def get_url(self, instance=None, action=None):
        if instance is None:
            instance = InstanceFactory()
        url = 'http://testserver' + reverse('instance-detail', kwargs={'uuid': instance.uuid})
        return url if action is None else url + action + '/'

    @classmethod
    def get_list_url(self):
        return 'http://testserver' + reverse('instance-list')


class InstanceSlaHistoryFactory(factory.DjangoModelFactory):
    class Meta(object):
        model = models.InstanceSlaHistory

    period = factory.Sequence(lambda n: '200%s' % n)
    instance = factory.SubFactory(InstanceFactory)
    value = factory.LazyAttribute(lambda o: Decimal('99.9'))


class InstanceLicenseFactory(factory.DjangoModelFactory):
    class Meta(object):
        model = models.InstanceLicense

    instance = factory.SubFactory(InstanceFactory)
    template_license = factory.SubFactory(TemplateLicenseFactory)
    setup_fee = factory.fuzzy.FuzzyDecimal(10.0, 50.0, 3)
    monthly_fee = factory.fuzzy.FuzzyDecimal(0.5, 20.0, 3)


class InstanceSecurityGroupFactory(factory.DjangoModelFactory):
    class Meta(object):
        model = models.InstanceSecurityGroup

    instance = factory.SubFactory(InstanceFactory)
    security_group = factory.SubFactory(SecurityGroupFactory)


class FloatingIPFactory(factory.DjangoModelFactory):
    class Meta(object):
        model = models.FloatingIP

    cloud_project_membership = factory.SubFactory(CloudProjectMembershipFactory)
    status = factory.Iterator(['ACTIVE', 'SHUTOFF', 'DOWN'])
    address = factory.LazyAttribute(lambda o: '.'.join('%s' % randint(0, 255) for _ in range(4)))

    @classmethod
    def get_url(self, instance=None):
        if instance is None:
            instance = FloatingIPFactory()
        return 'http://testserver' + reverse('floating_ip-detail', kwargs={'uuid': instance.uuid})

    @classmethod
    def get_list_url(self):
        return 'http://testserver' + reverse('floating_ip-list')


class IaasTemplateServiceFactory(factory.DjangoModelFactory):
    class Meta(object):
        model = models.IaasTemplateService

    name = factory.Sequence(lambda n: 'My VM %s' % n)
    template = factory.SubFactory(template_factories.TemplateFactory)

    service = factory.SubFactory(CloudFactory)
    flavor = factory.SubFactory(FlavorFactory)
    image = factory.SubFactory(ImageFactory)
    sla = True
    sla_level = factory.LazyAttribute(lambda o: Decimal('99.9'))
    backup_schedule = '*/5 * * * *'
