# Copyright 2018 Cloudbase Solutions


# TODO(gsamfira): properly order imports
from __future__ import absolute_import

import collections
import os
import subprocess
import shutil
import grp
import pwd

import charmhelpers.core.hookenv as hookenv

import charms_openstack.charm
import charms_openstack.adapters
import charms_openstack.ip as os_ip
from charms.layer import basic

PACKAGES = ['magnum-api', 'magnum-conductor', 'python-mysqldb']
MAGNUM_DIR = '/etc/magnum/'
MAGNUM_CONF = os.path.join(MAGNUM_DIR, "magnum.conf")
MAGNUM_PASTE_API = os.path.join(MAGNUM_DIR, "api-paste.ini")
SERVICE_NAME = "magnum"
MAGNUM_BINARIES = [
    "magnum-api",
    "magnum-conductor",
    "magnum-db-manage",
    "magnum-driver-manage"]
MAGNUM_API_SVC = 'magnum-api'
MAGNUM_CONDUCTOR_SVC = 'magnum-conductor'
MAGNUM_SERVICES = [MAGNUM_API_SVC, MAGNUM_CONDUCTOR_SVC]
MAGNUM_USER = "magnum"
MAGNUM_GROUP = "magnum"

OPENSTACK_RELEASE_KEY = 'magnum-charm.openstack-release-version'
INSTALL_TYPE_ARCHIVE = "archive"
INSTALL_TYPE_GIT = "git"
OPENSTACK_DEFAULT_BRANCH = "master"
INSTALL_PREFIX = "/opt/magnum"
VENV_DIR_PREFIX = os.path.join(INSTALL_PREFIX, "venvs")
DATA_DIR = os.path.join(INSTALL_PREFIX, "data")
CURRENT_VENV = os.path.join(INSTALL_PREFIX, "current")
MAGNUM_DB_MANAGE = os.path.join(CURRENT_VENV, "bin/magnum-db-manage")
DEFAULT_MAGNUM_REPO = "https://github.com/openstack/magnum"

PACKAGE_CODENAMES = {
    "6": "queens",
    "7": "rocky",
    "8": "stein",
    "9": "train",
    "10": "ussuri",
}

INSTALL_TYPES = (
    INSTALL_TYPE_ARCHIVE,
    INSTALL_TYPE_GIT,
)

SYSTEMD_TEMPLATE = """
[Unit]
Description=OpenStack %(service)s
After=ntp.service



[Service]
User=magnum
Group=magnum
Type=simple
WorkingDirectory=/var/lib/magnum
PermissionsStartOnly=true
ExecStartPre=/bin/mkdir -p /var/lock/magnum /var/log/magnum /var/lib/magnum
ExecStartPre=/bin/chown magnum:magnum /var/lock/magnum /var/lib/magnum
ExecStartPre=/bin/chown magnum:adm /var/log/magnum
ExecStart=%(binary)s --config-file=/etc/magnum/magnum.conf --log-file=/var/log/magnum/%(service)s.log
Restart=on-failure
LimitNOFILE=65535
TimeoutStopSec=15

[Install]
WantedBy=multi-user.target
"""

_SYSTEMD_SVC_FILE_FORMAT = "/lib/systemd/system/%(service)s.service"

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
        path3 = os.path.join(self._venv, "bin/pip3")
        if os.path.isfile(path3):
            return path3

        path = os.path.join(self._venv, "bin/pip")
        if os.path.isfile(path):
            return path
        raise ValueError(
            "Could not find pip in venv %s" % self._venv)        

    def pip_install(self, packages, update=False):
        cmd = [self._pip_bin, "install"]
        if update:
            cmd.append("-U")
        cmd.extend(packages)
        subprocess.check_call(cmd)

    def make_current(self):
        if os.path.exists(CURRENT_VENV):
            if os.path.islink(CURRENT_VENV):
                os.remove(CURRENT_VENV)
            else:
                shutil.rmtree(CURRENT_VENV)
        os.symlink(
            self._venv, CURRENT_VENV,
            target_is_directory=True)            


class GitHelper(object):

    def __init__(self, destination):
        self._dst = destination

    def clone(self, repo):
        if os.path.isdir(self._dst):
            return
        parent = os.path.dirname(self._dst)
        if os.path.isdir(parent) is False:
            os.makedirs(parent)
        subprocess.check_call(
            ["git", "clone", repo, self._dst])

    def _run_git(self, command):
        cmd = ["git", "-C", self._dst]
        cmd.extend(command)
        ret = subprocess.check_output(cmd)
        return ret.decode().splitlines()

    def checkout(self, branch):
        branches = self.list_branches()
        tags = self.list_tags()

        if branch in branches:
            self._run_git(
                ["checkout", branch])
        elif branch in tags:
            self._run_git(
                ["checkout", "-b", branch, branch])
        else:
            raise ValueError("Invalid branch %s" % branch)

    def list_tags(self):
        return list(set(self._run_git(["tag"])))
    
    def pull(self):
        self._run_git(["pull"])

    def list_branches(self):
        ret = self._run_git(["branch", "-a"])
        return list(set(
            map(lambda x: x.split()[-1].replace("remotes/origin/", ""),
            ret)))
        

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
        self._config = hookenv.config()
        self._venv_helper = VenvHelper(self._venv_path)
        self._magnum_source = os.path.join(DATA_DIR, SERVICE_NAME)
        self._git = GitHelper(self._magnum_source)
        self._magnum_api = os.path.join(
            CURRENT_VENV, "bin/magnum-api")
        self._magnum_conductor = os.path.join(
            CURRENT_VENV, "bin/magnum-conductor")
        self._magnum_db_manage = os.path.join(
            CURRENT_VENV, "bin/magnum-db-manage")
        self._svc_map = {
            MAGNUM_API_SVC: self._magnum_api,
            MAGNUM_CONDUCTOR_SVC: self._magnum_conductor,
        }

    def _get_install_source(self):
        install_type = self._config.get(
            "openstack-install-type", INSTALL_TYPE_GIT)
        if install_type not in INSTALL_TYPES:
            install_type = INSTALL_TYPE_GIT
        return install_type

    @property
    def _magnum_branch(self):
        branch = self._config.get(
            "openstack-install-branch", OPENSTACK_DEFAULT_BRANCH)
        return branch

    @property
    def _venv_name(self):
        branch = self._magnum_branch()
        return "magnum-%s" % branch.replace("/", "-")

    @property
    def _venv_path(self):
        return os.path.join(
            INSTALL_PREFIX, self._venv_name)

    @property
    def _project_repository(self):
        return self._config.get(
            "magnum-git-repo", DEFAULT_MAGNUM_REPO)

    def _ensure_prerequisites(self):
        basic.apt_install(self._PREREQUISITES)
        if os.path.isdir(VENV_DIR_PREFIX) is False:
            os.makedirs(VENV_DIR_PREFIX)
        if os.path.isdir(DATA_DIR) is False:
            os.makedirs(DATA_DIR)
        self._maybe_create_venv()

    def _maybe_create_venv(self):
        if os.path.isdir(self._venv_path):
            return
        subprocess.check_call(["python3", "-m", "venv", self._venv_path])
        self._venv_helper.pip_install(["wheel", "pip"], update=True)
        return

    def _ensure_repo(self):
        self._git.clone(self._project_repository)
        self._git.checkout(self._magnum_branch)
        self._git.pull()

    def _get_installed_version(self):
        if os.path.isfile(self._magnum_api) is False:
            return None
        ret = subprocess.check_output(
            [self._magnum_api, "--version"])
        ret_arr = ret.decode().splitlines()
        if len(ret_arr) == 0:
            return None
        return ret_arr[0]
    
    def _get_installed_version_codename(self):
        installed_version = self._get_installed_version()
        if installed_version is None:
            return None
        version_split = installed_version.split(".")
        if len(version_split) == 0:
            return None
        codename = PACKAGE_CODENAMES.get(version_split[0])
        return codename

    def _ensure_user_and_group(self):
        try:
            pwd.getpwnam(MAGNUM_USER)
        except:
            subprocess.check_call(
                ["useradd", "--create-home", "--system",
                 "--shell", "/bin/false",
                 "-d", "/var/lib/magnum", MAGNUM_USER])
        try:
            grp.getgrnam(MAGNUM_GROUP)
        except:
            subprocess.check_call(
                ["groupadd", "--system", MAGNUM_GROUP])

    def _ensure_directories(self):
        user = pwd.getpwnam(MAGNUM_USER)
        group = grp.getgrnam(MAGNUM_GROUP)
        if os.path.isdir(MAGNUM_DIR) is False:
            os.makedirs(MAGNUM_DIR)
        os.chown(MAGNUM_DIR, user.pw_uid, group.gr_gid)

    def _install_from_git(self):
        self._ensure_prerequisites()
        self._ensure_repo()
        self._venv_helper.pip_install(
            [self._magnum_source])
        self._venv_helper.make_current()
        self._ensure_user_and_group()
        self._ensure_directories()
        self._ensure_services()

    def _do_db_sync(self):
        if hookenv.is_leader() and self.sync_cmd:
            subprocess.check_call(self.sync_cmd)

    def _render_service_file(self, service):
        svc_file = _SYSTEMD_SVC_FILE_FORMAT % {
            "service": service}
        bin_path = self._svc_map.get(service)
        if bin_path is None:
            raise ValueError("invalid service %s" % service)
        with open(svc_file, "w") as fd:
            conf = SYSTEMD_TEMPLATE % {
                "binary": bin_path,
                "service": service,
            }
            fd.write(conf)

    def _service_file_exists(self, svc):
        svc_file = _SYSTEMD_SVC_FILE_FORMAT % {
            "service":svc}
        return os.path.isfile(svc_file)

    def _ensure_services(self):
        for svc in MAGNUM_SERVICES:
            if self._service_file_exists(svc) is False:
                self._render_service_file(svc)
                subprocess.check_call(["systemctl", "daemon-reload"])
                subprocess.check_call(["systemctl", "enable", svc])
                subprocess.check_call(["systemctl", "start", svc])

    def run_upgrade(self, interfaces_list=None):
        self._install_from_git()
        self._do_db_sync()

    def upgrade_if_available(self, interfaces_list):
        installed_version = self._get_installed_version_codename() or ""
        if self._magnum_branch.endswith(installed_version) is False:
            self.run_upgrade(interfaces_list=interfaces_list)
 
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
    services = MAGNUM_SERVICES
    sync_cmd = [self._magnum_db_manage, 'upgrade']

    required_relations = [
        'shared-db', 'amqp', 'identity-service', 'trustee-credentials']

    restart_map = {
        MAGNUM_CONF: services,
        MAGNUM_PASTE_API: [default_service,],
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
