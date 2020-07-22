#!/bin/bash

service=
host=

usage()
{
    echo "usage:  --service   the name of the service to wait for"
    echo "        --host      ip address or hostname of swarm master"
    echo "----------------------------------------------------------"
    echo "        -h | --help"
}

if [[ "$1" == "-h" ]] || [[ "$1" == "--help" ]]; then
  usage
  exit 0
fi

# Assign positional parameters.
while [ "$1" != "" ]; do
    case $1 in
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
echo "Waiting for docker service '$service'"
echo ""

# Wait until given service has CurrentState=="Running [...]".
state=""
while [ "$state" != "Running" ]; do
  # the docker command will return a multiline table,
  # so first make the response one line by replacing line delimiters with spaces
  # and then cut the third word (first two being the table header "Current State")
  state=$(docker -H tcp://$host:2376 -D --tlsverify --tlscacert /run/secrets/SSL_CA_PEM --tlscert /run/secrets/SSL_CERT_PEM --tlskey /run/secrets/SSL_KEY_PEM service ps --format "table {{.CurrentState}}" $service | tr '\n' " " | cut -d" " -f 3)
  echo $state
  sleep 2
done
echo ""
