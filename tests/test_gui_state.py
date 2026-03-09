from pixel_fix.gui.state import PreviewSettings, SettingsSession


def test_apply_tracks_undo_history() -> None:
    session = SettingsSession()
    session.apply(generated_shades=8)
    assert session.current.generated_shades == 8
    assert session.history.can_undo()


def test_undo_restores_previous_settings() -> None:
    session = SettingsSession(PreviewSettings(generated_shades=4, pixel_width=2))
    session.apply(generated_shades=8)
    session.apply(pixel_width=4)

    restored = session.undo()
    assert restored.generated_shades == 8
    assert restored.pixel_width == 2

    restored = session.undo()
    assert restored.generated_shades == 4
    assert restored.pixel_width == 2
