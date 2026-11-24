"""Track 2a: synthesis side of the hand-written RAG layer.

Called from app.py's /api/ask route — not run standalone. The caller owns
the anthropic.Anthropic() client (built once from ANTHROPIC_API_KEY) and
passes it in, same pattern as tagger.py's tag_posts().
"""

import anthropic

from ai_rag import bq_retrieval_query

MODEL = "claude-opus-5"

SYSTEM_PROMPT = """You are an AI assistant designed to answer user questions accurately based on retrieved posts and web search.

Follow these operational guidelines:
1. Primary Source: Base your response primarily on the provided retrieved posts.
2. Web Search Fallback: If the retrieved posts do not contain sufficient or clear information to answer the question, use the web search tool to find accurate, up-to-date information. Do not hallucinate or guess.
3. Grounding & Truthfulness: Synthesize facts strictly from verified context (the posts or search results). If neither provides enough detail, clearly state what cannot be answered.
4. Attribution: At the end of your response, include an "Sources & Inspiration" section listing the specific posts, authors, or web sources that informed your answer."""


def ui_answer_response(client: anthropic.Anthropic, ui_user_query: str) -> list:
    retrieved_posts = bq_retrieval_query.vector_search_call(ui_user_query)

    response = client.messages.create(
        model=MODEL,
        max_tokens=2000,
        system=SYSTEM_PROMPT,
        # medium effort: this is a chat-style Q&A workload, not long-horizon
        # agentic work — the default (high) was adding real latency for
        # thinking depth this task doesn't need.
        output_config={"effort": "medium"},
        messages=[{
            "role": "user",
            "content": f"User Query: {ui_user_query}; User Content: {retrieved_posts}"
        }],
        tools=[{
            "type": "web_search_20260209",
            "name": "web_search",
            "max_uses": 3,
        }]
    )

    if response.stop_reason == "refusal":
        return [{"type": "error", "error": "The model declined to answer this question."}]

    # A turn that uses web search comes back as several interleaved blocks —
    # text, then a search call, then more text continuing the same answer.
    # Collect everything first and merge into one answer + one source list,
    # rather than rendering each block as its own separate bubble in the UI.
    text_parts = []
    sources = []
    seen_urls = set()
    errors = []

    for block in response.content:
        if block.type == "text":
            text_parts.append(block.text)
        elif block.type == "web_search_tool_result":
            if isinstance(block.content, list):
                for r in block.content:
                    if r.url not in seen_urls:
                        seen_urls.add(r.url)
                        sources.append({"url": r.url, "title": r.title})
            else:
                # Error case: content is a single object (e.g. {error_code: "..."}),
                # not the list of results a success returns.
                errors.append(getattr(block.content, "error_code", str(block.content)))

    results = []
    if text_parts:
        results.append({"type": "text", "text": "\n\n".join(text_parts)})
    if sources:
        results.append({"type": "sources", "sources": sources})
    for e in errors:
        results.append({"type": "error", "error": e})

    return results
