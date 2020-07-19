#!/bin/bash

configs=""
configs_amount=
service=
host=

usage()
{
    echo "usage:  --configs   list of docker config names '<amount> <items...> --'"
    echo "        --service   the service to update"
    echo "        --host      ip address or hostname of swarm master"
    echo "------------------------------------------------------------------------"
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
                      configs="( "
                      while [ "$1" != "--" ]; do
                        configs+="$1 "
                      done
                      configs+=")"
                      shift  # shift the delimiter
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

# TODO: read and de-/serialize the array for input (like so: (runner--0 mutation--0 ...) )
# https://www.google.com/search?client=firefox-b-d&q=bash+shell+append+item+to+array
# https://linuxhint.com/bash_append_array/

# Confirming input.
echo "SSH into: $host"
echo "Updating docker service '$service' with configs: $configs"
echo ""

# Creating config params list.
param_list=""
for (( i=0; i<${#configs[@]}; i++ ))
do
  param_list+="--config-add ${configs[$i]} "
done

echo param_list
echo ""

# Update service with secrets for given certificates path and exit.
#docker -H tcp://$host:2376 -D --tlsverify --tlscacert $config_path/ca.pem --tlscert $config_path/cert.pem --tlskey $config_path/key.pem service update --secret-add SSL_CA_PEM --secret-add SSL_CERT_PEM --secret-add SSL_KEY_PEM manager
docker -H tcp://$host:2376 -D service update --update-monitor 0s --update-parallelism 0 --detach $param_list$service
# param_list has an extra space at the end from extension above, or is an empty string


# Since "docker-machine ssh" opens another interactive shell, give execution feedback.
echo ""
echo ""
read -p "Press ENTER to terminate:"
