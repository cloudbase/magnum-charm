# Copyright 2018 Cloudbase Solutions

from __future__ import absolute_import

import collections

import charms_openstack.charm
import charms_openstack.adapters
import charms_openstack.ip as os_ip

PACKAGES = ['magnum-api', 'magnum-conductor', 'python-mysqldb']
MAGNUM_DIR = '/etc/magnum/'
MAGNUM_CONF = MAGNUM_DIR + "magnum.conf"

OPENSTACK_RELEASE_KEY = 'magnum-charm.openstack-release-version'


# select the default release function
charms_openstack.charm.use_defaults('charm.default-select-release')


def db_sync_done():
    return MagnumCharm.singleton.db_sync_done()


def restart_all():
    MagnumCharm.singleton.restart_all()


def db_sync():
    MagnumCharm.singleton.db_sync()


def assess_status():
    MagnumCharm.singleton.assess_status()


def setup_endpoint(keystone):
    charm = MagnumCharm.singleton
    public_ep = '{}/v1'.format(charm.public_url)
    internal_ep = '{}/v1'.format(charm.internal_url)
    admin_ep = '{}/v1'.format(charm.admin_url)
    keystone.register_endpoints(charm.service_type,
                                charm.region,
                                public_ep,
                                internal_ep,
                                admin_ep)


class MagnumCharm(charms_openstack.charm.HAOpenStackCharm):

    abstract_class = False
    release = 'queens'
    name = 'magnum'
    packages = PACKAGES
    api_ports = {
        'magnum-api': {
            os_ip.PUBLIC: 9511,
            os_ip.ADMIN: 9511,
            os_ip.INTERNAL: 9511,
        }
    }
    service_type = 'magnum'
    default_service = 'magnum-api'
    services = ['magnum-api', 'magnum-conductor']
    sync_cmd = ['magnum-db-manage', 'upgrade']

    required_relations = [
        'shared-db', 'amqp', 'identity-service', 'trustee-credentials']

    restart_map = {
        MAGNUM_CONF: services,
    }

    ha_resources = ['vips', 'haproxy']

    # Package for release version detection
    release_pkg = 'magnum-common'

    # Package codename map for magnum-common
    package_codenames = {
        'magnum-common': collections.OrderedDict([
            ('6', 'queens'),
        ]),
    }

    group = "magnum"

    def get_amqp_credentials(self):
        """Provide the default amqp username and vhost as a tuple.

        :returns (username, host): two strings to send to the amqp provider.
        """
        return (self.config['rabbit-user'], self.config['rabbit-vhost'])

    def get_database_setup(self):
        return [
            dict(
                database=self.config['database'],
                username=self.config['database-user'], )
        ]
