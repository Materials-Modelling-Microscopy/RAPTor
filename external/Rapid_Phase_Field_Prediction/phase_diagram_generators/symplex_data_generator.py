import pickle
import numpy as np
from pycalphad import Database, equilibrium
from pycalphad import variables as v
import pandas as pd

from pathlib import Path

from phase_diagram_generators.spinodal_predictor import (
    load_interaction_data,
    predict_spinodal,
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
		mol_dict = {}
		if order == 4:
			with open(f"/Users/pravanomprakash/Documents/Projects/RPFP_web/external/Rapid_Phase_Field_Prediction/phase_diagram_generators/mol_grid_data/quaternary_raw.pkl", "rb") as f:
				mol_dict = pickle.load(f)
		if order == 5:
			with open(f"/Users/pravanomprakash/Documents/Projects/RPFP_web/external/Rapid_Phase_Field_Prediction/phase_diagram_generators/mol_grid_data/quinary_raw.pkl", "rb") as f:
				mol_dict = pickle.load(f)
	
		return mol_dict
	
	def _extract_tdb(self):
		composition = self._composition()
		path = f"/Users/pravanomprakash/Documents/Projects/RPFP_web/external/Rapid_Phase_Field_Prediction/input/tdb/{composition}.tdb"
		return path
	
	@staticmethod
	def predict_SPSS_fraction(df, comps, phases, feats, lattice):
		equi = equilibrium(df, comps, phases, feats)
		fracs_ans, phase_ans = np.round(equi.NP.values.squeeze(), 2), equi.Phase.values.squeeze()

		target = lattice

		mask = phase_ans == target

		if np.any(mask):
			bcc_fraction = np.nanmax(fracs_ans[mask])
		else:
			bcc_fraction = np.nan  # or np.nan, depending on what you want
		
		return bcc_fraction
	
	@staticmethod
	def predict_no_phases(df, comps, phases, feats, lattice):
		equi = equilibrium(df, comps, phases, feats)
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
		
		composition = self._composition()
		tdb_path = self._extract_tdb()
		df = Database(tdb_path)
		
		property_fn = self._extract_property()
		
		for path, mol_bar in mol_dict.items():
			temp_data = []
			
			for mol in mol_bar:
				eles = composition.split("-")
				comps = [i.upper() for i in eles] + ["VA"]
				phases = list(df.phases.keys())
				
				independent_components = comps[:-2]
				
				feats = {
					v.X(component): float(mol[i])
					for i, component in enumerate(independent_components)
				}
				
				feats[v.T] = self.temperature
				feats[v.P] = 101325
				
				try:
					property_value = property_fn(
						df,
						comps,
						phases,
						feats,
						lattice,
					)
				except Exception:
					property_value = np.nan
				
				temp_data.append(property_value)
			
			data[path] = temp_data
		
		return data