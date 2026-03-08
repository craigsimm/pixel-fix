from pixel_fix.gui.state import PreviewSettings, SettingsSession


def test_apply_tracks_undo_history() -> None:
    session = SettingsSession()
    session.apply(colors=8)
    assert session.current.colors == 8
    assert session.history.can_undo()


def test_undo_restores_previous_settings() -> None:
    session = SettingsSession(PreviewSettings(colors=16, min_island_size=2))
    session.apply(colors=32)
    session.apply(min_island_size=4)

    restored = session.undo()
    assert restored.colors == 32
    assert restored.min_island_size == 2

    restored = session.undo()
    assert restored.colors == 16
    assert restored.min_island_size == 2
