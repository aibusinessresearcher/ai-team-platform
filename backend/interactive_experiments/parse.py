import re
from typing import List, Dict

def parse_ranking(text: str, items: List[str]) -> Dict[str, int]:
    """Parse a ranking from text and return as dict of item name to rank.

    Returns 1-indexed ranks (1 = best, num_items = worst).

    Args:
        text: Text containing a numbered ranking of items

    Returns:
        Dictionary mapping item name to assigned rank (1-num_items)

    Raises:
        ValueError: If ranking is incomplete or invalid
    """
    ranking: Dict[str, int] = {}
    lines = text.split('\n')

    for line in lines:
        line = line.strip()
        if not line:
            continue

        # Match patterns like "1. Item name" or "1) Item name"
        match = re.match(r'^(\d+)[\.\)]\s*(.+)', line)
        if match:
            rank = int(match.group(1))
            item_text = match.group(2).strip()

            # Find best matching item - prioritize longer matches to avoid ambiguity
            matched_item = None
            best_match_score = 0

            for item in items:
                if item in ranking:
                    continue

                item_lower = item.lower()
                text_lower = item_text.lower()

                # Exact match gets highest priority
                if item_lower == text_lower:
                    matched_item = item
                    break

                # Check if agent's text is substring of ground truth item
                if text_lower in item_lower:
                    match_score = len(text_lower)
                    if match_score > best_match_score:
                        best_match_score = match_score
                        matched_item = item

                # Check if ground truth item is substring of agent's text
                elif item_lower in text_lower:
                    match_score = len(item_lower)
                    if match_score > best_match_score:
                        best_match_score = match_score
                        matched_item = item

            if matched_item:
                if matched_item in ranking:
                    raise ValueError(f"Item '{matched_item}' appears multiple times in ranking")
                ranking[matched_item] = rank

    # Validate we got all items
    if len(ranking) != len(items):
        missing_items = [item for item in items if item not in ranking]
        print(f"Incomplete ranking - found {len(ranking)}/{len(items)} items")
        print(f"Missing items: {missing_items}")
        print(f"Parsed ranking: {ranking}")
        raise ValueError(f"Could not parse complete ranking (found {len(ranking)}/{len(items)} items)")

    return ranking    

def parse_multiple_choice():
    pass

def parse_short_answer(text: str) -> str:

    """Extract the answer from "My answer is X" format.
    
    Since we explicitly instruct agents to put their answer on one line with
    "My answer is X", we extract until the first newline. GPT-5 autorating
    will handle equivalence checking for variations (e.g., "Dr. Smith" vs "Dr Smith").
    
    Args:
        text: The text containing the answer
        
    Returns:
        Extracted answer string or empty string if not found
    """
    text = str(text).strip()
    
    # Look for "My answer is X" pattern (case-insensitive)
    # Extract everything after "My answer is" until newline or end of string
    pattern = r'my\s+answer\s+is\s*:?\s*(.+?)(?:\n|$)'
    match = re.search(pattern, text, re.IGNORECASE | re.DOTALL)
    if match:
        answer = match.group(1).strip()
        # Remove trailing punctuation (period, semicolon, colon)
        # GPT-5 autorating will handle equivalence for variations
        answer = answer.rstrip('.;:')
        if answer:
            return answer
    
    # Fallback: look for "answer is X" without "my"
    pattern_fallback = r'answer\s+is\s*:?\s*(.+?)(?:\n|$)'
    match = re.search(pattern_fallback, text, re.IGNORECASE | re.DOTALL)
    if match:
        answer = match.group(1).strip()
        answer = answer.rstrip('.;:')
        if answer:
            return answer
    
    # If no pattern found, return empty string
    return ""

def parse_math():
    pass

def parse_llm_response(response: str) -> str:

    # will need updating depending on task and error checking
    
    match = re.search(r"\[([^\]]*)\]", response)
    if match:
        return match.group(1).lower()