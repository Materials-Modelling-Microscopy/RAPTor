import pickle
import numpy as np
from pycalphad import Database, Workspace
from pycalphad import variables as v
import pandas as pd

from pathlib import Path

from external.Rapid_Phase_Field_Prediction.phase_diagram_generators.spinodal_predictor import (
	load_interaction_data,
	predict_spinodal,
)
from external.Rapid_Phase_Field_Prediction.phase_diagram_generators.energy_above_hull import (
	calculate_homogeneous_bcc_gibbs,
	energy_above_hull_mev,
)


MODULE_DIR = Path(__file__).resolve().parent
PHASEFIELD_ROOT = MODULE_DIR.parents[0]

SPINODAL_DATA_PATH = (
    PHASEFIELD_ROOT
    / "input"
    / "spinodal"
    / "binary_interactions.json"
)


class symplexDataGenerator:
	
	def __init__(self,
	             alloy_system,
	             temperature,
	             property):
		
		self.alloy_system = alloy_system
		self.temperature = temperature
		self.property = property
		
	def _order(self):
		return len(self.alloy_system)
	
	def _composition(self):
		return '-'.join(self.alloy_system)
	
	def _extract_data_template(self):
		order = self._order()
		if order == 4:
			grid_path = MODULE_DIR / "mol_grid_data" / "quaternary_raw.pkl"
		elif order == 5:
			grid_path = MODULE_DIR / "mol_grid_data" / "quinary_raw.pkl"
		else:
			raise ValueError(
				f"SymPlex generation supports quaternary and quinary systems; got {order} elements."
			)

		if not grid_path.exists():
			raise FileNotFoundError(f"Composition grid not found: {grid_path}")

		with grid_path.open("rb") as f:
			mol_dict = pickle.load(f)
	
		return mol_dict
	
	def _extract_tdb(self):
		composition = self._composition()
		path = PHASEFIELD_ROOT / "input" / "tdb" / f"{composition}.tdb"

		if not path.exists():
			raise FileNotFoundError(f"TDB file not found: {path}")

		return str(path)
	
	@staticmethod
	def predict_SPSS_fraction(equi, lattice):
		fracs_ans, phase_ans = np.round(equi.NP.values.squeeze(), 2), equi.Phase.values.squeeze()

		target = lattice

		mask = phase_ans == target

		if np.any(mask):
			bcc_fraction = np.nanmax(fracs_ans[mask])
		else:
			bcc_fraction = np.nan  # or np.nan, depending on what you want
		
		return bcc_fraction
	
	@staticmethod
	def predict_no_phases(equi, lattice):
		phase_ans = equi.Phase.values.squeeze()
		phases = np.asarray(phase_ans).ravel()
		valid_phases = [
			p for p in phases
			if p is not None
			   and not pd.isna(p)
			   and str(p).strip() != ""
		]
		n_phases = len(valid_phases)
		
		if n_phases == 0:
			n_phases = np.nan
		
		return n_phases
	
	def _extract_property(self):
		'''return callable function'''
		if self.property == 'SPSS Phase Fraction':
			return self.predict_SPSS_fraction
		if self.property == 'Number of Phases':
			return self.predict_no_phases
	
	def _extract_spinodal_data(self):
		return load_interaction_data(SPINODAL_DATA_PATH)
	
	def _is_spinodal_property(self):
		return self.property in [
			"Minimum Spinodal Eigenvalue",
			"Number of Negative Eigenvalues",
			"Spinodal Flag",
		]
	
	def _spinodal_value(self, mol, interaction_data, lattice):
		result = predict_spinodal(
			composition=self.alloy_system,
			temperature=self.temperature,
			lattice=lattice,
			mol=mol,
			interaction_data=interaction_data,
		)
		
		if self.property == "Minimum Spinodal Eigenvalue":
			return result["lambda_min"]
		
		if self.property == "Number of Negative Eigenvalues":
			return result["n_negative"]
		
		if self.property == "Spinodal Flag":
			return 1.0 if result["spinodal"] else 0.0
		
		raise ValueError(f"Unknown spinodal property: {self.property}")

	def _equilibrium_conditions(self, mol, independent_components):
		conditions = {
			v.X(component): float(mol[i])
			for i, component in enumerate(independent_components)
		}
		conditions[v.T] = self.temperature
		conditions[v.P] = 101325
		return conditions

	def _generate_equilibrium_data(self, mol_dict, lattice):
		"""
		Evaluate the full SymPlex grid with one reusable PyCalphad workspace.

		Creating a new ``equilibrium`` workspace for every composition rebuilds
		models and phase records hundreds of times. Updating only the condition
		values preserves those compiled objects while still solving every grid
		point independently.
		"""
		composition = self._composition()
		db = Database(self._extract_tdb())
		components = [element.upper() for element in composition.split("-")] + ["VA"]
		phases = list(db.phases.keys())
		independent_components = components[:-2]
		property_fn = self._extract_property()
		is_energy_above_hull = self.property == "BCC Energy Above Hull"

		if property_fn is None and not is_energy_above_hull:
			raise ValueError(f"Unknown equilibrium property: {self.property}")

		all_mols = [mol for mol_bar in mol_dict.values() for mol in mol_bar]
		bcc_gibbs = None
		if is_energy_above_hull:
			bcc_gibbs = calculate_homogeneous_bcc_gibbs(
				database=db,
				components=components[:-1],
				mols=all_mols,
				temperatures=[self.temperature],
			)[0]

		first_mol = next(iter(mol_dict.values()))[0]
		workspace = Workspace(
			database=db,
			components=components,
			phases=phases,
			conditions=self._equilibrium_conditions(first_mol, independent_components),
		)

		data = {}
		point_index = 0
		for path, mol_bar in mol_dict.items():
			temp_data = []
			for mol in mol_bar:
				try:
					workspace.conditions.update(
						self._equilibrium_conditions(mol, independent_components)
					)
					equilibrium_result = workspace.eq.get_dataset()
					if is_energy_above_hull:
						equilibrium_gibbs = float(
							np.asarray(equilibrium_result.GM, dtype=float).ravel()[0]
						)
						property_value = float(
							energy_above_hull_mev(
								bcc_gibbs[point_index], equilibrium_gibbs
							)
						)
					else:
						property_value = property_fn(equilibrium_result, lattice)
				except Exception:
					property_value = np.nan

				temp_data.append(property_value)
				point_index += 1

			data[path] = temp_data

		return data
	
	def generate(self):
		
		lattice = "BCC_A2"
		mol_dict = self._extract_data_template()
		data = {}
		
		if self._is_spinodal_property():
			interaction_data = self._extract_spinodal_data()
			
			for path, mol_bar in mol_dict.items():
				temp_data = []
				
				for mol in mol_bar:
					try:
						property_value = self._spinodal_value(
							mol=mol,
							interaction_data=interaction_data,
							lattice=lattice,
						)
					except Exception:
						property_value = np.nan
					
					temp_data.append(property_value)
				
				data[path] = temp_data
			
			return data
		
		return self._generate_equilibrium_data(mol_dict, lattice)
