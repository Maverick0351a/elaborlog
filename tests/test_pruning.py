from elaborlog.score import InfoModel
from elaborlog.config import ScoringConfig


def test_pruning_token_and_template_caps():
    cfg = ScoringConfig(max_tokens=200, max_templates=50)
    model = InfoModel(cfg)

    # Create lines with controlled token/template diversity.
    # Each line introduces two new unique tokens to accelerate reaching the cap.
    for i in range(1000):
        line = f"INFO user{i} action{i} attr{i} xyz"
        model.observe(line)
        # Invariants: sizes never exceed caps
        assert len(model.token_counts) <= cfg.max_tokens
        assert len(model.template_counts) <= cfg.max_templates

    # After saturation, ensure that the tokens with the smallest counts were pruned.
    # Since each token should have roughly similar counts, we introduce some high-frequency tokens
    # and ensure they remain.
    for _ in range(500):
        model.observe("INFO stable alpha beta gamma")

    assert 'stable' in model.token_counts
    assert 'alpha' in model.token_counts
    # Introduce many new tokens to force further pruning
    for j in range(500):
        model.observe(f"INFO churn{j} feature{j} attr{j}")

    assert len(model.token_counts) <= cfg.max_tokens
    assert len(model.template_counts) <= cfg.max_templates

    # Heuristic: high-frequency tokens should still be present; some churn tokens likely evicted
    evicted = sum(1 for j in range(500) if f'churn{j}' not in model.token_counts)
    assert evicted > 0  # At least some churn tokens must have been pruned
