import logging
import os

from flask import Flask, jsonify, make_response, request
from werkzeug.utils import secure_filename

from orchestrator.docker_orchestrator import DockerOrchestrator
from utililities import utils

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


@mgr.route("/files", methods=["GET"])
def get_files():
    """
    Get all uploaded YAML files as a dictionary.
    :return: dict of uploaded YAML files as JSON
    """
    files_dict = utils.get_uploaded_files_dict()  # TODO: require pga-id to lookup subdir
    return jsonify(files_dict)


# TODO 104: make POST request only
@mgr.route("/pga", methods=["GET", "POST"])
def create_pga():
    """
    Run a new Parallel Genetic Algorithm in the cloud

    :return (dict): id of new pga
    """
    # TODO: convert files to docker configs? easier sharing across containers/services
    # Saves all the files that were uploaded with the request.
    filenames = request.files.keys()
    files_dir = utils.get_uploaded_files_path()  # TODO: make subdir for pga id, avoiding filename duplicates
    for filename in filenames:
        file = request.files[filename]
        file.save(os.path.join(files_dir, secure_filename(file.filename)))

    # Recognizes the correct orchestrator.
    master_host = request.args.get("master_host")
    orchestrator_name = request.args.get("orchestrator")
    if not orchestrator_name:
        raise Exception("No cloud orchestrator provided! Aborting deployment.")
    orchestrator = get_orchestrator(orchestrator_name, master_host)

    # Retrieves the configuration.
    config_file_path = request.args.get("config")
    if not config_file_path:
        raise Exception("No PGA configuration provided! Aborting deployment.")
    config_filename = utils.get_filename_from_path(config_file_path)
    config_path = os.path.join(utils.get_uploaded_files_path(), config_filename+".yml")
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
        # TODO 104: deploy rest of stack
        # Creates the new PGA.
        orchestrator.setup_pga(services=services, setups=setups, operators=operators,
                               population=population, properties=properties)

        # TODO 104: make files available to components (docker configs?)

    elif model == "Island":
        raise Exception("Island model not implemented yet. Aborting deployment.")  # TODO 204: implement island model
    else:
        raise Exception("Custom model detected.")  # TODO 205: implement for custom models

    return jsonify({"id": orchestrator.pga_id})


# @mgr.route("/pga", methods=["GET"])
# def get_all_pga():
#     return "OK"


@mgr.route("/pga/<int:pga_id>", methods=["GET"])
def get_pga(pga_id):
    print("getting pga {}".format(pga_id))
    return jsonify({
        "id": pga_id,
        "name": "other"
    })


def get_orchestrator(orchestrator_name, master_host):
    if orchestrator_name == "docker":
        return DockerOrchestrator(master_host)
    elif orchestrator_name == "kubernetes":
        print("Kubernetes orchestrator not yet implemented! Falling back to docker orchestrator.")
        return DockerOrchestrator(master_host)  # TODO 202: implement kubernetes orchestrator
    else:
        raise Exception("Unknown orchestrator requested!")


if __name__ == '__main__':
    mgr.run(host='0.0.0.0', debug=True)  # TODO: remove debug mode
