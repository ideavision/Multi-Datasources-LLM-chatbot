from typing import Any
from typing import Type

from payserai.configs.constants import DocumentSource
from payserai.connectors.confluence.connector import ConfluenceConnector

from payserai.connectors.interfaces import BaseConnector
from payserai.connectors.interfaces import EventConnector
from payserai.connectors.interfaces import LoadConnector
from payserai.connectors.interfaces import PollConnector
from payserai.connectors.models import InputType


import json


class ConnectorMissingException(Exception):
    pass


def identify_connector_class(
    source: DocumentSource,
    input_type: InputType | None = None,
) -> Type[BaseConnector]:
    connector_map = {
        DocumentSource.CONFLUENCE: ConfluenceConnector,
    }
    connector_by_source = connector_map.get(source, {})

    if isinstance(connector_by_source, dict):
        if input_type is None:
            # If not specified, default to most exhaustive update
            connector = connector_by_source.get(InputType.LOAD_STATE)
        else:
            connector = connector_by_source.get(input_type)
    else:
        connector = connector_by_source
    if connector is None:
        raise ConnectorMissingException(f"Connector not found for source={source}")

    if any(
        [
            input_type == InputType.LOAD_STATE
            and not issubclass(connector, LoadConnector),
            input_type == InputType.POLL and not issubclass(connector, PollConnector),
            input_type == InputType.EVENT and not issubclass(connector, EventConnector),
        ]
    ):
        raise ConnectorMissingException(
            f"Connector for source={source} does not accept input_type={input_type}"
        )

    return connector


def load_confluence_config(config_file_path: str) -> dict:
    with open(config_file_path, "r") as file:
        return json.load(file)


def instantiate_connector(
    source: DocumentSource,
    input_type: InputType,
    connector_specific_config: dict[str, Any],
    credentials: dict[str, Any],
) -> tuple[BaseConnector, dict[str, Any] | None]:
    connector_class = identify_connector_class(source, input_type)

    if source == DocumentSource.CONFLUENCE:
        # Assuming 'confluence_config.json' is at the specified path
        confluence_config_path = "confluence_config.json"
        confluence_config = load_confluence_config(confluence_config_path)
        labels = confluence_config.get("labels", [])
        connector_specific_config["labels"] = labels

    connector = connector_class(**connector_specific_config)
    new_credentials = connector.load_credentials(credentials)

    return connector, new_credentials
