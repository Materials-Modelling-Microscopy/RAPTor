from alloy_web.adapters.alloy_summary_adapter import resolve_tdb_for_system
from alloy_web.config import TDB_DIR
from external.Symplex.generate_plot import generate_symplex_plot
from external.Rapid_Phase_Field_Prediction.phase_diagram_generators.symplex_data_generator import symplexDataGenerator
from dataclasses import dataclass
from typing import Any
import pickle
import matplotlib.figure


@dataclass
class SymplexPredictionResult:
    """Generated SymPlex property data and its Matplotlib figure.

    Attributes:
        alloy_system: Elements in resolved TDB order.
        temperature: Calculation temperature in kelvin.
        constraint_element: Element used to organize the projection.
        property_name: Exact generated-property identifier.
        data: SymPlex grid and property values consumed by the plotter.
        figure: Generated Matplotlib figure.
    """
    alloy_system: list[str]
    temperature: float
    constraint_element: str
    property_name: str
    data: dict[str, Any]
    figure: matplotlib.figure.Figure

    def to_pickle_bytes(self) -> bytes:
        return pickle.dumps(self.data)


def run_symplex_prediction(
    alloy_system: list[str],
    temperature: float,
    constraint_element: str,
    property_name: str,
) -> SymplexPredictionResult:
    """Generate a property map for a quaternary or quinary alloy system.

    Args:
        alloy_system: Four or five element symbols.
        temperature: Calculation temperature in kelvin.
        constraint_element: An element in ``alloy_system`` used to organize the
            SymPlex projection.
        property_name: Property identifier understood by the SymPlex generator.

    Returns:
        Generated property data and a ready-to-save Matplotlib figure.

    Raises:
        ValueError: If the system order is unsupported or the constraint element
            is absent.
        FileNotFoundError: If no packaged TDB covers the requested elements.

    Notes:
        This function uses RAPTor's packaged ``TDB_DIR`` and can be
        computationally expensive for fine high-dimensional grids.
    """

    if len(alloy_system) not in [4, 5]:
        raise ValueError(
            f"SymPlex currently supports quaternary or quinary systems. "
            f"Received {len(alloy_system)} elements: {alloy_system}"
        )

    if constraint_element not in alloy_system:
        raise ValueError(
            f"constraint_element={constraint_element} is not in alloy_system={alloy_system}"
        )

    # The generator builds its TDB path straight from this list, so hand it
    # the order the database file is named with.
    _, alloy_system = resolve_tdb_for_system(alloy_system, TDB_DIR)

    data = symplexDataGenerator(
        alloy_system=alloy_system,
        temperature=temperature,
        property=property_name,
    ).generate()

    fig = generate_symplex_plot(
        alloy_system=alloy_system,
        temperature=temperature,
        constraint_element=constraint_element,
        property_name=property_name,
        data=data,
    )

    return SymplexPredictionResult(
        alloy_system=alloy_system,
        temperature=temperature,
        constraint_element=constraint_element,
        property_name=property_name,
        data=data,
        figure=fig,
    )
