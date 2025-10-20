# TUI Navigation Guide

## Tab Navigation
- **Number keys 1-6**: Switch to specific tabs
- **?**: Switch to Help tab

## Tab-Specific Controls

### Run Tab (1)
- **Enter**: Start the automation process
- **Ctrl+C**: Stop running process
- **q**: Quit application

### PRD Tab (2)
- **↑/↓ Arrow Keys**: Navigate through PRD files
- **Enter**: Select highlighted PRD file
- **t**: Add tag to selected PRD
- **Backspace**: Remove last tag
- **s**: Save tags for selected PRD
- **/**: Filter/search PRD files

### Settings Tab (3)
- **↑/↓/←/→**: Navigate between input fields (2D grid navigation)
- **Enter**: Focus first input field or unfocus current input
- **Esc**: Unfocus current input field
- **Type**: Edit focused input field
- **s**: Save configuration
- **Tab**: Alternative navigation (cycles through fields linearly)

### Env & Flags Tab (4)
- **↑/↓**: Navigate between flags (visual highlighting shows focused flag)
- **←/→/Enter**: Toggle the focused flag
- **L**: Toggle Local phase (direct toggle)
- **P**: Toggle PR phase (direct toggle)
- **R**: Toggle Review phase (direct toggle)
- **a**: Toggle Allow Unsafe flag (direct toggle)
- **d**: Toggle Dry Run flag (direct toggle)
- **g**: Toggle Sync Git flag (direct toggle)
- **i**: Toggle Infinite Reviews flag (direct toggle)
- **s**: Save configuration
- **Esc**: Unfocus current flag

### Prompt Tab (5)
- **↑/↓/←/→**: Focus text area when not focused
- **Enter**: Focus text area or add newline when already focused
- **Esc**: Unfocus text area
- **Arrow keys**: Navigate text when focused
- **Type**: Edit text when focused

### Logs Tab (6)
- **↑/↓ Arrow Keys**: Scroll through log output line by line
- **Page Up/Page Down**: Scroll by pages (10 lines at a time)
- **Home/End**: Jump to top/bottom of logs
- **Arrow keys**: Work for navigation when focused on logs

### Help Tab (?)
- **q**: Quit application
- **Number keys**: Switch to other tabs

## Global Controls
- **q**: Quit application (when not running)
- **Ctrl+C**: Stop process or quit
- **1-6**: Direct tab switching
- **?**: Show help

## Input Field Navigation
When an input field is focused:
- **Type normally**: Edit the field value
- **Enter/Esc**: Unfocus the field
- **Tab**: Move to next field (Settings tab only)
- **Arrow keys**: Move cursor within field

## Flag Navigation (Env Tab)
The Env tab now supports a flag selection system:
- **Visual Highlighting**: Focused flags are highlighted with background color
- **Two Navigation Modes**:
  1. **Arrow Key Mode**: Use ↑/↓ to navigate, ←/→/Enter to toggle
  2. **Direct Toggle Mode**: Use letter keys for immediate flag changes
- **Focus Management**: Esc clears flag focus, arrow keys establish focus
- **Smart Toggle**: Left/right arrows toggle the currently focused flag