"""Track 2a: retrieval side of the hand-written RAG layer.

VECTOR_SEARCH against the materialized embedding table built by
bq_embedding.py, using an inline ML.GENERATE_EMBEDDING subquery so the
caller only ever has to pass plain question text — no separate embed step.
"""

import logging
import os
from typing import Any, Dict, List

from google.cloud import bigquery

from ai_rag.bq_embedding import EMBEDDING_TABLE_ID, GCP_PROJECT, BQ_DATASET

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

MODEL_ID = os.getenv("EMBEDDING_MODEL", "linkedinposts_text_embedding")


def _client() -> bigquery.Client:
    """Initializes and returns a single BigQuery client."""
    return bigquery.Client(project=GCP_PROJECT)


def vector_search_call(question: str, top_k: int = 5) -> List[Dict[str, Any]]:
    """Runs VECTOR_SEARCH directly against the materialized table using an inline embedding subquery."""
    client = _client()
    project = client.project or GCP_PROJECT
    full_model_path = f"`{project}.{BQ_DATASET}.{MODEL_ID}`"

    logger.info("Running vector search for query: '%s' (top_k=%d)", question, top_k)

    sql = f"""
    SELECT
        base.post_url,
        base.author_name,
        base.post_text,
        base.post_date,
        distance
    FROM VECTOR_SEARCH(
        TABLE `{EMBEDDING_TABLE_ID}`,
        'ml_generate_embedding_result',
        (
            SELECT ml_generate_embedding_result, content AS query
            FROM ML.GENERATE_EMBEDDING(
                MODEL {full_model_path},
                (SELECT @question AS content),
                STRUCT('RETRIEVAL_QUERY' AS task_type, TRUE AS flatten_json_output)
            )
        ),
        top_k => @top_k,
        distance_type => 'COSINE',
        options => '{{"fraction_lists_to_search": 0.05}}'
    )
    ORDER BY distance ASC;
    """

    # "options" has no effect until there's a proper vector index

    job_config = bigquery.QueryJobConfig(
        query_parameters=[
            bigquery.ScalarQueryParameter("question", "STRING", question),
            bigquery.ScalarQueryParameter("top_k", "INT64", top_k),
        ]
    )

    query_job = client.query(sql, job_config=job_config)
    results = [dict(row) for row in query_job.result()]

    logger.info("Retrieved %d matching posts.", len(results))
    return results
