import logging
import os
import subprocess
import sys

import yaml

files_dir = ""


def execute_command(
        command,
        working_directory,
        environment_variables,
        executor,
        logger=logging,
        livestream=False
):
    logger_prefix = ""
    if executor:
        logger_prefix = executor + ": "

    process = subprocess.Popen(
        command,
        cwd=working_directory,
        env=environment_variables,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        shell=True,
    )

    logger.debug(logger_prefix + "command: " + command)

    stdout = ""
    for line in iter(process.stdout.readline, b''):
        line = str(line, "utf-8")
        stdout += line

        if livestream:
            sys.stdout.write(line)
        else:
            logger.debug(logger_prefix + "command output: " + line.rstrip())

    return_code = process.wait()
    stdout = stdout.rstrip()
    return stdout, return_code


def get_uploaded_files_path(pga_id):
    return os.path.join(files_dir, pga_id)


def get_uploaded_files_dict(pga_id):
    files_dict = {}
    directory = get_uploaded_files_path(pga_id)
    files = os.listdir(directory)
    for filename in files:
        name = filename.split(".")[0]
        yaml_dict = parse_yaml(os.path.join(directory, filename))
        yaml_dict["_filename"] = filename
        files_dict[name] = yaml_dict
    return files_dict


def get_filename_from_path(file_path):
    if file_path.__contains__("\\"):
        filename = file_path.split("\\")[-1].split(".")[0]
    else:
        filename = file_path.split("/")[-1].split(".")[0]
    return filename


def parse_yaml(yaml_file_path):
    with open(yaml_file_path, mode="r", encoding="utf-8") as yaml_file:
        content = yaml.safe_load(yaml_file) or {}
    return content


def __set_files_dir(path):
    global files_dir
    files_dir = os.path.join(path, 'files')
    os.makedirs(files_dir, exist_ok=True)
