# Calculation guides

| Question | Public function | Main result |
| --- | --- | --- |
| Which phases appear as temperature changes? | `run_phase_fraction_temperature_prediction` | Phase fractions and BCC energy above hull |
| How does equilibrium split a nominal composition? | `run_composition_splitting_prediction` | Phase-specific compositions |
| What does a binary or ternary phase diagram look like? | `run_phase_diagram_prediction` | T-x or isothermal ternary figure |
| Is the homogeneous solution locally stable? | `run_spinodal_analysis` | Hessian eigenvalues and soft mode |
| How does a property vary across a 4D/5D composition space? | `run_symplex_prediction` | SymPlex data and figure |
| Does sequential alloying route matter? | `run_pathway_analysis` | Per-path thermodynamic burden |
| What is known about one complete alloy system? | `run_alloy_system_summary` | PMR, subsystems, phases, interactions |
| Which candidate systems rank best? | `run_inter_system_comparison` | Ranked and Pareto-filtered table |

All temperatures are in kelvin unless a field explicitly states otherwise.
Composition vectors are mole fractions paired positionally with element lists.
