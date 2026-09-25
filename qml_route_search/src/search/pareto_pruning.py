import numpy as np
from typing import List
from src.search.wavefront import WavefrontState

def dominates(a_obj: np.ndarray, b_obj: np.ndarray, epsilon: np.ndarray) -> bool:
    """
    Check if a_obj epsilon-dominates b_obj (assuming minimization).
    a_obj epsilon-dominates b_obj if a_obj <= b_obj + epsilon in all objectives,
    and a_obj < b_obj in at least one objective.
    This prevents the Curse of Dimensionality in 10D space.
    """
    return np.all(a_obj <= (b_obj + epsilon)) and np.any(a_obj < b_obj)

def pareto_prune(candidates: List[WavefrontState], confidence_caution_margin: float = 0.3) -> List[WavefrontState]:
    """
    Prunes a list of candidates by removing those that are Pareto dominated.
    Applies spatial binning to only compare candidates near each other.
    """
    if not candidates:
        return []

    # Epsilon bounds for the 9 dimensions to prevent frontier explosion:
    # [fuel, wave, wind, time, roll, slam, comfort, green_water, prop_emerge]
    epsilon = np.array([10.0, 1.0, 1.0, 0.1, 0.02, 10.0, 0.1, 0.05, 0.05])

    # Spatial binning (approx 300 NM resolution for massive trans-oceanic steps)
    binned_candidates = {}
    for cand in candidates:
        bin_key = (round(cand.lat / 5.0), round(cand.lon / 5.0))
        if bin_key not in binned_candidates:
            binned_candidates[bin_key] = []
        binned_candidates[bin_key].append(cand)

    pruned = []
    
    for bin_cands in binned_candidates.values():
        n = len(bin_cands)
        is_dominated = [False] * n
        
        # Prepare objectives (inflate risks if confidence is low)
        adjusted_objs = []
        for cand in bin_cands:
            obj = np.copy(cand.objectives)
            if cand.confidence_min < 0.5:
                # inflate risks in dimensions 4,5,6,7,8
                for k in range(4, 9):
                    obj[k] += confidence_caution_margin
            adjusted_objs.append(obj)
            
        # O(N^2) pairwise dominance check within bin
        for i in range(n):
            if is_dominated[i]:
                continue
            for j in range(n):
                if i == j or is_dominated[j]:
                    continue
                if dominates(adjusted_objs[i], adjusted_objs[j], epsilon):
                    is_dominated[j] = True
                    
        for i in range(n):
            if not is_dominated[i]:
                pruned.append(bin_cands[i])
                
    return pruned
