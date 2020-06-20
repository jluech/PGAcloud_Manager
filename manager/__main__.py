from flask import Flask

SELECTION_QUEUE_NAME = '{pga_name_}@selection.queue'
CROSSOVER_QUEUE_NAME = '{pga_name_}@crossover.queue'
MUTATION_QUEUE_NAME = '{pga_name_}@mutation.queue'


# App initialization.
mgr = Flask(__name__)


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
    return


@mgr.route("/pga", methods=["GET"])
def get_all_pga():
    print("getting all pga")
    return


@mgr.route("/pga/<number:pga_id>", methods=["GET"])
def get_pga(pga_id):
    print("getting pga " + pga_id)
    return


if __name__ == '__main__':
    mgr.run(host='0.0.0.0', debug=False)
