import logging
import os

from flask import Flask, jsonify, make_response, request
from werkzeug.utils import secure_filename

from orchestrator.docker_orchestrator import DockerOrchestrator
from utilities import utils

logging.basicConfig(level=logging.DEBUG)  # TODO: remove and reduce to INFO

SELECTION_QUEUE_NAME = '{pga_name_}@selection.queue'
CROSSOVER_QUEUE_NAME = '{pga_name_}@crossover.queue'
MUTATION_QUEUE_NAME = '{pga_name_}@mutation.queue'


# App initialization.
mgr = Flask(__name__)

# Create a directory in a known location to save files to.
utils.__set_files_dir(mgr.instance_path)


@mgr.errorhandler(404)
def not_found(error):
    return make_response(jsonify({'error': 'Not found'}), 404)


@mgr.route("/status", methods=["GET"])
def status():
    return "OK"


@mgr.route("/files/<int:pga_id>", methods=["GET"])
def get_files(pga_id):
    """
    Get all uploaded YAML files as a dictionary.
    :return: dict of uploaded YAML files as JSON
    """
    files_dict = utils.get_uploaded_files_dict(pga_id)
    return jsonify(files_dict)


@mgr.route("/pga", methods=["POST"])
def create_pga():
    """
    Creates a new Parallel Genetic Algorithm in the cloud.

    :arg master_host: the ip address or hostname of the master node.
    :type master_host: str

    :arg orchestrator: the chosen cloud orchestrator.
    :type orchestrator: str

    :return (dict): id [int] and model [str] of new pga
    """
    # Recognizes the correct orchestrator.
    master_host = request.args.get("master_host")
    orchestrator_name = request.args.get("orchestrator")
    if not orchestrator_name:
        raise Exception("No cloud orchestrator provided! Aborting deployment.")
    orchestrator = get_orchestrator(orchestrator_name, master_host)
    pga_id = orchestrator.pga_id

    # Saves all the files that were uploaded with the request.
    file_keys = [*request.files]
    utils.create_pga_subdir(pga_id)
    files_dir = utils.get_uploaded_files_path(pga_id)
    file_names = []
    if "config" not in file_keys:
        raise Exception("No PGA configuration provided! Aborting deployment.")
    for file_key in file_keys:
        file = request.files[file_key]
        if file_key == "config":
            file_name = secure_filename("config.yml")
        elif file_key == "population":
            file_name = secure_filename("population.yml")
        else:
            file_name = secure_filename(file.filename)
        file_names.append(file_name)
        file.save(os.path.join(files_dir, file_name))

    # Retrieves the configuration and appends the current PGAs id.
    config_path = os.path.join(files_dir, "config.yml")
    config_file = open(config_path, mode="a")
    config_file.write("\npga_id: {id_}\n".format(id_=pga_id))
    config_file.close()
    configuration = utils.parse_yaml(config_path)

    # Determines the model to deploy.
    model = configuration.get("model")
    if not model:
        raise Exception("No PGA model provided! Aborting deployment.")
    if model == "Master-Slave":
        # Retrieves the configuration details.
        services = {}
        services_config = configuration.get("services")
        for service_key in [*services_config]:
            service = services_config.get(service_key)
            services[service.get("name")] = service

        setups = {}
        images_config = configuration.get("setups")
        for service_key in [*images_config]:
            service = images_config.get(service_key)
            setups[service.get("name")] = service

        operators = {}
        operators_config = configuration.get("operators")
        for service_key in [*operators_config]:
            service = operators_config.get(service_key)
            operators[service.get("name")] = service

        population = {}
        population_config = configuration.get("population")
        for population_key in [*population_config]:
            population[population_key] = population_config.get(population_key)

        properties = {}
        properties_config = configuration.get("properties")
        for property_key in [*properties_config]:
            properties[property_key] = properties_config.get(property_key)

        # TODO 104: deploy INIT image if configuration.get("properties").get("USE_INIT")
        # Creates the new PGA.
        orchestrator.setup_pga(services=services, setups=setups, operators=operators,
                               population=population, properties=properties, file_names=file_names)
        orchestrator.distribute_properties(properties=properties)
        orchestrator.initialize_population(population=population)
    elif model == "Island":
        raise Exception("Island model not implemented yet. Aborting deployment.")  # TODO 204: implement island model
    else:
        raise Exception("Custom model detected.")  # TODO 205: implement for custom models

    return jsonify({
        "id": orchestrator.pga_id,
        "model": model,
        "status": "created"
    })


@mgr.route("/pga/<int:pga_id>/start", methods=["PUT"])
def start_pga(pga_id):
    """
    Starts the PGA identified by the pga_id route param.

    :param pga_id: the PGA id of the PGA to be started.
    :type pga_id: int

    :arg orchestrator: the chosen cloud orchestrator.
    :type orchestrator: str
    """
    # Recognizes the correct orchestrator.
    master_host = request.args.get("master_host")
    orchestrator_name = request.args.get("orchestrator")
    if not orchestrator_name:
        raise Exception("No cloud orchestrator provided! Aborting deployment.")
    orchestrator = get_orchestrator(orchestrator_name, master_host)

    # Starts the chosen PGA.
    orchestrator.pga_id = pga_id
    logging.debug("Starting PGA {}.".format(orchestrator.pga_id))
    orchestrator.start_pga()

    return jsonify({
        "id": orchestrator.pga_id,
        "status": "started"
    })


def get_orchestrator(orchestrator_name, master_host, pga_id=None):
    if orchestrator_name == "docker":
        return DockerOrchestrator(master_host, pga_id)
    elif orchestrator_name == "kubernetes":
        logging.error("Kubernetes orchestrator not yet implemented! Falling back to docker orchestrator.")
        return DockerOrchestrator(master_host, pga_id)  # TODO 202: implement kubernetes orchestrator
    else:
        raise Exception("Unknown orchestrator requested!")


if __name__ == "__main__":
    mgr.run(host="0.0.0.0", debug=True)  # TODO: remove debug mode
