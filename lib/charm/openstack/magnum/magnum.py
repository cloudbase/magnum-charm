# Copyright 2018 Cloudbase Solutions


# TODO(gsamfira): properly order imports
from __future__ import absolute_import

import collections

import charmhelpers.core.hookenv as hookenv

import charms_openstack.charm
import charms_openstack.adapters
import charms_openstack.ip as os_ip
from charms.layer import basic
import subprocess

PACKAGES = ['magnum-api', 'magnum-conductor', 'python-mysqldb']
MAGNUM_DIR = '/etc/magnum/'
MAGNUM_CONF = os.path.join(MAGNUM_DIR, "magnum.conf")
SERVICE_NAME = "magnum"

OPENSTACK_RELEASE_KEY = 'magnum-charm.openstack-release-version'
INSTALL_TYPE_ARCHIVE = "archive"
INSTALL_TYPE_GIT = "git"
OPENSTACK_DEFAULT_BRANCH = "master"
INSTALL_PREFIX = "/opt/magnum"
VENV_DIR_PREFIX = os.path.join(INSTALL_PREFIX, "venvs")
DATA_DIR = os.path.join(INSTALL_PREFIX, "data")
DEFAULT_MAGNUM_REPO = "https://github.com/openstack/magnum"

INSTALL_TYPES = (
    INSTALL_TYPE_ARCHIVE,
    INSTALL_TYPE_GIT,
)

# select the default release function
charms_openstack.charm.use_defaults('charm.default-select-release')


def db_sync_done():
    return MagnumCharm.singleton.db_sync_done()


def restart_all():
    MagnumCharm.singleton.restart_all()


def db_sync():
    MagnumCharm.singleton.db_sync()


def configure_ha_resources(hacluster):
    MagnumCharm.singleton.configure_ha_resources(hacluster)


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


class VenvHelper(object):

    def __init__(self, venv_path):
        self._venv = venv_path

    @property
    def _pip_bin(self):
        path3 = os.path.join(
            self._venv,
            "bin/pip3")
        if os.path.isfile(path3):
            return path

        path = os.path.join(
            self._venv,
            "bin/pip")
        if os.path.isfile(path3):
            return path
        raise ValueError(
            "Could not find pip in venv %s" % self._venv)        

    def pip_install(self, update=False, packages):
        cmd = [self._pip_bin, "install"]
        if update:
            cmd.append("-U")
        cmd.extend(packages)
        subprocess.check_call(cmd)


class GitHelper(object):

    def __init__(self, destination):
        self._dst = destination

    def clone(self, repo):
        if os.path.isdir(self._dst):
            raise ValueError("%s already exists" % self._dst)
        parent = os.path.dirname(self._dst)
        if os.path.isdir(parent) is False:
            os.makedirs(parent)

        subprocess.check_call(
            ["git", "clone", repo, self._dst])

    def _run_git(self, command):
        cmd = ["git", "-C", self._dst]
        cmd.extend(command)
        ret = subprocess.check_output(cmd)
        return ret.decode().split()

    def checkout(self, branch):
        branches = self.list_branches()
        tags = self.list_tags()

        if branch in branches:
            self._run_git(
                ["checkout", branch])
        elif branch in tags:
            elf._run_git(
                ["checkout", "-b", branch, branch])
        else:
            raise ValueError("Invalid branch %s" % branch)

    def list_tags(self):
        ret = self._run_git(["tag"])
        return ret.decode().splitlines()

    def list_branches(self):
        ret = self._run_git(["branch", "-a"])
        return list(
            map(lambda x: x.split()[-1],
            ret.decode().splitlines()))
        

class GitInstaller(charms_openstack.charm.HAOpenStackCharm):
    _PREREQUISITES = [
        "python-dev",
        "python3-dev",
        "python3-pip",
        "libssl-dev",
        "libxml2-dev",
        "libmysqlclient-dev",
        "libxslt-dev",
        "libpq-dev",
        "git",
        "libffi-dev",
        "gettext",
        "build-essential",
    ]

    def __init__(self, *args, **kw):
        super().__init__(*args, **kw)
        self._venv_helper = VenvHelper(self._venv_path)
        self._magnum_source = os.path.join(DATA_DIR, SERVICE_NAME)
        self._git = GitHelper(self._magnum_source)

    def _get_install_source(self):
        install_type = config.get(
            "openstack-install-type", INSTALL_TYPE_ARCHIVE)
        if install_type not in INSTALL_TYPES:
            install_type = INSTALL_TYPE_ARCHIVE
        return install_type

    @property
    def _magnum_branch(self):
        return config.get(
            "openstack-install-branch", OPENSTACK_DEFAULT_BRANCH)

    @property
    def _venv_name(self):
        branch = self._get_magnum_branch()
        return "magnum-%s" % branch

    @property
    def _venv_path(self):
        return os.path.join(
            INSTALL_PREFIX, self._venv_name)

    @property
    def _project_repository(self):
        return config.get(
            "magnum-git-repo", DEFAULT_MAGNUM_REPO)

    def _ensure_prerequisites(self):
        basic.apt_install(_PREREQUISITES)
        if os.path.isdir(VENV_DIR_PREFIX) is False:
            os.makedirs(VENV_DIR_PREFIX)
        if os.path.isdir(DATA_DIR) is False:
            os.makedirs(DATA_DIR)
        self._maybe_create_venv()

    def _maybe_create_venv(self):
        if os.path.isdir(self._venv_path):
            return
        subprocess.check_call(["python3", "-m", "venv", self._venv_path])
        self._venv_helper.pip_install(update=True, ["wheel", "pip"])
        return

    def _ensure_repo(self):
        self._git.clone(self._project_repository)
        self._git.checkout(self._magnum_branch)

    def _install_from_git(self):
        self._ensure_prerequisites()
        self._ensure_repo()
        self._venv_helper.pip_install(
            [self._magnum_source])
 
    def install(self):
        install_type = self._get_install_source()
        if install_type == INSTALL_TYPE_ARCHIVE:
            super().install()
        else:
            self._install_from_git()


class MagnumCharm(GitInstaller):

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
