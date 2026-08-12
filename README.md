# TFT Analyzer

Trajectory-first Teamfight Tactics match recorder and post-game analysis platform.

## Architectural rules

1. **Raw evidence is immutable. Derived data is rebuildable.**
2. **Perception != game logic != analysis.**
3. **All future consumers use the same domain contracts.**
4. **Every derived artifact carries provenance/version information.**
5. **Real-time advice is an optional consumer, never part of the core pipeline.**

## Data pipeline

```text
Evidence -> Observation -> GameEvent -> GameState
                                      |
                                      +-> DecisionEpisode
                                              |
                     +------------------------+----------------------+
                     |                        |                      |
                  Analyzers                ML/Value              RL datasets
                     |                        |                      |
                  Findings              Counterfactuals        BC / Offline RL
                     |
                  Reports

GameState + Findings/Policy
          |
          +-> optional realtime advisor
```

## Stage 0

Implemented:
- versioned Pydantic domain models;
- evidence / observation / event / state / action / decision contracts;
- analyzer and transition-model protocols;
- future real-time advisor protocol;
- versioned match manifest;
- config skeleton;
- minimal CLI;
- initial contract tests.

Not implemented yet:
- screen capture;
- TFT recognition;
- event inference;
- persistent database;
- Riot API integration;
- analysis rules;
- ML / RL.

## Run

```bash
python -m venv .venv
source .venv/bin/activate
# PowerShell: .venv\Scripts\Activate.ps1

pip install -e ".[dev]"
pytest
python -m tft_analyzer
```
