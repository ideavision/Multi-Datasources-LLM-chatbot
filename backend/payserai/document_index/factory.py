from payserai.document_index.interfaces import DocumentIndex
from payserai.document_index.vespa.index import VespaIndex


def get_default_document_index() -> DocumentIndex:
    # Currently only supporting Vespa
    return VespaIndex()
