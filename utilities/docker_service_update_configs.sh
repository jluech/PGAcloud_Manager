#!/bin/bash

configs=""
service=
host=

usage()
{
    echo "usage:  --configs   list of docker config names [items... --]"
    echo "        --service   the service to update"
    echo "        --host      ip address or hostname of swarm master"
    echo "-------------------------------------------------------------"
    echo "        -h | --help"
}

if [[ "$1" == "-h" ]] || [[ "$1" == "--help" ]]; then
  usage
  exit 0
fi

# Assign positional parameters.
while [ "$1" != "" ]; do
    case $1 in
        --configs )   shift
                      configs=()
                      while [ "$1" != "--" ]; do
                        configs+=("$1")
                        shift
                      done
                      ;;
        --service )   shift
                      service=$1
                      ;;
        --host )      shift
                      host=$1
                      ;;
        * )           usage
                      exit 1
    esac
    shift
done

# Confirming input.
echo "SSH into: $host"
echo "Updating docker service '$service' with configs: ${configs[*]}"
echo ""

# Creating config params list.
param_list=""
for (( i=0; i<${#configs[@]}; i++ ))
do
  param_list+="--config-add ${configs[$i]} "
done

# Update service with secrets for given certificates path and exit.
docker -H tcp://$host:2376 -D --tlsverify --tlscacert /run/secrets/SSL_CA_PEM --tlscert /run/secrets/SSL_CERT_PEM --tlskey /run/secrets/SSL_KEY_PEM service update --update-monitor 0s --update-parallelism 0 --detach $param_list$service
