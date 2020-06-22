from flask import Flask, jsonify, make_response

SELECTION_QUEUE_NAME = '{pga_name_}@selection.queue'
CROSSOVER_QUEUE_NAME = '{pga_name_}@crossover.queue'
MUTATION_QUEUE_NAME = '{pga_name_}@mutation.queue'


# App initialization.
mgr = Flask(__name__)


@mgr.errorhandler(404)
def not_found(error):
    return make_response(jsonify({'error': 'Not found'}), 404)


@mgr.route("/status", methods=["GET"])
def status():
    return "Status: OK"


@mgr.route("/pga", methods=["POST"])
def run_pga():
    """
    Run a new Parallel Genetic Algorithm in the cloud

    :return:
    """
    print("creating pga")
    return {id: 123}


@mgr.route("/pga", methods=["GET"])
def get_all_pga():
    print("getting all pga")
    return "getting all pga"


@mgr.route("/pga/<int:pga_id>", methods=["GET"])
def get_pga(pga_id):
    print("getting pga {}".format(pga_id))
    return "getting pga {}".format(pga_id)


if __name__ == '__main__':
    mgr.run(host='0.0.0.0', debug=False)
