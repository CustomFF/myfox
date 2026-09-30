from __future__ import annotations

from myfox.state import State
from ._helpers import IsolatedStateCase


class StateTests(IsolatedStateCase):
    def test_defaults_to_empty_when_no_file_exists(self):
        state = State()
        self.assertIsNone(state.get("install_dir"))
        self.assertEqual(state.get("install_dir", "fallback"), "fallback")
        self.assertFalse(state.is_installed())

    def test_get_after_set_without_save_is_in_memory_only(self):
        state = State()
        state.set("install_dir", "/opt/firefox")
        self.assertEqual(state.get("install_dir"), "/opt/firefox")
        self.assertTrue(state.is_installed())
        # A second, unrelated State() must not see it — nothing was saved.
        self.assertIsNone(State().get("install_dir"))

    def test_save_then_reload_round_trips(self):
        state = State()
        state.set("install_dir", "/opt/firefox")
        state.set("opt_bl", True)
        state.save()

        reloaded = State()
        self.assertEqual(reloaded.get("install_dir"), "/opt/firefox")
        self.assertIs(reloaded.get("opt_bl"), True)
        self.assertTrue(reloaded.is_installed())

    def test_corrupt_state_file_is_treated_as_empty_not_fatal(self):
        from myfox.state import state_file

        path = state_file()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("{not valid json", encoding="utf-8")

        state = State()  # must not raise
        self.assertIsNone(state.get("install_dir"))

    def test_clear_then_save_empties_the_file(self):
        state = State()
        state.set("install_dir", "/opt/firefox")
        state.save()

        state.clear()
        state.save()
        self.assertIsNone(State().get("install_dir"))

    def test_delete_file_is_safe_when_nothing_was_ever_saved(self):
        State().delete_file()  # must not raise
