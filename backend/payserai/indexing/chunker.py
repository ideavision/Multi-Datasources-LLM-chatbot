import abc
from collections.abc import Callable

from llama_index.text_splitter import SentenceSplitter
from payserai.configs.app_configs import (BLURB_SIZE, CHUNK_OVERLAP,
                                          CHUNK_SIZE, MINI_CHUNK_SIZE)
from payserai.connectors.models import Document, Section
from payserai.indexing.models import DocAwareChunk
from payserai.search.search_nlp_models import get_default_tokenizer
from payserai.utils.text_processing import shared_precompare_cleanup
from transformers import AutoTokenizer  # type:ignore

SECTION_SEPARATOR = "\n\n"
ChunkFunc = Callable[[Document], list[DocAwareChunk]]


# This function extracts a blurb from the given text. A blurb is a short description or summary.
def extract_blurb(text: str, blurb_size: int) -> str:
    # Get the default tokenizer function
    token_count_func = get_default_tokenizer().tokenize
    
    # Create a SentenceSplitter object with the tokenizer function, blurb size and no overlap
    blurb_splitter = SentenceSplitter(
        tokenizer=token_count_func, chunk_size=blurb_size, chunk_overlap=0
    )

    # Split the text into chunks and return the first chunk as the blurb
    return blurb_splitter.split_text(text)[0]


def chunk_large_section(
def chunk_large_section(
    section: Section,
    document: Document,
    start_chunk_id: int,
    tokenizer: AutoTokenizer,
    chunk_size: int = CHUNK_SIZE,
    chunk_overlap: int = CHUNK_OVERLAP,
    blurb_size: int = BLURB_SIZE,
) -> list[DocAwareChunk]:
    # Get the text and link from the section
    section_text = section.text
    section_link_text = section.link or ""
    
    # Extract a blurb from the section text
    blurb = extract_blurb(section_text, blurb_size)

    # Create a SentenceSplitter object with the tokenizer function, chunk size and overlap
    sentence_aware_splitter = SentenceSplitter(
        tokenizer=tokenizer.tokenize, chunk_size=chunk_size, chunk_overlap=chunk_overlap
    )

    # Split the section text into chunks
    split_texts = sentence_aware_splitter.split_text(section_text)

    # Create a list of DocAwareChunk objects from the split texts
    chunks = [
        DocAwareChunk(
            source_document=document,
            chunk_id=start_chunk_id + chunk_ind,
            blurb=blurb,
            content=chunk_str,
            source_links={0: section_link_text},
            section_continuation=(chunk_ind != 0),
        )
        for chunk_ind, chunk_str in enumerate(split_texts)
    ]
    return chunks


def chunk_document(
    document: Document,
    chunk_tok_size: int = CHUNK_SIZE,
    subsection_overlap: int = CHUNK_OVERLAP,
    blurb_size: int = BLURB_SIZE,
) -> list[DocAwareChunk]:
    tokenizer = get_default_tokenizer()

    chunks: list[DocAwareChunk] = []
    link_offsets: dict[int, str] = {}
    chunk_text = ""
    for section in document.sections:
        section_link_text = section.link or ""
        section_tok_length = len(tokenizer.tokenize(section.text))
        current_tok_length = len(tokenizer.tokenize(chunk_text))
        curr_offset_len = len(shared_precompare_cleanup(chunk_text))

        # Large sections are considered self-contained/unique therefore they start a new chunk and are not concatenated
        # at the end by other sections
        if section_tok_length > chunk_tok_size:
            if chunk_text:
                chunks.append(
                    DocAwareChunk(
                        source_document=document,
                        chunk_id=len(chunks),
                        blurb=extract_blurb(chunk_text, blurb_size),
                        content=chunk_text,
                        source_links=link_offsets,
                        section_continuation=False,
                    )
                )
                link_offsets = {}
                chunk_text = ""

            large_section_chunks = chunk_large_section(
                section=section,
                document=document,
                start_chunk_id=len(chunks),
                tokenizer=tokenizer,
                chunk_size=chunk_tok_size,
                chunk_overlap=subsection_overlap,
                blurb_size=blurb_size,
            )
            chunks.extend(large_section_chunks)
            continue

        # In the case where the whole section is shorter than a chunk, either adding to chunk or start a new one
        if (
            current_tok_length
            + len(tokenizer.tokenize(SECTION_SEPARATOR))
            + section_tok_length
            <= chunk_tok_size
        ):
            chunk_text += (
                SECTION_SEPARATOR + section.text if chunk_text else section.text
            )
            link_offsets[curr_offset_len] = section_link_text
        else:
            chunks.append(
                DocAwareChunk(
                    source_document=document,
                    chunk_id=len(chunks),
                    blurb=extract_blurb(chunk_text, blurb_size),
                    content=chunk_text,
                    source_links=link_offsets,
                    section_continuation=False,
                )
            )
            link_offsets = {0: section_link_text}
            chunk_text = section.text

    # Once we hit the end, if we're still in the process of building a chunk, add what we have
    if chunk_text:
        chunks.append(
            DocAwareChunk(
                source_document=document,
                chunk_id=len(chunks),
                blurb=extract_blurb(chunk_text, blurb_size),
                content=chunk_text,
                source_links=link_offsets,
                section_continuation=False,
            )
        )
    return chunks


def split_chunk_text_into_mini_chunks(
    chunk_text: str, mini_chunk_size: int = MINI_CHUNK_SIZE
) -> list[str]:
    token_count_func = get_default_tokenizer().tokenize
    sentence_aware_splitter = SentenceSplitter(
        tokenizer=token_count_func, chunk_size=mini_chunk_size, chunk_overlap=0
    )

    return sentence_aware_splitter.split_text(chunk_text)


class Chunker:
    @abc.abstractmethod
    def chunk(self, document: Document) -> list[DocAwareChunk]:
        raise NotImplementedError


class DefaultChunker(Chunker):
    def chunk(self, document: Document) -> list[DocAwareChunk]:
        return chunk_document(document)
