#!/bin/bash

cert_path=
host=

usage()
{
    echo "usage:  --certs   path to SSL certificates"
    echo "        --host    ip address or hostname of swarm master"
    echo "--------------------------------------------------------"
    echo "        -h | --help"
}

if [[ "$1" == "-h" ]] || [[ "$1" == "--help" ]]; then
  usage
  exit 0
fi

# Assign positional parameters.
while [ "$1" != "" ]; do
    case $1 in
        --certs )   shift
                    cert_path=$1
                    ;;
        --host )    shift
                    host=$1
                    ;;
        * )         usage
                    exit 1
    esac
    shift
done

# Confirming input.
echo "SSH into: $host"
echo "Updating docker service with secrets for SSL certificates in $cert_path"
echo ""

# Update service with secrets for given certificates path and exit.
docker -H tcp://$host:2376 -D --tlsverify --tlscacert $cert_path/ca.pem --tlscert $cert_path/cert.pem --tlskey $cert_path/key.pem service update --secret-add SSL_CA_PEM --secret-add SSL_CERT_PEM --secret-add SSL_KEY_PEM manager
