from dataclasses import dataclass

from src.collectors.aliexpress import AliExpressProduct
from src.collectors.tiktok import TikTokProduct

STOP_WORDS = {
    "the", "a", "an", "and", "or", "but", "in", "on", "at", "to", "for",
    "of", "with", "by", "from", "is", "it", "this", "that", "are", "was",
    "be", "has", "had", "not", "no", "you", "your", "we", "our", "new",
}

JACCARD_THRESHOLD = 0.3


@dataclass
class Match:
    tiktok_product: TikTokProduct
    ali_product: AliExpressProduct
    similarity: float


def tokenize(text: str) -> set[str]:
    """Tokenize text into lowercase words, removing stop words."""
    words = set(text.lower().split())
    return words - STOP_WORDS


def calculate_jaccard_similarity(set_a: set[str], set_b: set[str]) -> float:
    """Calculate Jaccard similarity between two sets."""
    if not set_a or not set_b:
        return 0.0
    intersection = set_a & set_b
    union = set_a | set_b
    return len(intersection) / len(union)


def find_best_match(
    tiktok_product: TikTokProduct,
    ali_products: list[AliExpressProduct],
) -> Match | None:
    """Find the best AliExpress match for a TikTok product by keyword similarity."""
    tiktok_tokens = tokenize(tiktok_product.title)

    best_match: Match | None = None
    best_similarity = 0.0

    for ali_product in ali_products:
        ali_tokens = tokenize(ali_product.title)
        similarity = calculate_jaccard_similarity(tiktok_tokens, ali_tokens)

        if similarity > best_similarity:
            best_similarity = similarity
            best_match = Match(
                tiktok_product=tiktok_product,
                ali_product=ali_product,
                similarity=similarity,
            )

    if best_match and best_match.similarity >= JACCARD_THRESHOLD:
        return best_match

    return None
