"""
GameForge LLM Decomposition Layer
===================================
Takes extracted JSON from the GameForge Extractor (Layer 1) and feeds
text blocks to Claude's API for structured rule decomposition.

Outputs a normalized game rules database in JSON — procedures, rules,
references, and their relationships.

Usage:
    python gameforge_decompose.py extracted.json --output rules.json
    python gameforge_decompose.py extracted.json --batch-size 10 --verbose
    python gameforge_decompose.py extracted.json --stats-only

Requires:
    pip install anthropic
    
    Set your API key:
    export ANTHROPIC_API_KEY=sk-ant-...
    (or set it in a .env file)
"""

import argparse
import json
import os
import sys
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Optional

try:
    import anthropic
except ImportError:
    print("Error: anthropic package not installed.")
    print("Run: pip install anthropic")
    sys.exit(1)


# =============================================================================
# SCHEMA — what we're decomposing INTO
# =============================================================================

RULE_SCHEMA = {
    "id": "string — unique identifier (e.g., 'fof_combat_013')",
    "game": "string — game name (e.g., 'Fields of Fire')",
    "type": "string — one of: 'procedure', 'rule', 'reference', 'definition'",
    "category": "string — high-level category (e.g., 'combat', 'movement', 'supply', 'command', 'setup', 'terrain', 'morale')",
    "title": "string — short descriptive title",
    "section_number": "string or null — original rulebook section number (e.g., '6.2.1')",
    "phase": "string or null — game phase this applies to (e.g., 'command', 'combat', 'logistics')",
    "summary": "string — one-sentence summary of what this rule does",
    "full_text": "string — the complete rule text, cleaned up",
    "steps": "list of strings or null — ordered steps if this is a procedure",
    "conditions": "list of strings or null — when does this rule apply",
    "modifiers": "list of objects or null — any numerical modifiers, DRMs, etc.",
    "references": {
        "tables": "list of strings — table names this rule uses",
        "related_rules": "list of strings — IDs of related rules",
        "page": "integer — source page number"
    },
    "tags": "list of strings — searchable tags"
}


# =============================================================================
# DECOMPOSITION PROMPT
# =============================================================================

SYSTEM_PROMPT = """You are a game rules analyst. Your job is to decompose rulebook text into structured, machine-readable rule entries.

You will receive blocks of text extracted from a tabletop game rulebook. For each meaningful rule, procedure, definition, or reference table you identify, output a structured JSON entry.

CLASSIFICATION TYPES:
- "procedure": A multi-step sequence players must follow (e.g., "Fire Resolution Sequence")
- "rule": A single directive or constraint (e.g., "Units in cover apply a -1 DRM")
- "reference": A table, chart, or modifier list (e.g., "Terrain Effects Chart")
- "definition": A game term and its meaning (e.g., "Engaged: A unit projecting a VOF")

RULES FOR DECOMPOSITION:
1. Each discrete rule gets its own entry — don't lump unrelated rules together
2. Preserve the original section numbers (1.2, 3.4.1, etc.)
3. Extract ALL cross-references (section numbers, page numbers, table names)
4. Identify conditional logic ("if X then Y", "when X, apply Y")
5. Pull out any numerical modifiers, DRMs, die roll requirements
6. Tag each entry with relevant searchable terms
7. If a block contains multiple rules, split them into separate entries
8. If a block is just flavor text, a page header, copyright, or table of contents entry (lines with dots/periods leading to page numbers) — skip it and return empty array
9. IMPORTANT: Blocks may be labeled as "body" type even when they contain section headings like "1.2 Components" or "3.4.1 Fire Resolution". Classify based on the actual TEXT content, not the block type label.
10. Table of contents entries with dotted leaders (....) are NOT rules — skip them.

OUTPUT FORMAT:
Return a JSON array of rule objects. Each object must have these fields:
{
    "type": "procedure|rule|reference|definition",
    "category": "combat|movement|supply|command|setup|terrain|morale|general|victory|units|los|cards",
    "title": "short title",
    "section_number": "1.2.3 or null",
    "phase": "game phase or null",
    "summary": "one sentence",
    "full_text": "complete rule text",
    "steps": ["step 1", "step 2"] or null,
    "conditions": ["condition 1"] or null,
    "modifiers": [{"name": "cover", "value": -1, "applies_to": "fire resolution"}] or null,
    "table_references": ["table name"],
    "rule_references": ["1.2", "3.4.1"],
    "page": page_number,
    "tags": ["tag1", "tag2"]
}

Return ONLY the JSON array, no other text. If the input has no meaningful rules, return [].
"""


def build_block_prompt(blocks: list[dict], game_name: str) -> str:
    """Build the user prompt from a batch of extracted blocks."""
    block_text = []
    for b in blocks:
        header = f"[Page {b['page']} | Type: {b['blockType']}]"
        if b.get('section'):
            header += f" [Section: {b['section']}]"
        block_text.append(f"{header}\n{b['text']}")

    joined = "\n\n---\n\n".join(block_text)

    return f"""Game: {game_name}

Decompose the following rulebook blocks into structured rule entries:

{joined}

Return a JSON array of rule objects. If a block is just a page header, copyright, or flavor text with no game rules, skip it."""


# =============================================================================
# API CLIENT
# =============================================================================

class DecompositionEngine:
    """Manages Claude API calls for rule decomposition."""

    def __init__(self, api_key: str = None, model: str = "claude-sonnet-4-20250514"):
        self.api_key = api_key or os.environ.get("ANTHROPIC_API_KEY")
        if not self.api_key:
            raise ValueError(
                "No API key found. Set ANTHROPIC_API_KEY environment variable "
                "or pass api_key parameter."
            )
        self.client = anthropic.Anthropic(api_key=self.api_key)
        self.model = model
        self.total_input_tokens = 0
        self.total_output_tokens = 0
        self.total_calls = 0

    def decompose_batch(self, blocks: list[dict], game_name: str, retries: int = 2) -> list[dict]:
        """Send a batch of blocks to Claude for decomposition."""
        prompt = build_block_prompt(blocks, game_name)

        for attempt in range(retries + 1):
            try:
                response = self.client.messages.create(
                    model=self.model,
                    max_tokens=4096,
                    system=SYSTEM_PROMPT,
                    messages=[{"role": "user", "content": prompt}]
                )

                self.total_input_tokens += response.usage.input_tokens
                self.total_output_tokens += response.usage.output_tokens
                self.total_calls += 1

                # Parse the response
                text = response.content[0].text.strip()

                # Strip markdown code fences if present
                if text.startswith("```"):
                    text = text.split("\n", 1)[1] if "\n" in text else text[3:]
                if text.endswith("```"):
                    text = text[:-3].strip()
                if text.startswith("json"):
                    text = text[4:].strip()

                rules = json.loads(text)
                if not isinstance(rules, list):
                    rules = [rules]

                return rules

            except json.JSONDecodeError as e:
                if attempt < retries:
                    time.sleep(1)
                    continue
                print(f"  Warning: Failed to parse JSON response after {retries + 1} attempts: {e}")
                return []

            except anthropic.RateLimitError:
                wait = 2 ** (attempt + 1)
                print(f"  Rate limited, waiting {wait}s...")
                time.sleep(wait)

            except anthropic.APIError as e:
                if attempt < retries:
                    time.sleep(2)
                    continue
                print(f"  API error: {e}")
                return []

        return []

    def get_usage_stats(self) -> dict:
        return {
            "total_api_calls": self.total_calls,
            "total_input_tokens": self.total_input_tokens,
            "total_output_tokens": self.total_output_tokens,
            "estimated_cost_usd": round(
                (self.total_input_tokens * 3 / 1_000_000) +
                (self.total_output_tokens * 15 / 1_000_000), 4
            )
        }


# =============================================================================
# PIPELINE
# =============================================================================

def load_extraction(path: str) -> dict:
    """Load the JSON output from GameForge Extractor."""
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)


def get_all_blocks(extraction: dict, skip_pages: int = 0) -> list[dict]:
    """Flatten all text blocks from an extraction, skipping empty/trivial ones."""
    blocks = []
    for page in extraction.get("pages", []):
        page_num = page.get("pageNumber", page.get("page_number", 0))
        if page_num <= skip_pages:
            continue
        for block in page.get("blocks", page.get("text_blocks", [])):
            text = block.get("text", "").strip()
            if len(text) < 10:
                continue
            if "©" in text or "copyright" in text.lower():
                continue
            if "GMTGames" in text or "GMT Games" in text:
                continue
            if text.startswith("Fields of Fire") and "Edition" in text:
                continue
            # Skip TOC entries (lines full of dots)
            if text.count('.') > 20:
                continue
            blocks.append(block)
    return blocks


def batch_blocks(blocks: list[dict], batch_size: int = 8) -> list[list[dict]]:
    """
    Group blocks into batches for API calls.
    Tries to keep related blocks together (same section).
    """
    batches = []
    current_batch = []
    current_section = None

    for block in blocks:
        section = block.get("section") or block.get("detected_section")

        # If section changed and batch is getting full, flush
        if (section != current_section
                and len(current_batch) >= batch_size // 2
                and current_batch):
            batches.append(current_batch)
            current_batch = []

        current_batch.append(block)
        current_section = section

        if len(current_batch) >= batch_size:
            batches.append(current_batch)
            current_batch = []

    if current_batch:
        batches.append(current_batch)

    return batches


def assign_ids(rules: list[dict], game_prefix: str) -> list[dict]:
    """Assign unique IDs to decomposed rules."""
    counters = {}
    for rule in rules:
        category = rule.get("category", "general")
        counters[category] = counters.get(category, 0) + 1
        rule["id"] = f"{game_prefix}_{category}_{counters[category]:03d}"
    return rules


def run_decomposition(
    extraction_path: str,
    output_path: str = None,
    game_name: str = None,
    game_prefix: str = None,
    batch_size: int = 8,
    max_batches: int = None,
    skip_pages: int = 0,
    verbose: bool = False,
    stats_only: bool = False,
) -> dict:
    """
    Full decomposition pipeline.
    """
    # Load extraction
    extraction = load_extraction(extraction_path)
    source_file = extraction.get("sourceFile", extraction.get("source_file", "unknown"))

    if not game_name:
        game_name = source_file.replace("_", " ").replace(".pdf", "").replace(".json", "")

    if not game_prefix:
        # Generate prefix from game name: "Fields of Fire" -> "fof"
        words = game_name.lower().split()
        game_prefix = "".join(w[0] for w in words if w not in ("of", "the", "a", "an"))[:5]

    print(f"GameForge Decomposition Engine")
    print(f"{'=' * 50}")
    print(f"Source:     {source_file}")
    print(f"Game:       {game_name}")
    print(f"Prefix:     {game_prefix}")

    # Get blocks
    all_blocks = get_all_blocks(extraction, skip_pages=skip_pages)
    print(f"Blocks:     {len(all_blocks)} (after filtering)")

    # Batch them
    batches = batch_blocks(all_blocks, batch_size)
    if max_batches:
        batches = batches[:max_batches]
    print(f"Batches:    {len(batches)} (size ~{batch_size})")

    if stats_only:
        print(f"\nStats-only mode — no API calls made.")
        est_tokens = sum(len(b.get("text", "")) for b in all_blocks) // 4
        est_calls = len(batches)
        print(f"Estimated input tokens: ~{est_tokens:,}")
        print(f"Estimated API calls:    {est_calls}")
        print(f"Estimated cost:         ~${est_tokens * 3 / 1_000_000:.2f} input + output")
        return {}

    # Initialize engine
    engine = DecompositionEngine()
    all_rules = []

    print(f"\nDecomposing...")
    for i, batch in enumerate(batches):
        if verbose:
            pages = sorted(set(b["page"] for b in batch))
            print(f"  Batch {i + 1}/{len(batches)} — {len(batch)} blocks (pages {pages[0]}-{pages[-1]})")
        else:
            print(f"  [{i + 1}/{len(batches)}]", end='\r')

        rules = engine.decompose_batch(batch, game_name)
        all_rules.extend(rules)

        # Brief pause to respect rate limits
        if i < len(batches) - 1:
            time.sleep(0.5)

    print()

    # Assign IDs
    all_rules = assign_ids(all_rules, game_prefix)

    # Build cross-reference index
    section_to_id = {}
    for rule in all_rules:
        sec = rule.get("section_number")
        if sec:
            section_to_id[sec] = rule["id"]

    # Resolve references
    for rule in all_rules:
        resolved = []
        for ref in (rule.get("rule_references") or []):
            if ref in section_to_id:
                resolved.append(section_to_id[ref])
            else:
                resolved.append(ref)
        rule["resolved_references"] = resolved
        # Null-safe all list fields
        for key in ["steps", "conditions", "modifiers", "table_references", "rule_references", "tags"]:
            if rule.get(key) is None:
                rule[key] = []

    # Stats
    usage = engine.get_usage_stats()
    type_counts = {}
    category_counts = {}
    for rule in all_rules:
        t = rule.get("type", "unknown")
        c = rule.get("category", "unknown")
        type_counts[t] = type_counts.get(t, 0) + 1
        category_counts[c] = category_counts.get(c, 0) + 1

    result = {
        "game": game_name,
        "source_file": source_file,
        "total_rules": len(all_rules),
        "stats": {
            "by_type": type_counts,
            "by_category": category_counts,
            "api_usage": usage,
        },
        "rules": all_rules,
    }

    print(f"Decomposition Complete:")
    print(f"  Total rules extracted: {len(all_rules)}")
    print(f"\n  By type:")
    for t, c in sorted(type_counts.items(), key=lambda x: -x[1]):
        print(f"    {t:15s} {c}")
    print(f"\n  By category:")
    for cat, c in sorted(category_counts.items(), key=lambda x: -x[1]):
        print(f"    {cat:15s} {c}")
    print(f"\n  API usage:")
    print(f"    Calls:        {usage['total_api_calls']}")
    print(f"    Input tokens:  {usage['total_input_tokens']:,}")
    print(f"    Output tokens: {usage['total_output_tokens']:,}")
    print(f"    Est. cost:     ${usage['estimated_cost_usd']}")

    # Write output
    if output_path:
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(result, f, indent=2, ensure_ascii=False)
        print(f"\nOutput written to: {output_path}")

    return result


# =============================================================================
# CLI
# =============================================================================

def main():
    parser = argparse.ArgumentParser(
        description="GameForge LLM Decomposition — structured rule extraction via Claude API"
    )
    parser.add_argument("input", help="Path to extracted JSON from GameForge Extractor")
    parser.add_argument("--output", "-o", help="Output JSON path (default: <input>_decomposed.json)")
    parser.add_argument("--game-name", "-g", help="Game name (auto-detected from filename if omitted)")
    parser.add_argument("--game-prefix", help="ID prefix (auto-generated if omitted)")
    parser.add_argument("--batch-size", "-b", type=int, default=8, help="Blocks per API call (default: 8)")
    parser.add_argument("--max-batches", "-m", type=int, help="Limit number of API calls (for testing)")
    parser.add_argument("--skip-pages", "-s", type=int, default=0, help="Skip first N pages (TOC, intro)")
    parser.add_argument("--verbose", "-v", action="store_true", help="Print detailed progress")
    parser.add_argument("--stats-only", action="store_true", help="Estimate cost without making API calls")
    parser.add_argument("--model", default="claude-sonnet-4-20250514", help="Claude model to use")

    args = parser.parse_args()

    output_path = args.output or Path(args.input).stem + "_decomposed.json"

    run_decomposition(
        extraction_path=args.input,
        output_path=output_path,
        game_name=args.game_name,
        game_prefix=args.game_prefix,
        batch_size=args.batch_size,
        max_batches=args.max_batches,
        verbose=args.verbose,
        stats_only=args.stats_only,
        skip_pages=args.skip_pages,

    )


if __name__ == "__main__":
    main()
