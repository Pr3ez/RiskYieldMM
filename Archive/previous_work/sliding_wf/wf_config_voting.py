"""
Config Voting System for Walk-Forward Backtest
===============================================

Weighted voting system where configs are assigned roles based on their strengths:
- GATEKEEPER: High TP, stable performance → can veto trades
- PRECISION: High precision → weighted voting for scaling
- DIRECTIONAL: Good at direction prediction → alignment signal
- GENERAL: All-around configs → ensemble participation

Each config earns authority through demonstrated performance.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple
import numpy as np


# ═══════════════════════════════════════════════════════════════════════════
# CONFIGURATION
# ═══════════════════════════════════════════════════════════════════════════

@dataclass
class VotingConfig:
    """Configuration for the voting system."""
    
    # Minimum requirements for role assignment
    min_samples_for_role: int = 30          # Need this many samples before role assignment
    
    # GATEKEEPER role thresholds
    gatekeeper_min_ratio: float = 1.30      # Need TP/FP >= 1.30 to be gatekeeper
    gatekeeper_min_tp: int = 15             # Need at least 15 TPs
    gatekeeper_min_stability: float = 0.6   # Consistency across windows >= 0.6
    gatekeeper_veto_threshold: float = 0.7  # If 70%+ gatekeepers predict DOWN → veto
    
    # PRECISION role thresholds  
    precision_min_precision: float = 0.58   # Need precision >= 58%
    precision_min_tp: int = 10              # Need at least 10 TPs
    
    # Weight calculation
    base_weight: float = 1.0                # Default weight for all configs
    precision_weight_mult: float = 1.5      # Multiplier for precision role
    gatekeeper_weight_mult: float = 2.0     # Multiplier for gatekeeper role
    tp_weight_scale: float = 0.1            # Additional weight per TP (scaled)
    
    # Voting thresholds
    min_configs_for_vote: int = 5           # Minimum configs to have valid vote
    strong_agreement_threshold: float = 0.8 # 80%+ agreement = strong signal
    weak_agreement_threshold: float = 0.5   # 50-60% = weak/uncertain


# ═══════════════════════════════════════════════════════════════════════════
# CONFIG ROLE
# ═══════════════════════════════════════════════════════════════════════════

@dataclass
class ConfigRole:
    """Represents a config's current role and authority."""
    name: str
    
    # Performance metrics
    tp: int = 0
    fp: int = 0
    precision: float = 0.0
    ratio: float = 0.0
    stability: float = 0.0
    consistency: float = 0.0
    momentum: str = 'STABLE'
    
    # Role flags
    is_gatekeeper: bool = False
    is_precision: bool = False
    is_directional: bool = False
    
    # Computed weight
    vote_weight: float = 1.0
    gate_weight: float = 0.0  # Only gatekeepers have gate weight
    
    def get_roles_str(self) -> str:
        """Get string representation of roles."""
        roles = []
        if self.is_gatekeeper:
            roles.append('GATE')
        if self.is_precision:
            roles.append('PREC')
        if self.is_directional:
            roles.append('DIR')
        return '+'.join(roles) if roles else 'GEN'


# ═══════════════════════════════════════════════════════════════════════════
# VOTING RESULT
# ═══════════════════════════════════════════════════════════════════════════

@dataclass
class VotingResult:
    """Result of a voting round."""
    
    # Weighted vote
    weighted_up_votes: float = 0.0
    weighted_down_votes: float = 0.0
    weighted_alignment: float = 0.5  # 0.0 = all DOWN, 1.0 = all UP
    
    # Gatekeeper vote
    gatekeeper_up_votes: float = 0.0
    gatekeeper_down_votes: float = 0.0
    gatekeeper_alignment: float = 0.5
    gatekeeper_veto: bool = False
    
    # Simple vote (for comparison)
    simple_up_count: int = 0
    simple_down_count: int = 0
    simple_alignment: float = 0.5
    
    # Participation
    n_configs_voted: int = 0
    n_gatekeepers: int = 0
    n_precision: int = 0
    
    # Recommended scaling factor
    scaling_factor: float = 1.0
    
    # Debug
    vote_details: List[Dict] = field(default_factory=list)


# ═══════════════════════════════════════════════════════════════════════════
# CONFIG VOTING SYSTEM
# ═══════════════════════════════════════════════════════════════════════════

class ConfigVotingSystem:
    """
    Weighted voting system for config-based decisions.
    
    Configs earn roles through performance:
    - GATEKEEPER: Can veto trades (high TP, stable)
    - PRECISION: Higher vote weight (accurate predictions)
    - DIRECTIONAL: Good at direction calls
    
    Usage:
        voting = ConfigVotingSystem()
        
        # Each iteration, update config stats from scorer
        roles = voting.update_roles(scorer, current_iter)
        
        # When making trade decision, get weighted vote
        result = voting.calculate_vote(config_predictions)
        
        # Use result for position sizing
        if result.gatekeeper_veto:
            position = 0.0
        else:
            position *= result.scaling_factor
    """
    
    def __init__(self, config: Optional[VotingConfig] = None):
        self.config = config or VotingConfig()
        self.roles: Dict[str, ConfigRole] = {}
        self.history: List[Dict] = []  # Track role changes over time
    
    def update_roles(
        self,
        config_stats: List[Dict],
        current_iter: int,
    ) -> Dict[str, ConfigRole]:
        """
        Update config roles based on current performance.
        
        Args:
            config_stats: List of dicts with config performance:
                - name: str
                - tp, fp: int
                - ratio: float
                - precision: float
                - stability: float (optional)
                - consistency: float (optional)
                - momentum: str (optional)
            current_iter: Current iteration number
            
        Returns:
            Dict mapping config name to ConfigRole
        """
        cfg = self.config
        
        for stat in config_stats:
            name = stat['name']
            tp = stat.get('tp', 0)
            fp = stat.get('fp', 0)
            samples = tp + fp
            
            # If not enough samples, still create role but without special powers
            if samples < cfg.min_samples_for_role:
                self.roles[name] = ConfigRole(
                    name=name, 
                    tp=tp, 
                    fp=fp,
                    precision=tp / samples if samples > 0 else 0,
                    ratio=tp / max(fp, 1),
                )
                continue
            
            precision = tp / samples if samples > 0 else 0.0
            ratio = tp / max(fp, 1)
            stability = stat.get('stability', 0.0)
            consistency = stat.get('consistency', 0.0)
            momentum = stat.get('momentum', 'STABLE')
            
            # Determine roles
            is_gatekeeper = (
                ratio >= cfg.gatekeeper_min_ratio and
                tp >= cfg.gatekeeper_min_tp and
                consistency >= cfg.gatekeeper_min_stability
            )
            
            is_precision = (
                precision >= cfg.precision_min_precision and
                tp >= cfg.precision_min_tp
            )
            
            # Directional: good ratio but maybe not enough for gatekeeper
            is_directional = ratio >= 1.1 and tp >= 8
            
            # Calculate vote weight
            vote_weight = cfg.base_weight
            
            if is_precision:
                vote_weight *= cfg.precision_weight_mult
            
            # Add TP-based bonus (diminishing returns via sqrt)
            tp_bonus = np.sqrt(tp) * cfg.tp_weight_scale
            vote_weight += tp_bonus
            
            # Momentum adjustment
            if momentum in ['DECLINING', 'WEAKENING']:
                vote_weight *= 0.8
            elif momentum in ['IMPROVING', 'STRENGTHENING']:
                vote_weight *= 1.1
            
            # Gate weight (only for gatekeepers)
            gate_weight = 0.0
            if is_gatekeeper:
                gate_weight = cfg.gatekeeper_weight_mult * (1 + np.sqrt(tp) * 0.1)
            
            # Store role
            self.roles[name] = ConfigRole(
                name=name,
                tp=tp,
                fp=fp,
                precision=precision,
                ratio=ratio,
                stability=stability,
                consistency=consistency,
                momentum=momentum,
                is_gatekeeper=is_gatekeeper,
                is_precision=is_precision,
                is_directional=is_directional,
                vote_weight=vote_weight,
                gate_weight=gate_weight,
            )
        
        return self.roles
    
    def calculate_vote(
        self,
        config_predictions: List[Dict],
        verbose: bool = False,
    ) -> VotingResult:
        """
        Calculate weighted vote from config predictions.
        
        Args:
            config_predictions: List of dicts with:
                - name: str (config name)
                - prob: float (predicted probability)
                - threshold: float (classification threshold)
            verbose: Print debug info
            
        Returns:
            VotingResult with weighted alignment and gatekeeper veto decision
        """
        cfg = self.config
        result = VotingResult()
        
        if len(config_predictions) < cfg.min_configs_for_vote:
            result.n_configs_voted = len(config_predictions)
            if verbose:
                print(f"  [VOTE] Insufficient configs: {len(config_predictions)} < {cfg.min_configs_for_vote}")
            return result
        
        # Process each config's vote
        weighted_up = 0.0
        weighted_down = 0.0
        gate_up = 0.0
        gate_down = 0.0
        simple_up = 0
        simple_down = 0
        
        vote_details = []
        
        for pred in config_predictions:
            name = pred.get('name', 'unknown')
            prob = pred.get('prob', 0.5)
            threshold = pred.get('threshold', 0.5)
            
            # Get role (or default)
            role = self.roles.get(name, ConfigRole(name=name))
            
            # Determine vote
            predicts_up = prob >= threshold
            
            # Simple vote
            if predicts_up:
                simple_up += 1
            else:
                simple_down += 1
            
            # Weighted vote
            weight = role.vote_weight
            if predicts_up:
                weighted_up += weight
            else:
                weighted_down += weight
            
            # Gatekeeper vote
            if role.is_gatekeeper:
                result.n_gatekeepers += 1
                if predicts_up:
                    gate_up += role.gate_weight
                else:
                    gate_down += role.gate_weight
            
            if role.is_precision:
                result.n_precision += 1
            
            vote_details.append({
                'name': name,
                'prob': prob,
                'threshold': threshold,
                'vote': 'UP' if predicts_up else 'DOWN',
                'roles': role.get_roles_str(),
                'weight': weight,
                'gate_weight': role.gate_weight,
            })
        
        # Calculate alignments
        total_weighted = weighted_up + weighted_down
        result.weighted_up_votes = weighted_up
        result.weighted_down_votes = weighted_down
        result.weighted_alignment = weighted_up / total_weighted if total_weighted > 0 else 0.5
        
        total_gate = gate_up + gate_down
        result.gatekeeper_up_votes = gate_up
        result.gatekeeper_down_votes = gate_down
        result.gatekeeper_alignment = gate_up / total_gate if total_gate > 0 else 0.5
        
        result.simple_up_count = simple_up
        result.simple_down_count = simple_down
        result.simple_alignment = simple_up / (simple_up + simple_down) if (simple_up + simple_down) > 0 else 0.5
        
        result.n_configs_voted = len(config_predictions)
        result.vote_details = vote_details
        
        # Determine gatekeeper veto
        # Veto if gatekeepers strongly disagree (predict DOWN)
        if result.n_gatekeepers >= 2:
            result.gatekeeper_veto = result.gatekeeper_alignment < (1.0 - cfg.gatekeeper_veto_threshold)
        
        # Calculate scaling factor based on weighted alignment
        if result.weighted_alignment >= cfg.strong_agreement_threshold:
            # Strong agreement: boost
            result.scaling_factor = 1.2 + (result.weighted_alignment - 0.8) * 0.5
        elif result.weighted_alignment >= 0.7:
            # Good agreement: normal
            result.scaling_factor = 1.0 + (result.weighted_alignment - 0.7) * 0.5
        elif result.weighted_alignment >= cfg.weak_agreement_threshold:
            # Weak agreement: reduce
            result.scaling_factor = 0.6 + (result.weighted_alignment - 0.5) * 1.0
        else:
            # Disagreement: strong reduction
            result.scaling_factor = 0.3 + result.weighted_alignment * 0.6
        
        if verbose:
            print(f"  [VOTE] Weighted: {result.weighted_alignment:.2f} "
                  f"(UP={weighted_up:.1f}, DOWN={weighted_down:.1f})")
            print(f"  [VOTE] Gatekeepers: {result.n_gatekeepers}, "
                  f"alignment={result.gatekeeper_alignment:.2f}, "
                  f"veto={result.gatekeeper_veto}")
            print(f"  [VOTE] Scaling: {result.scaling_factor:.2f}")
        
        return result
    
    def get_gatekeepers(self) -> List[ConfigRole]:
        """Get all current gatekeepers."""
        return [r for r in self.roles.values() if r.is_gatekeeper]
    
    def get_precision_configs(self) -> List[ConfigRole]:
        """Get all precision-role configs."""
        return [r for r in self.roles.values() if r.is_precision]
    
    def get_role_summary(self) -> Dict:
        """Get summary of current role assignments."""
        gatekeepers = self.get_gatekeepers()
        precision = self.get_precision_configs()
        
        return {
            'n_total': len(self.roles),
            'n_gatekeepers': len(gatekeepers),
            'n_precision': len(precision),
            'gatekeeper_names': [r.name for r in gatekeepers],
            'precision_names': [r.name for r in precision],
            'top_by_weight': sorted(
                self.roles.values(), 
                key=lambda r: r.vote_weight, 
                reverse=True
            )[:5],
        }
    
    def get_state(self) -> Dict:
        """Get serializable state for checkpointing."""
        return {
            'roles': {
                name: {
                    'name': r.name,
                    'tp': r.tp,
                    'fp': r.fp,
                    'precision': r.precision,
                    'ratio': r.ratio,
                    'stability': r.stability,
                    'consistency': r.consistency,
                    'momentum': r.momentum,
                    'is_gatekeeper': r.is_gatekeeper,
                    'is_precision': r.is_precision,
                    'is_directional': r.is_directional,
                    'vote_weight': r.vote_weight,
                    'gate_weight': r.gate_weight,
                }
                for name, r in self.roles.items()
            },
            'history': self.history,
        }
    
    def load_state(self, state: Dict) -> None:
        """Load state from checkpoint."""
        if not state:
            return
        
        self.history = state.get('history', [])
        
        roles_data = state.get('roles', {})
        self.roles = {}
        for name, data in roles_data.items():
            self.roles[name] = ConfigRole(
                name=data['name'],
                tp=data['tp'],
                fp=data['fp'],
                precision=data['precision'],
                ratio=data['ratio'],
                stability=data.get('stability', 0.0),
                consistency=data.get('consistency', 0.0),
                momentum=data.get('momentum', 'STABLE'),
                is_gatekeeper=data['is_gatekeeper'],
                is_precision=data['is_precision'],
                is_directional=data.get('is_directional', False),
                vote_weight=data['vote_weight'],
                gate_weight=data['gate_weight'],
            )


# ═══════════════════════════════════════════════════════════════════════════
# HELPER FUNCTIONS
# ═══════════════════════════════════════════════════════════════════════════

def build_config_stats_from_scorer(
    scorer,  # AdaptiveMultiPeriodScorerV3
    current_iter: int,
    window: int = 180,
) -> List[Dict]:
    """
    Build config stats list from AdaptiveMultiPeriodScorerV3.
    
    Args:
        scorer: The adaptive scorer instance
        current_iter: Current iteration
        window: Window for TP/FP calculation
        
    Returns:
        List of config stat dicts suitable for update_roles()
    """
    stats = []
    
    for cfg_name in scorer.config_histories:
        # Get TP/FP
        tp, fp = scorer.get_rolling_tp_fp(cfg_name, current_iter, window=window)
        samples = tp + fp
        
        if samples == 0:
            continue
        
        # Get dense window data for consistency
        dense_data = scorer.get_dense_window_scores(cfg_name, current_iter)
        consistency = dense_data.get('consistency', 0.0)
        
        # Get momentum
        momentum, signal = scorer.get_true_momentum(cfg_name, current_iter)
        
        stats.append({
            'name': cfg_name,
            'tp': tp,
            'fp': fp,
            'ratio': tp / max(fp, 1),
            'precision': tp / samples,
            'stability': dense_data.get('avg_score', 0.0),
            'consistency': consistency,
            'momentum': signal,
        })
    
    return stats


# ═══════════════════════════════════════════════════════════════════════════
# TESTING
# ═══════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    print("=" * 60)
    print("Config Voting System Test")
    print("=" * 60)
    
    # Create voting system
    voting = ConfigVotingSystem()
    
    # Simulate config stats
    config_stats = [
        # Strong gatekeeper: high TP, stable
        {'name': 'config_A', 'tp': 25, 'fp': 10, 'ratio': 2.5, 'precision': 0.71, 
         'consistency': 0.75, 'momentum': 'STABLE'},
        # Precision config: accurate but fewer samples
        {'name': 'config_B', 'tp': 15, 'fp': 8, 'ratio': 1.88, 'precision': 0.65,
         'consistency': 0.55, 'momentum': 'IMPROVING'},
        # Mediocre config
        {'name': 'config_C', 'tp': 12, 'fp': 10, 'ratio': 1.2, 'precision': 0.545,
         'consistency': 0.45, 'momentum': 'STABLE'},
        # Weak config
        {'name': 'config_D', 'tp': 8, 'fp': 12, 'ratio': 0.67, 'precision': 0.4,
         'consistency': 0.3, 'momentum': 'DECLINING'},
        # Another gatekeeper
        {'name': 'config_E', 'tp': 20, 'fp': 12, 'ratio': 1.67, 'precision': 0.625,
         'consistency': 0.65, 'momentum': 'STABLE'},
    ]
    
    # Update roles
    roles = voting.update_roles(config_stats, current_iter=100)
    
    print("\n📊 Role Assignments:")
    print("-" * 60)
    for name, role in roles.items():
        print(f"  {name}: {role.get_roles_str():>10}  "
              f"TP={role.tp:2d} FP={role.fp:2d} "
              f"ratio={role.ratio:.2f} prec={role.precision:.2f} "
              f"weight={role.vote_weight:.2f} gate={role.gate_weight:.2f}")
    
    # Simulate predictions
    print("\n🗳️ Voting Scenarios:")
    print("-" * 60)
    
    # Scenario 1: All predict UP
    preds_all_up = [
        {'name': 'config_A', 'prob': 0.60, 'threshold': 0.50},
        {'name': 'config_B', 'prob': 0.55, 'threshold': 0.50},
        {'name': 'config_C', 'prob': 0.52, 'threshold': 0.50},
        {'name': 'config_D', 'prob': 0.51, 'threshold': 0.50},
        {'name': 'config_E', 'prob': 0.58, 'threshold': 0.50},
    ]
    
    print("\nScenario 1: All predict UP")
    result1 = voting.calculate_vote(preds_all_up, verbose=True)
    print(f"  → Final: align={result1.weighted_alignment:.2f}, "
          f"scale={result1.scaling_factor:.2f}, veto={result1.gatekeeper_veto}")
    
    # Scenario 2: Gatekeepers predict DOWN
    preds_gate_down = [
        {'name': 'config_A', 'prob': 0.45, 'threshold': 0.50},  # Gate DOWN
        {'name': 'config_B', 'prob': 0.55, 'threshold': 0.50},  # UP
        {'name': 'config_C', 'prob': 0.52, 'threshold': 0.50},  # UP
        {'name': 'config_D', 'prob': 0.51, 'threshold': 0.50},  # UP
        {'name': 'config_E', 'prob': 0.48, 'threshold': 0.50},  # Gate DOWN
    ]
    
    print("\nScenario 2: Gatekeepers predict DOWN")
    result2 = voting.calculate_vote(preds_gate_down, verbose=True)
    print(f"  → Final: align={result2.weighted_alignment:.2f}, "
          f"scale={result2.scaling_factor:.2f}, veto={result2.gatekeeper_veto}")
    
    # Scenario 3: Mixed predictions
    preds_mixed = [
        {'name': 'config_A', 'prob': 0.55, 'threshold': 0.50},  # Gate UP
        {'name': 'config_B', 'prob': 0.48, 'threshold': 0.50},  # DOWN
        {'name': 'config_C', 'prob': 0.49, 'threshold': 0.50},  # DOWN
        {'name': 'config_D', 'prob': 0.52, 'threshold': 0.50},  # UP
        {'name': 'config_E', 'prob': 0.53, 'threshold': 0.50},  # Gate UP
    ]
    
    print("\nScenario 3: Mixed predictions (3 UP, 2 DOWN)")
    result3 = voting.calculate_vote(preds_mixed, verbose=True)
    print(f"  → Final: align={result3.weighted_alignment:.2f}, "
          f"scale={result3.scaling_factor:.2f}, veto={result3.gatekeeper_veto}")
    
    print("\n✅ Test complete!")
