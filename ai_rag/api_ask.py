"""Synthesis side of the hand-written RAG layer ("Ask Archive").

Called from app.py's /api/ask route — not run standalone. The caller owns
the anthropic.Anthropic() client (built once from ANTHROPIC_API_KEY) and
passes it in, same pattern as tagger.py's tag_posts().

stream_answer() is a generator of small dict events that app.py forwards to
the browser as Server-Sent Events, so the answer appears token-by-token
instead of after one long blocking wait. It's multi-turn: the browser keeps
the conversation history and sends it back with each question (the server
stays stateless, which matters on Cloud Run where consecutive requests can
land on different instances).
"""

import re
from typing import Any, Dict, Iterator, List

import anthropic

from ai_rag import bq_retrieval_query

# Measured side-by-side on 2026-11-25 (same questions, medium effort):
# Opus 5.5 was ~40% faster on archive questions and ~30% cheaper per answer
# than claude-opus-5, at equal or better quality.
MODEL = "claude-opus-5-5"
WEB_SEARCH_MAX_USES = 3
# Deliberately the basic web search tool, not the newer web_search_20260209.
# With the newer one (search runs inside a hidden code-execution filtering
# step), Opus 5.5 repeatedly used every search it was allowed, then reported
# it "could only run one search" and answered from stale memory, in 3 of 4
# test runs, even with max_uses raised to 5. With this basic tool it gave
# correct, current, well-sourced answers in ~20s in both runs (vs ~30s).
# Re-test before changing it.
WEB_SEARCH_TOOL = "web_search_20250305"

SYSTEM_PROMPT = """You are an AI assistant in an ongoing conversation with the user about their personal archive of saved LinkedIn posts.

Follow these operational guidelines:
1. Primary Source: Base your response primarily on the retrieved posts provided with the latest message. Earlier turns in the conversation are context for follow-up questions.
2. Web Search Fallback: If the retrieved posts do not contain sufficient or clear information to answer the question, use the web search tool to find accurate, up-to-date information. Do not hallucinate or guess.
3. Grounding & Truthfulness: Synthesize facts strictly from verified context (the posts, search results, or earlier turns). If none provides enough detail, clearly state what cannot be answered.
4. Attribution: At the end of your response, include a "Sources & Inspiration" section listing the specific posts (author + link), or web sources that informed your answer. For a short conversational follow-up that adds no new facts, you may skip it."""

# Upper bounds on what the browser can send back as history — keeps one
# runaway conversation from turning into an arbitrarily large (and
# arbitrarily expensive) request.
MAX_HISTORY_MESSAGES = 20
MAX_MESSAGE_CHARS = 20000


def clean_history(raw: Any) -> List[Dict[str, str]]:
    """Validate the client-supplied history: alternating user/assistant
    plain-text turns, starting with user, trimmed to the most recent turns."""
    if not isinstance(raw, list):
        return []
    msgs = []
    for m in raw:
        if not isinstance(m, dict):
            continue
        role, content = m.get("role"), m.get("content")
        if role not in ("user", "assistant") or not isinstance(content, str) or not content.strip():
            continue
        if msgs and msgs[-1]["role"] == role:
            continue  # drop anything that breaks alternation
        msgs.append({"role": role, "content": content[:MAX_MESSAGE_CHARS]})
    # Must end on an assistant turn (the new question is the next user turn)
    if msgs and msgs[-1]["role"] == "user":
        msgs.pop()
    msgs = msgs[-MAX_HISTORY_MESSAGES:]
    if msgs and msgs[0]["role"] == "assistant":
        msgs = msgs[1:]
    return msgs


def _format_posts(posts: List[Dict[str, Any]]) -> str:
    if not posts:
        return "(no matching posts found in the archive)"
    lines = []
    for i, p in enumerate(posts, 1):
        lines.append(
            f"[{i}] {p.get('author_name') or 'Unknown author'} "
            f"({p.get('post_date') or 'date unknown'}) — {p.get('post_url')}\n"
            f"{p.get('post_text') or ''}"
        )
    return "\n\n".join(lines)


_SENTENCE_END = re.compile(r"([.!?:]|\*\*)$")


def _block_separator(prev: str, nxt: str) -> str:
    """What to put between two consecutive text blocks of one answer.

    A turn's answer arrives as many text blocks (split around thinking, web
    searches, and sometimes mid-sentence). Usually each block carries its own
    whitespace and they concatenate cleanly — but sometimes a boundary falls
    exactly where a space or paragraph break should be, e.g. a `**Heading**`
    block followed directly by `Body text...`. Only intervene when the two
    would otherwise glue together.
    """
    if not prev or prev[-1].isspace() or nxt[0].isspace():
        return ""
    if nxt[0] in ",.;:!?)]}…'\"’”—–":
        return ""  # continuing the same sentence
    if _SENTENCE_END.search(prev) and (nxt[0].isupper() or nxt[0] in "#*-[0123456789"):
        return "\n\n"  # new sentence/section after a heading or full stop
    return " "


def stream_answer(
    client: anthropic.Anthropic, question: str, history: List[Dict[str, str]]
) -> Iterator[Dict[str, Any]]:
    """Yield events: {"type": "status"|"delta"|"sources"|"error", ...}."""
    yield {"type": "status", "text": "Searching your archive…"}

    # Follow-ups like "tell me more about the second one" embed poorly on
    # their own, so retrieve on the previous question + this one.
    prev_questions = [m["content"] for m in history if m["role"] == "user"]
    retrieval_query = f"{prev_questions[-1]}\n{question}" if prev_questions else question
    posts = bq_retrieval_query.vector_search_call(retrieval_query)

    messages: List[Dict[str, Any]] = list(history) + [{
        "role": "user",
        "content": (
            f"<retrieved_posts>\n{_format_posts(posts)}\n</retrieved_posts>\n\n"
            f"Question: {question}"
        ),
    }]

    yield {"type": "status", "text": "Writing answer…"}

    emitted_text = ""
    new_block = False
    final = None
    all_blocks: List[Any] = []  # every block across pause_turn continuations

    # The server-side web search loop can return stop_reason "pause_turn"
    # when it needs more iterations — re-send to let it continue (bounded).
    for _ in range(3):
        with client.beta.messages.stream(
            model=MODEL,
            max_tokens=16000,
            system=SYSTEM_PROMPT,
            # medium effort: chat-style Q&A, not long-horizon agentic work.
            output_config={"effort": "medium"},
            # On a safety-classifier decline, re-run on a fallback model
            # inside the same call instead of just stopping.
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",
            messages=messages,
            tools=[{
                "type": WEB_SEARCH_TOOL,
                "name": "web_search",
                "max_uses": WEB_SEARCH_MAX_USES,
            }],
        ) as stream:
            for event in stream:
                if event.type == "content_block_start":
                    btype = event.content_block.type
                    if btype == "server_tool_use":
                        yield {"type": "status", "text": "Searching the web…"}
                    elif btype == "text":
                        new_block = True
                elif event.type == "text" and event.text:
                    if new_block:
                        sep = _block_separator(emitted_text, event.text)
                        if sep:
                            emitted_text += sep
                            yield {"type": "delta", "text": sep}
                        new_block = False
                    emitted_text += event.text
                    yield {"type": "delta", "text": event.text}
            final = stream.get_final_message()
        all_blocks.extend(final.content)

        if final.stop_reason != "pause_turn":
            break
        messages = messages + [{"role": "assistant", "content": final.content}]

    if final is not None and final.stop_reason == "refusal":
        yield {"type": "error", "error": "The model declined to answer this question."}
        return

    # Sources come from the completed message(s) — web search result blocks
    # arrive whole, so there's nothing to gain by streaming them.
    sources, seen = [], set()
    for block in all_blocks:
        if block.type == "web_search_tool_result":
            if isinstance(block.content, list):
                for r in block.content:
                    if r.url not in seen:
                        seen.add(r.url)
                        sources.append({"url": r.url, "title": r.title})
            else:
                # Error case: content is a single error object, not a list.
                yield {"type": "error",
                       "error": f"Web search failed: {getattr(block.content, 'error_code', block.content)}"}
    if sources:
        yield {"type": "sources", "sources": sources}
