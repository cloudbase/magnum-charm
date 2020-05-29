# Charm Magnum


Charm to deploy Magnum in a Canonical OpenStack deployment


## Build charm

```bash
export CHARM_BASE="$HOME/work/charms"
export JUJU_REPOSITORY="$CHARM_BASE/build"
export INTERFACE_PATH="$CHARM_BASE/interfaces"
export LAYER_PATH="$CHARM_BASE/layers"

mkdir -p $JUJU_REPOSITORY
mkdir $INTERFACE_PATH
mkdir $LAYER_PATH

cd charm-magnum
charm build
```


## Deploy charm

```bash
juju deploy ./charm-magnum magnum --config openstack-origin="cloud:bionic-train"

juju add-relation magnum mysql
juju add-relation magnum rabbitmq-server
juju add-relation magnum:identity-service keystone:identity-service
```

After the charm is deployed and all relations have been established, you must run the ```domain-setup``` action to finalize the deployment. This action can be run on any unit.

```bash
juju run-action magnum/0 domain-setup
```
