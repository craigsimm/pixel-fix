from pixel_fix.gui.zoom import choose_fit_zoom, clamp_zoom, zoom_in, zoom_out


def test_clamp_zoom_uses_presets() -> None:
    assert clamp_zoom(350) == 400
    assert clamp_zoom(120) == 100


def test_zoom_steps() -> None:
    assert zoom_in(100) == 200
    assert zoom_in(800) == 800
    assert zoom_out(800) == 400
    assert zoom_out(100) == 100


def test_fit_zoom_chooses_largest_supported_preset() -> None:
    assert choose_fit_zoom(100, 100, 220, 220) == 200
    assert choose_fit_zoom(100, 100, 700, 700) == 400
    assert choose_fit_zoom(100, 100, 50, 50) == 100
