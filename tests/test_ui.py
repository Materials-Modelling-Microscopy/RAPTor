import unittest

from streamlit.testing.v1 import AppTest


def _mole_fraction_app():
    import streamlit as st

    from alloy_web.ui import mole_fraction_inputs

    st.session_state.result = mole_fraction_inputs(["Cr", "Nb", "Ti", "V"])


class MoleFractionInputTests(unittest.TestCase):
    def test_final_fraction_tracks_the_first_three_fractions(self):
        app = AppTest.from_function(_mole_fraction_app).run(timeout=15)

        for fraction in app.session_state.result:
            self.assertAlmostEqual(fraction, 0.25)
        self.assertTrue(all(not field.disabled for field in app.number_input[:3]))
        self.assertTrue(app.number_input[3].disabled)
        self.assertTrue(
            all("calculated" not in field.label for field in app.number_input)
        )

        app.number_input[0].set_value(0.1).run(timeout=15)
        app.number_input[1].set_value(0.2).run(timeout=15)
        app.number_input[2].set_value(0.3).run(timeout=15)

        expected_remainder = 1.0 - 0.1 - 0.2 - 0.3
        self.assertAlmostEqual(app.session_state.result[3], expected_remainder)
        self.assertAlmostEqual(app.number_input[3].value, expected_remainder)
        self.assertEqual(len(app.warning), 0)

    def test_overfilled_fractions_leave_zero_remainder_and_warn(self):
        app = AppTest.from_function(_mole_fraction_app).run(timeout=15)

        app.number_input[0].set_value(0.8).run(timeout=15)
        app.number_input[1].set_value(0.5).run(timeout=15)

        self.assertEqual(list(app.session_state.result), [0.8, 0.5, 0.25, 0.0])
        self.assertEqual(len(app.warning), 1)


if __name__ == "__main__":
    unittest.main()
