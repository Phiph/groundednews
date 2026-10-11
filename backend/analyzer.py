import json
import anthropic
from config import ANTHROPIC_API_KEY

client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)


def cluster_articles(articles: list[dict]) -> list[dict]:
    """
    Takes a list of article dicts with title/summary/source.
    Returns list of cluster dicts, each with a headline, summary, category,
    and list of article indices belonging to it.
    """
    if not articles:
        return []

    articles_text = "\n".join(
        f"{i}. [{a['source']}] {a['title']}"
        for i, a in enumerate(articles)
    )

    prompt = f"""You are a news editor. Below are {len(articles)} news article headlines from different sources.

Group them into clusters where each cluster represents the SAME news story covered by multiple outlets.
Only cluster articles that are clearly about the same specific event or story.
Articles about general topics or different angles of a broad issue should NOT be clustered together.
Single-source stories that don't match anything else should be their own cluster of 1.

For each cluster, provide:
- headline: A single neutral, factual headline that covers the story
- summary: 1-2 sentence neutral summary of what happened
- category: One of: Politics, World, Business, Tech, Science, Health, Sports, Entertainment, Environment
- indices: List of article numbers (0-based) in this cluster

Articles:
{articles_text}

Respond with ONLY valid JSON in this exact format:
{{
  "clusters": [
    {{
      "headline": "...",
      "summary": "...",
      "category": "...",
      "indices": [0, 3, 7]
    }}
  ]
}}"""

    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=4096,
        messages=[{"role": "user", "content": prompt}],
    )

    text = response.content[0].text.strip()
    # Strip markdown code fences if present
    if text.startswith("```"):
        text = text.split("```")[1]
        if text.startswith("json"):
            text = text[4:]
    text = text.strip()

    data = json.loads(text)
    return data.get("clusters", [])


def generate_cluster_headline(articles: list[dict]) -> dict:
    """For a single cluster of articles, generate a headline and summary."""
    titles = "\n".join(f"- [{a['source']}] {a['title']}" for a in articles)
    prompt = f"""Given these headlines about the same story from different news sources:
{titles}

Generate:
1. A single neutral, factual headline
2. A 1-2 sentence neutral summary
3. A category (Politics/World/Business/Tech/Science/Health/Sports/Entertainment/Environment)

Respond as JSON: {{"headline": "...", "summary": "...", "category": "..."}}"""

    response = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=256,
        messages=[{"role": "user", "content": prompt}],
    )
    text = response.content[0].text.strip()
    if text.startswith("```"):
        text = text.split("```")[1]
        if text.startswith("json"):
            text = text[4:]
    return json.loads(text.strip())
