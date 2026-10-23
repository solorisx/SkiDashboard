import requests
import gzip
import shutil
import os
import logging

# Get an instance of a logger
logger = logging.getLogger(__name__)


def load_osm():
    url = "https://www.opensnowmap.org/download/planet_pistes.osm.gz"
    state_url = "https://www.opensnowmap.org/download/planet_pistes-state.txt"
    dest = "planet_pistes-osmium.osm"
    dest_compressed = "planet_pistes.osm.gz"
    dest_state = "planet_pistes-state.txt"
    updated = False

    # Download the state file
    state_response = requests.get(state_url, stream=True)

    logger.debug(f"Working directory: {os.getcwd()}")
    logger.debug(f"Downloading state file from {state_url}")
    logger.debug(f"State file response status code: {state_response.status_code}")
    logger.debug(f"State file response content: {state_response.text}")
    logger.debug(f"Checking if state file exists at {dest_state}: {os.path.exists(dest_state)}")
    logger.debug(f"Checking if OSM file exists at {dest}: {os.path.exists(dest)}")

    if state_response.status_code == 200:
        new_state = state_response.text.strip()
        if os.path.exists(dest_state):
            with open(dest_state, "r") as f:
                current_state = f.read().strip()
        else:
            current_state = None

        # Compare state files

        logger.debug(f"Current state: {current_state}")
        logger.debug(f"New state: {new_state}")

        if current_state != new_state:
            # Download the OSM file
            response = requests.get(url, stream=True)
            if response.status_code == 200:
                with open(dest_compressed, "wb") as f:
                    f.write(response.content)

                # Extract the compressed file
                with gzip.open(dest_compressed, "rb") as f_in:
                    with open(dest, "wb") as f_out:
                        shutil.copyfileobj(f_in, f_out)

                # Remove the compressed file
                os.remove(dest_compressed)

                # Save the new state file
                with open(dest_state, "w") as f:
                    f.write(new_state)

                updated = True
                logging.info(f"File downloaded and extracted to {dest}, file timestamp {new_state}")
            else:
                updated = False
                logging.error(f"Failed to download file, status code: {response.status_code}")
        else:
            updated = False
            logging.info("File is up to date. No download needed.")
    else:
        updated = False
        logging.error(f"Failed to download state file, status code: {state_response.status_code}")

    return updated
