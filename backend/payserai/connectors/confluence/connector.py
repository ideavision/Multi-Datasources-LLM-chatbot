import base64
from collections.abc import Callable
from collections.abc import Collection
from datetime import datetime
from datetime import timezone
from typing import Any
from typing import cast
from urllib.parse import urlparse
import requests
from requests.auth import HTTPBasicAuth


from atlassian import Confluence  # type:ignore
from requests import HTTPError

from payserai.configs.app_configs import CONFLUENCE_CONNECTOR_LABELS_TO_SKIP
from payserai.configs.app_configs import CONTINUE_ON_CONNECTOR_FAILURE
from payserai.configs.app_configs import INDEX_BATCH_SIZE
from payserai.configs.constants import DocumentSource
from payserai.connectors.cross_connector_utils.html_utils import parse_html_page_basic
from payserai.connectors.interfaces import GenerateDocumentsOutput
from payserai.connectors.interfaces import LoadConnector
from payserai.connectors.interfaces import PollConnector
from payserai.connectors.interfaces import SecondsSinceUnixEpoch
from payserai.connectors.models import ConnectorMissingCredentialError
from payserai.connectors.models import Document
from payserai.connectors.models import Section
from payserai.utils.logger import setup_logger


logger = setup_logger()


def _extract_confluence_keys_from_cloud_url(wiki_url: str) -> tuple[str, str]:
    parsed_url = urlparse(wiki_url)
    wiki_base = (
        parsed_url.scheme
        + "://"
        + parsed_url.netloc
        + parsed_url.path.split("/spaces")[0]
    )
    space = parsed_url.path.split("/")[3]
    return wiki_base, space


def _extract_confluence_keys_from_datacenter_url(wiki_url: str) -> tuple[str, str]:
    DISPLAY = "/display/"
    parsed_url = urlparse(wiki_url)
    wiki_base = (
        parsed_url.scheme
        + "://"
        + parsed_url.netloc
        + parsed_url.path.split(DISPLAY)[0]
    )
    space = DISPLAY.join(parsed_url.path.split(DISPLAY)[1:]).split("/")[0]
    return wiki_base, space


def extract_confluence_keys_from_url(wiki_url: str) -> tuple[str, str, bool]:
    is_confluence_cloud = ".atlassian.net/wiki/spaces/" in wiki_url
    try:
        if is_confluence_cloud:
            wiki_base, space = _extract_confluence_keys_from_cloud_url(wiki_url)
        else:
            wiki_base, space = _extract_confluence_keys_from_datacenter_url(wiki_url)
    except Exception as e:
        error_msg = f"Not a valid Confluence Wiki Link, unable to extract wiki base and space names. Exception: {e}"
        logger.error(error_msg)
        raise ValueError(error_msg)
    return wiki_base, space, is_confluence_cloud


def _comment_dfs(
    comments_str: str,
    comment_pages: Collection[dict[str, Any]],
    confluence_client: Confluence,
) -> str:
    for comment_page in comment_pages:
        comment_html = comment_page["body"]["storage"]["value"]
        comments_str += "\nComment:\n" + parse_html_page_basic(comment_html)
        child_comment_pages = confluence_client.get_page_child_by_type(
            comment_page["id"],
            type="comment",
            start=None,
            limit=None,
            expand="body.storage.value",
        )
        comments_str = _comment_dfs(
            comments_str, child_comment_pages, confluence_client
        )
    return comments_str


class ConfluenceConnector(LoadConnector, PollConnector):
    def __init__(
        self,
        wiki_page_url: str,
        labels: list[str],
        batch_size: int = INDEX_BATCH_SIZE,
        continue_on_failure: bool = CONTINUE_ON_CONNECTOR_FAILURE,
    ):
        self.batch_size = batch_size
        self.continue_on_failure = continue_on_failure
        self.labels = labels  # Accepts multiple labels
        self.labels_to_skip = set()
        self.wiki_base, self.space, self.is_cloud = extract_confluence_keys_from_url(
            wiki_page_url
        )
        self.confluence_client: Confluence | None = None

    def load_credentials(self, credentials: dict[str, Any]) -> None:
        self.username = credentials.get("confluence_username")
        self.password_or_token = credentials.get("confluence_access_token")
        self.confluence_client = Confluence(
            url=self.wiki_base,
            username=self.username,
            password=self.password_or_token,
            cloud=self.is_cloud,
        )

    # def _fetch_pages(self, labels: list[str], start_at: int = 0) -> list[Document]:
    # documents = []
    # for label in labels:
    #     auth = base64.b64encode(f'{self.username}:{self.password_or_token}'.encode('ascii')).decode('ascii')
    #     headers = {'Authorization': f'Basic {auth}'}
    #     cql = f"type=page AND label='{label}'"
    #     url = f'{self.wiki_base}/rest/api/content/search?cql={cql}&start={start_at}&limit={self.batch_size}'
    #     response = requests.get(url, headers=headers)
    #     if response.status_code != 200:
    #         raise Exception(f"Failed to fetch pages with label '{label}'. Status Code: {response.status_code}")
    #     pages_data = response.json()

    
    def _fetch_pages(self, labels: list[str], start_at: int = 0) -> list[Document]:
        documents = []
        if not labels:
            return documents  # Return empty list if no labels are provided

        # Construct the CQL query to include all labels
        labels_query = ",".join([f"'{label}'" for label in labels])
        cql = f"type=page AND label IN ({labels_query})"

        # Rest of your existing logic for making the API request
        url = f"{self.wiki_base}/rest/api/content/search?cql={cql}&start={start_at}&limit={self.batch_size}"
        auth = base64.b64encode(
            f"{self.username}:{self.password_or_token}".encode("ascii")
        ).decode("ascii")
        headers = {"Authorization": f"Basic {auth}"}

        response = requests.get(url, headers=headers)
        if response.status_code != 200:
            raise Exception(
                f"Failed to fetch pages with labels {labels}. Status Code: {response.status_code}"
            )

        pages_data = response.json()
        for page in pages_data.get("results", []):
            page_id = page.get("id")
            page_title = page.get("title")
            page_url = f"{self.wiki_base}/pages/viewpage.action?pageId={page_id}"
            page_details = self.confluence_client.get_page_by_id(
                page_id, expand="body.storage"
            )
            page_html = page_details.get("body", {}).get("storage", {}).get("value", "")
            page_text = parse_html_page_basic(page_html)
            last_modified = datetime.utcnow().replace(tzinfo=timezone.utc)
            author_info = page.get("history", {}).get("createdBy", {})
            author = author_info.get("displayName")
            documents.append(
                Document(
                    id=page_url,
                    sections=[Section(link=page_url, text=page_text)],
                    source=DocumentSource.CONFLUENCE,
                    semantic_identifier=page_title,
                    doc_updated_at=last_modified,
                    primary_owners=[author] if author else None,
                    metadata={},
                )
            )
        return documents

    def _get_doc_batch(
        self, labels: list[str], start_ind: int
    ) -> tuple[list[Document], int]:
        doc_batch = self._fetch_pages(labels, start_ind)
        num_pages = len(doc_batch)
        return doc_batch, num_pages

    def load_from_state(self) -> GenerateDocumentsOutput:
        if self.confluence_client is None:
            raise ConnectorMissingCredentialError("Confluence")
        start_ind = 0
        while True:
            doc_batch, num_pages = self._get_doc_batch(self.labels, start_ind)
            start_ind += num_pages
            if doc_batch:
                yield doc_batch
            if num_pages < self.batch_size:
                break

    def poll_source(
        self, start: SecondsSinceUnixEpoch, end: SecondsSinceUnixEpoch
    ) -> GenerateDocumentsOutput:
        start_ind = 0
        while True:
            doc_batch, num_pages = self._get_doc_batch(self.labels, start_ind)
            if not doc_batch:
                break
            yield doc_batch
            start_ind += num_pages
            if num_pages < self.batch_size:
                break


if __name__ == "__main__":
    import os

    # config_file_path = os.getenv('CONFLUENCE_CONFIG_PATH', 'confluence_config.json')
    # confluence_config = load_confluence_config(config_file_path)
    # connector = ConfluenceConnector(os.environ["CONFLUENCE_TEST_SPACE_URL"], confluence_config)

    connector = ConfluenceConnector(os.environ["CONFLUENCE_TEST_SPACE_URL"], labels)
    connector.load_credentials(
        {
            "confluence_username": os.environ["CONFLUENCE_USER_NAME"],
            "confluence_access_token": os.environ["CONFLUENCE_ACCESS_TOKEN"],
        }
    )

    document_batches = connector.load_from_state()
    for batch in document_batches:
        print(batch)
