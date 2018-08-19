# Copyright 2018 Cloudbase Solutions

from __future__ import absolute_import

import charms.reactive as reactive
import charmhelpers.core.hookenv as hookenv

import charms_openstack.charm as charm
import charm.openstack.magnum.magnum as magnum  # noqa


# Use the charms.openstack defaults for common states and hooks
charm.use_defaults(
    'charm.installed',
    'amqp.connected',
    'shared-db.connected',
    'identity-service.available',  # enables SSL support
    'config.changed',
    'update-status')


@reactive.when('shared-db.available')
@reactive.when('identity-service.available')
@reactive.when('amqp.available')
@reactive.when('trustee-credentials.available')
def render_stuff(*args):
    hookenv.log("about to call the render_configs with {}".format(args))
    with charm.provide_charm_instance() as magnum_charm:
        magnum_charm.render_with_interfaces(
            charm.optional_interfaces(args))
        magnum_charm.assess_status()
    reactive.set_state('config.complete')


@reactive.when('trustee-credentials.connected')
def request_domain(interface):
    hookenv.log("requesting trustee domain credentials")
    config = hookenv.config()
    domain = config.get("trustee-domain", "magnum")
    domain_admin = config.get("trustee-admin", "magnum_domain_admin")
    interface.request_domain(domain, domain_admin)


@reactive.when('identity-service.connected')
def setup_endpoint(keystone):
    magnum.setup_endpoint(keystone)
    magnum.assess_status()


@reactive.when('config.complete')
@reactive.when_not('db.synced')
def run_db_migration():
    magnum.db_sync()
    magnum.restart_all()
    reactive.set_state('db.synced')
    magnum.assess_status()
