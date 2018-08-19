# Charm Magnum


Charm to deploy Magnum in a Canonical OpenStack deployment


## Build charm

You will need to have the [trustee](https://github.com/gabriel-samfira/layer-trustee) interface copied in your ```$INTERFACE_PATH```.


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
juju deploy ./charm-magnum magnum --config openstack-origin="cloud:xenial-queens"

juju add-relation magnum mysql
juju add-relation magnum rabbitmq-server
juju add-relation magnum:identity-service keystone:identity-service
juju add-relation magnum:trustee-credentials keystone:trustee-credentials

```