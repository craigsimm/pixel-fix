Original prompt: update the fonts to use pixel-fix\fonts\pixelmix.ttf (size 6) also I want a dark theme that uses #222323 as the main colour, the lighter colours should be #F0F6F0 (for text)

- Added a shared GUI theme module with the requested dark palette and a Windows font loader for `fonts/pixelmix.ttf`.
- Updated the Tk/ttk app theme wiring, menus, canvases, scales, palette borders, and empty-canvas text to use the new palette and 6px pixel font.
- Updated tooltip styling to match the new dark theme.
- Styled ttk checkbox and radio indicators so their boxes/circles also use the dark palette instead of the default light theme.
- Switched to the requested three-color scheme, added `pixelmix_bold.ttf` for section headers and the Downsample/Apply Palette buttons, updated pressed-state button behavior to use the pale blue accent, and moved the palette into a fixed right-side column sized to 20% of the body width.
- Tightened palette swatches into a gapless grid with 1px borders that switch from `#222323` to `#7FD9F8` when selected.
- Replaced the header/special-button font with `ChiKareGo2.ttf` at size 12, gave the two special tk buttons the same 1px light border treatment as the rest of the UI, and moved `Adjust palette` under `Current palette` so the right column is split into two equal-height sections.
- Switched the header/special-button font again to `hiscore.ttf` (`New HiScore`) at size 8.
- Converted `Downsample` and `Apply Palette` to plain `ttk.Button`s so they now inherit the exact same border, font, and state styling as the other buttons.
- Forced ttk border/light/shadow colors to use `#F0F6F0` in the shared theme so any remaining default white borders/header rendering is replaced by the configured light grey.
- Added consistent internal padding to the shared `LabelFrame` section helper so the other containers match the more comfortable inset used by `Current palette`.
- Renamed section headers to the shorter labels: `Pixel scale`, `Resize`, `Palette`, and `Adjust`.
- Moved the palette reduction spinbox and renamed button (`Reduce Palette`) to the top of the Adjust section, and removed the old Palette Reduction row from Apply palette.
- Clicking the empty preview area with no image loaded now opens the same file picker as `File > Open`.
- Switched the section header font back to `pixelmix.ttf` and render section titles in all caps.
- Moved `Apply` into the Palette panel, reorganized the palette action buttons into three rows beneath the swatches, and changed selected swatches to use a 2px inset accent border.
- Added hover preview support for built-in palette menu entries so the swatches update while hovering menu options and revert when the menu closes without a selection.

TODO
- Launch the GUI in a desktop session to visually confirm ttk indicator styling on the target OS theme.
