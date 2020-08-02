import logging
import os

from flask import Flask, jsonify, make_response, request
from werkzeug.utils import secure_filename

from orchestrator.docker_orchestrator import DockerOrchestrator
from utilities import utils

logging.basicConfig(level=logging.INFO)
# TODO: remove connector image and repo since no longer needed


# App initialization.
mgr = Flask(__name__)

# Create a directory in a known location to save files to.
utils.__set_files_dir(mgr.instance_path)


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

    logging.info("Creating new PGA: {}.".format(pga_id))

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

        # Creates the new PGA.
        all_services = utils.merge_dict(services, utils.merge_dict(setups, utils.merge_dict(
            operators, utils.merge_dict(population, properties))))
        model_dict = construct_model_dict(model, all_services)
        orchestrator.setup_pga(model_dict=model_dict, services=services, setups=setups, operators=operators,
                               population=population, properties=properties, file_names=file_names)
        logging.info("Distribute properties:")
        orchestrator.distribute_properties(properties=properties)
        logging.info("Initialize properties:")
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
    orchestrator = get_orchestrator(orchestrator_name, master_host, pga_id)

    # Starts the chosen PGA.
    logging.info("Starting PGA {}.".format(orchestrator.pga_id))
    orchestrator.start_pga()  # Makes a blocking call to Runner.

    return jsonify({
        "id": orchestrator.pga_id,
        "status": "finished"
    })


@mgr.route("/pga/<int:pga_id>/stop", methods=["PUT"])
def stop_pga(pga_id):
    # Recognizes the correct orchestrator.
    master_host = request.args.get("master_host")
    orchestrator_name = request.args.get("orchestrator")
    if not orchestrator_name:
        raise Exception("No cloud orchestrator provided! Aborting deployment.")
    orchestrator = get_orchestrator(orchestrator_name, master_host, pga_id)

    # Stops the chosen PGA.
    logging.info("Terminating PGA {}.".format(orchestrator.pga_id))
    exit_code = orchestrator.stop_pga()
    if exit_code != 202:
        logging.error("Terminating PGA {id_} finished with unexpected exit code: {code_}".format(
            id_=orchestrator.pga_id,
            code_=exit_code,
        ))

    # Removes the PGA components.
    logging.info("Removing components of PGA {}.".format(orchestrator.pga_id))
    orchestrator.remove_pga()

    return jsonify({
        "id": orchestrator.pga_id,
        "status": "removed"
    })


@mgr.route("/pga/<int:pga_id>/result", methods=["PUT"])
def result_from_pga(pga_id):
    # Recognizes the correct orchestrator.
    master_host = request.args.get("master_host")
    orchestrator_name = request.args.get("orchestrator")
    if not orchestrator_name:
        raise Exception("No cloud orchestrator provided! Aborting deployment.")
    orchestrator = get_orchestrator(orchestrator_name, master_host, pga_id)

    # Retrieves the result from the PGA.
    logging.info("Received result from PGA {}.".format(pga_id))
    result = request.data
    logging.info(result)  # TODO: remove

    return make_response(jsonify(None), 204)


def get_orchestrator(orchestrator_name, master_host, pga_id=None):
    if orchestrator_name == "docker":
        return DockerOrchestrator(master_host, pga_id)
    elif orchestrator_name == "kubernetes":
        logging.error("Kubernetes orchestrator not yet implemented! Falling back to docker orchestrator.")
        return DockerOrchestrator(master_host, pga_id)  # TODO 202: implement kubernetes orchestrator
    else:
        raise Exception("Unknown orchestrator requested!")


def construct_model_dict(model, all_services):
    if model == "Master-Slave":
        # init = RUN/(INIT/)FE/RUN
        # model = RUN/SEL/CO/MUT/FE/RUN
        model_dict = {
            "runner": {
                "source": "generation",
                "init_gen": "initializer",
                "init_eval": "fitness",
                "pga": "selection"
            },
            "initializer": {
                "source": "initializer",
                "target": "fitness"
            },
            "selection": {
                "source": "selection",
                "target": "crossover"
            },
            "crossover": {
                "source": "crossover",
                "target": "mutation"
            },
            "mutation": {
                "source": "mutation",
                "target": "fitness"
            },
            "fitness": {
                "source": "fitness",
                "target": "generation"
            }
        }
    elif model == "Island":
        model_dict = {}
        raise Exception("Island model not implemented yet!")
    else:
        model_dict = {}
        raise Exception("Custom models not implemented yet!")
    return model_dict


if __name__ == "__main__":
    mgr.run(host="0.0.0.0")
