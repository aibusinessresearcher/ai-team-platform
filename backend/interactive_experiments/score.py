from typing import List, Dict

def score_ranking(items: List[str], ground_truth: List[int], ranking_dict: Dict[str, int]) -> float:
        """Score a ranking solution using L1 distance from ground truth ranking.

        Args:
            ranking_dict: parsed ranking, a dict of item name to rank

        Returns:
            L1 distance from ground truth ranking (lower is better)
        """
        try:
            l1_distance = 0.0
            for i, item in enumerate(items):
                model_rank = ranking_dict[item]
                expert_rank = ground_truth[i]
                l1_distance += abs(model_rank - expert_rank)
            return float(l1_distance)

        except Exception as e:
            print(f"Error parsing ranking: {e}")
            # Return worst possible score (complete reversal of ranking)
            # For n items, worst case L1 distance is sum(|n - 2i - 1|) for i=0 to n-1
            # For odd n: (n-1)*(n+1)/2, for even n: n*n/2
            num_items = len(items)
            if num_items % 2 == 0:
                worst_score = num_items * num_items / 2
            else:
                worst_score = (num_items - 1) * (num_items + 1) / 2
            return float(worst_score)


def score_multiple_choice():
    pass

def score_short_answer():
    pass

def score_math():
    pass

    