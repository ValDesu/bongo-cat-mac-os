import sys
import os
import threading
from PyQt6.QtWidgets import QApplication, QWidget, QLabel, QMessageBox
from PyQt6.QtGui import QPixmap, QMovie, QFont
from PyQt6.QtCore import Qt, pyqtSignal, QObject, QTimer

# macOS specific imports for key logging
try:
    from ApplicationServices import *
    MACOS_AVAILABLE = True
except ImportError:
    MACOS_AVAILABLE = False

# --- Configuration Loading ---
def load_config():
    """Load configuration from settings.env file with fallback defaults."""
    config = {
        'ALWAYS_ON_TOP': False,
        'REMOVE_DECORATIONS': True,
        'THEME': 'nyao',
        'SCALE': 1
    }
    
    script_dir = os.path.dirname(os.path.abspath(__file__))
    settings_path = os.path.join(script_dir, 'settings.env')
    
    if os.path.exists(settings_path):
        try:
            with open(settings_path, 'r') as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith('#'):
                        if '=' in line:
                            key, value = line.split('=', 1)
                            key = key.strip()
                            value = value.strip()
                            
                            # Convert string values to appropriate types
                            if key in config:
                                if isinstance(config[key], bool):
                                    config[key] = value.lower() in ('true', '1', 'yes', 'on')
                                elif isinstance(config[key], int):
                                    try:
                                        config[key] = int(value)
                                    except ValueError:
                                        print(f"Warning: Invalid integer value for {key}: {value}")
                                elif isinstance(config[key], float):
                                    try:
                                        config[key] = float(value)
                                    except ValueError:
                                        print(f"Warning: Invalid float value for {key}: {value}")
                                else:
                                    config[key] = value
        except Exception as e:
            print(f"Warning: Error reading settings.env: {e}")
            print("Using default configuration values.")
    else:
        print("settings.env not found, using default configuration values.")
    
    return config

# Load configuration
_config = load_config()
ALWAYS_ON_TOP = _config['ALWAYS_ON_TOP']
REMOVE_DECORATIONS = _config['REMOVE_DECORATIONS']
THEME = _config['THEME']
SCALE = _config['SCALE']
# ---------------------


class KeyLogger(QObject):
    """
    A QObject-based key logger that runs in a separate thread
    and emits a signal when the keyboard state changes.
    """
    # Signal that will be emitted with the new state (left_state, right_state)
    stateChanged = pyqtSignal(int, int)

    def __init__(self):
        super().__init__()
        
        # Define keyboard areas based on a standard QWERTY layout
        self.l1keys = set('`1qaz2wsx')
        self.l2keys = set('3edc4rfv5tgb')
        self.r1keys = set('6yhn7ujm8ik,')
        self.r2keys = set("9ol.0p;/-[]'\\")
        
        # Add special keys
        self.l1keys.update({"tab", "caps", "left_shift", "left_ctrl", "left_option"})
        self.l2keys.update({"space", "left_cmd"})
        self.r1keys.update({"return", "right_cmd"}) # 'return' is often hit with the right pinky
        self.r2keys.update({"right_shift", "right_ctrl", "right_option", "delete"})

        # Key states
        self.pressed_keys = set()
        self.l1_pressed = False
        self.l2_pressed = False
        self.r1_pressed = False
        self.r2_pressed = False

    def keycode_to_key(self, keycode):
        # macOS virtual keycode to character mapping
        keymap = {
            0: "a", 1: "s", 2: "d", 3: "f", 4: "h", 5: "g", 6: "z", 7: "x",
            8: "c", 9: "v", 11: "b", 12: "q", 13: "w", 14: "e", 15: "r",
            16: "y", 17: "t", 18: "1", 19: "2", 20: "3", 21: "4", 22: "6",
            23: "5", 24: "=", 25: "9", 26: "7", 27: "-", 28: "8", 29: "0",
            30: "]", 31: "o", 32: "u", 33: "[", 34: "i", 35: "p", 36: "return",
            37: "l", 38: "j", 39: "'", 40: "k", 41: ";", 42: "\\", 43: ",",
            44: "/", 45: "n", 46: "m", 47: ".", 49: "space", 50: "`",
            51: "delete", 53: "escape", 55: "left_cmd", 54: "right_cmd",
            56: "left_shift", 60: "right_shift", 58: "left_option",
            61: "right_option", 59: "left_ctrl", 62: "right_ctrl", 57: "caps",
            48: "tab"
        }
        return keymap.get(keycode)

    def update_key_states(self):
        """Recalculate area press states based on the set of currently pressed keys."""
        self.l1_pressed = any(key in self.l1keys for key in self.pressed_keys)
        self.l2_pressed = any(key in self.l2keys for key in self.pressed_keys)
        self.r1_pressed = any(key in self.r1keys for key in self.pressed_keys)
        self.r2_pressed = any(key in self.r2keys for key in self.pressed_keys)
        
        left_state = 1 if self.l1_pressed else 2 if self.l2_pressed else 0
        right_state = 1 if self.r1_pressed else 2 if self.r2_pressed else 0
        
        self.stateChanged.emit(left_state, right_state)

    def event_callback(self, proxy, event_type, event, refcon):
        """The callback that fires on every key up/down event."""
        keycode = CGEventGetIntegerValueField(event, kCGKeyboardEventKeycode)
        key_name = self.keycode_to_key(keycode)
        if not key_name: return event

        if event_type == kCGEventKeyDown:
            self.pressed_keys.add(key_name)
        elif event_type == kCGEventKeyUp:
            self.pressed_keys.discard(key_name)
        
        self.update_key_states()
        return event

    def start_monitoring(self):
        """Sets up and starts the macOS event tap."""
        event_mask = (1 << kCGEventKeyDown) | (1 << kCGEventKeyUp)
        event_tap = CGEventTapCreate(
            kCGSessionEventTap, kCGHeadInsertEventTap, 0, event_mask, self.event_callback, 0
        )
        if not event_tap:
            return False

        run_loop_source = CFMachPortCreateRunLoopSource(kCFAllocatorDefault, event_tap, 0)
        CFRunLoopAddSource(CFRunLoopGetCurrent(), run_loop_source, kCFRunLoopCommonModes)
        CGEventTapEnable(event_tap, True)
        
        # The run loop needs to be started in its own thread
        thread = threading.Thread(target=CFRunLoopRun, daemon=True)
        thread.start()
        return True


class BongoCatApp(QWidget):
    def __init__(self):
        super().__init__()
        
        # Store current config for comparison
        self.current_config = {
            'ALWAYS_ON_TOP': ALWAYS_ON_TOP,
            'REMOVE_DECORATIONS': REMOVE_DECORATIONS,
            'THEME': THEME,
            'SCALE': SCALE
        }
        
        # Help overlay
        self.help_overlay = None
        self.help_visible = False
        
        # Load images first. If loading fails, we can't proceed.
        self.images = self.load_images()
        if not self.images or not self.images[0][0]:
            # The error message is shown in load_images()
            sys.exit(1) # Exit if default image is missing

        # Variables for window dragging
        self.dragging = False
        self.drag_position = None

        self.init_ui()
        self.init_key_listener()

    def load_images(self):
        """Loads all required GIF images from the 'img' folder."""
        script_dir = os.path.dirname(os.path.abspath(__file__))
        res_path = os.path.join(script_dir, "img", THEME)
        print(f"Loading images from: {res_path}")

        if not os.path.isdir(res_path):
            self.show_error("Resource Folder Not Found", f"The 'img' folder is missing from {script_dir}")
            return None
        
        images = [[None for _ in range(3)] for _ in range(3)]
        for left in range(3):
            for right in range(3):
                filepath = os.path.join(res_path, f"{left}{right}.gif")
                if os.path.exists(filepath):
                    images[left][right] = QMovie(filepath)
                    print(f"Loaded: {left}{right}.gif")
                else:
                    print(f"Warning: Missing image file: {left}{right}.gif")

        if not images[0][0]:
            self.show_error("Critical Error", "Default image '00.gif' could not be loaded. The application cannot start.")
            return None
            
        return images

    def init_ui(self):
        """Configures the application window and label."""
        # Get dimensions from the default movie (00.gif)
        # We need to start the movie to get a valid frame rect
        default_movie = self.images[0][0]
        default_movie.start()
        width = int(default_movie.frameRect().width() * SCALE)
        height = int(default_movie.frameRect().height() * SCALE)
        default_movie.stop()

        self.setGeometry(100, 100, width, height)
        self.setWindowTitle("Bongo Cat")

        # Set window flags for appearance
        flags = Qt.WindowType.Widget
        if REMOVE_DECORATIONS:
            flags |= Qt.WindowType.FramelessWindowHint
        if ALWAYS_ON_TOP:
            flags |= Qt.WindowType.WindowStaysOnTopHint
        self.setWindowFlags(flags)

        # Set transparency
        if REMOVE_DECORATIONS:
            self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

        # Create a label to display the animation
        self.label = QLabel(self)
        self.label.setGeometry(0, 0, width, height)
        # Scale the label content if needed
        if SCALE != 1:
            self.label.setScaledContents(True)
        self.update_image(0, 0) # Set initial image
        
        # Enable keyboard focus for shortcuts
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        
        self.show()

    def init_key_listener(self):
        """Initializes and connects the key logger."""
        self.key_logger = KeyLogger()
        
        # Connect the logger's signal to the update_image slot
        self.key_logger.stateChanged.connect(self.update_image)

        if not self.key_logger.start_monitoring():
            self.show_error("Permissions Error",
                "Failed to start key listener.\n"
                "Please grant Accessibility permissions to your Terminal or IDE:\n"
                "System Settings > Privacy & Security > Accessibility")
            self.close()

    def update_image(self, left_state, right_state):
        """Slot to update the displayed GIF based on keyboard state."""
        movie = self.images[left_state][right_state]
        if movie:
            if self.label.movie() is not movie:
                self.label.setMovie(movie)
                movie.start()
        else:
            # Fallback to default if a combination is missing
            default_movie = self.images[0][0]
            if self.label.movie() is not default_movie:
                self.label.setMovie(default_movie)
                default_movie.start()

    def show_error(self, title, message):
        """Utility to show a blocking error message."""
        msg_box = QMessageBox()
        msg_box.setIcon(QMessageBox.Icon.Critical)
        msg_box.setText(title)
        msg_box.setInformativeText(message)
        msg_box.setWindowTitle("Error")
        msg_box.exec()

    def mousePressEvent(self, event):
        """Handle mouse press events for window dragging."""
        if REMOVE_DECORATIONS and event.button() == Qt.MouseButton.LeftButton:
            self.dragging = True
            self.drag_position = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            event.accept()

    def mouseMoveEvent(self, event):
        """Handle mouse move events for window dragging."""
        if REMOVE_DECORATIONS and self.dragging and event.buttons() == Qt.MouseButton.LeftButton:
            self.move(event.globalPosition().toPoint() - self.drag_position)
            event.accept()

    def mouseReleaseEvent(self, event):
        """Handle mouse release events for window dragging."""
        if REMOVE_DECORATIONS and event.button() == Qt.MouseButton.LeftButton:
            self.dragging = False
            event.accept()

    def reload_settings(self):
        """Reload settings from settings.env and apply changes."""
        print("Reloading settings...")
        
        # Load new configuration
        new_config = load_config()
        
        # Check what changed
        theme_changed = new_config['THEME'] != self.current_config['THEME']
        scale_changed = new_config['SCALE'] != self.current_config['SCALE']
        always_on_top_changed = new_config['ALWAYS_ON_TOP'] != self.current_config['ALWAYS_ON_TOP']
        decorations_changed = new_config['REMOVE_DECORATIONS'] != self.current_config['REMOVE_DECORATIONS']
        
        # Update global variables
        global ALWAYS_ON_TOP, REMOVE_DECORATIONS, THEME, SCALE
        ALWAYS_ON_TOP = new_config['ALWAYS_ON_TOP']
        REMOVE_DECORATIONS = new_config['REMOVE_DECORATIONS']
        THEME = new_config['THEME']
        SCALE = new_config['SCALE']
        
        # Update stored config
        self.current_config = new_config.copy()
        
        # Apply changes that require UI updates
        if theme_changed:
            print(f"Theme changed to: {THEME}")
            # Reload images for new theme
            new_images = self.load_images()
            if new_images and new_images[0][0]:
                self.images = new_images
                # Update current display with new theme
                self.update_image(0, 0)  # Reset to default state
            else:
                print(f"Warning: Could not load theme '{THEME}', keeping current theme.")
        
        if scale_changed:
            print(f"Scale changed to: {SCALE}")
            self.apply_scale_changes()
        
        if always_on_top_changed or decorations_changed:
            print("Window flags changed, applying...")
            self.apply_window_flag_changes()
        
        print("Settings reloaded successfully!")

    def apply_scale_changes(self):
        """Apply scale changes to the window and label."""
        if self.images and self.images[0][0]:
            default_movie = self.images[0][0]
            default_movie.start()
            width = int(default_movie.frameRect().width() * SCALE)
            height = int(default_movie.frameRect().height() * SCALE)
            default_movie.stop()
            
            self.resize(width, height)
            self.label.setGeometry(0, 0, width, height)
            
            # Update scaled contents setting
            self.label.setScaledContents(SCALE != 1)

    def apply_window_flag_changes(self):
        """Apply window flag changes (always on top, decorations)."""
        flags = Qt.WindowType.Widget
        if REMOVE_DECORATIONS:
            flags |= Qt.WindowType.FramelessWindowHint
        if ALWAYS_ON_TOP:
            flags |= Qt.WindowType.WindowStaysOnTopHint
        
        # Store current position
        current_pos = self.pos()
        
        # Apply new flags
        self.setWindowFlags(flags)
        
        # Set transparency based on decorations setting
        if REMOVE_DECORATIONS:
            self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        else:
            self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, False)
        
        # Restore position and show window
        self.move(current_pos)
        self.show()

    def adjust_scale(self, delta):
        """Adjust the scale by the given delta and apply changes."""
        global SCALE
        new_scale = SCALE + delta
        
        # Clamp scale to reasonable bounds (0.1 to 5.0)
        new_scale = max(0.1, min(5.0, new_scale))
        
        if new_scale != SCALE:
            old_scale = SCALE
            SCALE = new_scale
            self.current_config['SCALE'] = SCALE
            
            print(f"Scale changed from {old_scale:.1f} to {SCALE:.1f}")
            self.apply_scale_changes()
            
            # Update the settings.env file to persist the change
            self.update_settings_file()
        else:
            print(f"Scale already at bounds (current: {SCALE:.1f})")

    def update_settings_file(self):
        """Update the settings.env file with current configuration."""
        script_dir = os.path.dirname(os.path.abspath(__file__))
        settings_path = os.path.join(script_dir, 'settings.env')
        
        try:
            # Read current file contents
            lines = []
            if os.path.exists(settings_path):
                with open(settings_path, 'r') as f:
                    lines = f.readlines()
            
            # Update or add configuration values
            config_keys = {'ALWAYS_ON_TOP', 'REMOVE_DECORATIONS', 'THEME', 'SCALE'}
            updated_keys = set()
            
            for i, line in enumerate(lines):
                stripped = line.strip()
                if stripped and not stripped.startswith('#') and '=' in stripped:
                    key = stripped.split('=', 1)[0].strip()
                    if key in config_keys:
                        if key == 'ALWAYS_ON_TOP':
                            lines[i] = f"ALWAYS_ON_TOP={'true' if self.current_config['ALWAYS_ON_TOP'] else 'false'}\n"
                        elif key == 'REMOVE_DECORATIONS':
                            lines[i] = f"REMOVE_DECORATIONS={'true' if self.current_config['REMOVE_DECORATIONS'] else 'false'}\n"
                        elif key == 'THEME':
                            lines[i] = f"THEME={self.current_config['THEME']}\n"
                        elif key == 'SCALE':
                            lines[i] = f"SCALE={self.current_config['SCALE']}\n"
                        updated_keys.add(key)
            
            # Add any missing keys
            missing_keys = config_keys - updated_keys
            if missing_keys:
                if lines and not lines[-1].endswith('\n'):
                    lines.append('\n')
                for key in missing_keys:
                    if key == 'ALWAYS_ON_TOP':
                        lines.append(f"ALWAYS_ON_TOP={'true' if self.current_config['ALWAYS_ON_TOP'] else 'false'}\n")
                    elif key == 'REMOVE_DECORATIONS':
                        lines.append(f"REMOVE_DECORATIONS={'true' if self.current_config['REMOVE_DECORATIONS'] else 'false'}\n")
                    elif key == 'THEME':
                        lines.append(f"THEME={self.current_config['THEME']}\n")
                    elif key == 'SCALE':
                        lines.append(f"SCALE={self.current_config['SCALE']}\n")
            
            # Write back to file
            with open(settings_path, 'w') as f:
                f.writelines(lines)
                
        except Exception as e:
            print(f"Warning: Could not update settings.env: {e}")

    def get_available_themes(self):
        """Get a list of available theme folders."""
        script_dir = os.path.dirname(os.path.abspath(__file__))
        img_dir = os.path.join(script_dir, "img")
        
        if not os.path.exists(img_dir):
            return []
        
        themes = []
        for item in os.listdir(img_dir):
            theme_path = os.path.join(img_dir, item)
            if os.path.isdir(theme_path):
                # Check if it has at least the default 00.gif file
                default_gif = os.path.join(theme_path, "00.gif")
                if os.path.exists(default_gif):
                    themes.append(item)
        
        return sorted(themes)

    def cycle_theme(self):
        """Cycle to the next available theme."""
        available_themes = self.get_available_themes()
        
        if len(available_themes) <= 1:
            print("No other themes available to cycle through.")
            return
        
        global THEME
        current_index = 0
        
        # Find current theme index
        try:
            current_index = available_themes.index(THEME)
        except ValueError:
            print(f"Current theme '{THEME}' not found in available themes, starting from first theme.")
        
        # Move to next theme (cycle back to start if at end)
        next_index = (current_index + 1) % len(available_themes)
        new_theme = available_themes[next_index]
        
        # Update theme
        old_theme = THEME
        THEME = new_theme
        self.current_config['THEME'] = THEME
        
        print(f"Theme changed from '{old_theme}' to '{THEME}' ({next_index + 1}/{len(available_themes)})")
        
        # Reload images for new theme
        new_images = self.load_images()
        if new_images and new_images[0][0]:
            self.images = new_images
            # Update current display with new theme
            self.update_image(0, 0)  # Reset to default state
            
            # Update the settings.env file to persist the change
            self.update_settings_file()
        else:
            # Revert if loading failed
            THEME = old_theme
            self.current_config['THEME'] = THEME
            print(f"Warning: Could not load theme '{new_theme}', reverted to '{old_theme}'.")

    def create_help_overlay(self):
        """Create the help overlay widget."""
        if self.help_overlay is not None:
            return
            
        # Create overlay widget
        self.help_overlay = QLabel(self)
        
        # Set up the help text
        help_text = """
🐱 Bongo Cat - Keyboard Shortcuts

⌨️  Controls:
• Ctrl+R (⌘+R)  -  Reload settings from settings.env
• Ctrl+U (⌘+U)  -  Upscale (+0.1)
• Ctrl+D (⌘+D)  -  Downscale (-0.1)
• Ctrl+T (⌘+T)  -  Cycle through themes
• Ctrl+H (⌘+H)  -  Show/hide this help

🎨  Current Settings:
• Theme: {theme}
• Scale: {scale}
• Always on Top: {always_on_top}
• Decorations: {decorations}

💡  Tips:
• Drag the cat around when decorations are off
• All changes auto-save to settings.env
• Edit settings.env manually and press Ctrl+R to reload

Press Ctrl+H (⌘+H) again to close this help
        """.format(
            theme=THEME,
            scale=f"{SCALE:.1f}",
            always_on_top="Yes" if ALWAYS_ON_TOP else "No",
            decorations="Hidden" if REMOVE_DECORATIONS else "Visible"
        ).strip()
        
        self.help_overlay.setText(help_text)
        
        # Style the overlay
        self.help_overlay.setStyleSheet("""
            QLabel {
                background-color: rgba(0, 0, 0, 180);
                color: white;
                font-family: 'SF Mono', 'Monaco', 'Menlo', monospace;
                font-size: 11px;
                padding: 15px;
                border-radius: 8px;
                line-height: 1.3;
            }
        """)
        
        # Set font
        font = QFont("SF Mono", 11)
        if not font.exactMatch():
            font = QFont("Monaco", 11)
        if not font.exactMatch():
            font = QFont("Menlo", 11)
        if not font.exactMatch():
            font = QFont("Courier", 11)
        self.help_overlay.setFont(font)
        
        # Set alignment and word wrap
        self.help_overlay.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        self.help_overlay.setWordWrap(True)
        self.help_overlay.setScaledContents(False)
        
        # Allow the label to resize to fit content
        self.help_overlay.setSizePolicy(
            self.help_overlay.sizePolicy().horizontalPolicy(),
            self.help_overlay.sizePolicy().verticalPolicy()
        )
        
        # Position and size the overlay
        self.position_help_overlay()
        
        # Hide initially
        self.help_overlay.hide()

    def position_help_overlay(self):
        """Position the help overlay in the center of the window."""
        if self.help_overlay is None:
            return
            
        # Calculate the size needed for the content
        self.help_overlay.adjustSize()  # Let Qt calculate the optimal size
        content_width = self.help_overlay.width()
        content_height = self.help_overlay.height()
        
        # Set minimum size but allow expansion for content
        window_width = self.width()
        window_height = self.height()
        
        # Use content size but ensure it fits within reasonable bounds
        min_width = 400
        min_height = 350
        max_width = max(window_width - 40, min_width)
        max_height = max(window_height - 40, min_height)
        
        # Use the larger of content size or minimum size, but cap at maximum
        overlay_width = min(max(content_width + 40, min_width), max_width)
        overlay_height = min(max(content_height + 40, min_height), max_height)
        
        # Center the overlay
        x = (window_width - overlay_width) // 2
        y = (window_height - overlay_height) // 2
        
        self.help_overlay.setGeometry(x, y, overlay_width, overlay_height)

    def toggle_help(self):
        """Toggle the visibility of the help overlay."""
        if self.help_overlay is None:
            self.create_help_overlay()
        
        self.help_visible = not self.help_visible
        
        if self.help_visible:
            # Update the help text with current settings
            self.update_help_text()
            self.position_help_overlay()
            self.help_overlay.show()
            self.help_overlay.raise_()  # Bring to front
            print("Help overlay shown")
        else:
            self.help_overlay.hide()
            print("Help overlay hidden")

    def update_help_text(self):
        """Update the help overlay text with current settings."""
        if self.help_overlay is None:
            return
            
        help_text = """
🐱 Bongo Cat - Keyboard Shortcuts

⌨️  Controls:
• Ctrl+R (⌘+R)  -  Reload settings from settings.env
• Ctrl+U (⌘+U)  -  Upscale (+0.1)
• Ctrl+D (⌘+D)  -  Downscale (-0.1)
• Ctrl+T (⌘+T)  -  Cycle through themes
• Ctrl+H (⌘+H)  -  Show/hide this help

🎨  Current Settings:
• Theme: {theme}
• Scale: {scale}
• Always on Top: {always_on_top}
• Decorations: {decorations}

💡  Tips:
• Drag the cat around when decorations are off
• All changes auto-save to settings.env
• Edit settings.env manually and press Ctrl+R to reload

Press Ctrl+H (⌘+H) again to close this help
        """.format(
            theme=THEME,
            scale=f"{SCALE:.1f}",
            always_on_top="Yes" if ALWAYS_ON_TOP else "No",
            decorations="Hidden" if REMOVE_DECORATIONS else "Visible"
        ).strip()
        
        self.help_overlay.setText(help_text)

    def keyPressEvent(self, event):
        """Handle keyboard shortcuts."""
        ctrl_or_cmd = (event.modifiers() & Qt.KeyboardModifier.ControlModifier or 
                       event.modifiers() & Qt.KeyboardModifier.MetaModifier)
        
        if ctrl_or_cmd:
            if event.key() == Qt.Key.Key_R:
                # Ctrl+R: Reload settings
                self.reload_settings()
                event.accept()
                return
            elif event.key() == Qt.Key.Key_U:
                # Ctrl+U: Upscale (increase by 0.1)
                self.adjust_scale(0.1)
                event.accept()
                return
            elif event.key() == Qt.Key.Key_D:
                # Ctrl+D: Downscale (decrease by 0.1)
                self.adjust_scale(-0.1)
                event.accept()
                return
            elif event.key() == Qt.Key.Key_T:
                # Ctrl+T: Cycle theme
                self.cycle_theme()
                event.accept()
                return
            elif event.key() == Qt.Key.Key_H:
                # Ctrl+H: Toggle help overlay
                self.toggle_help()
                event.accept()
                return
        
        super().keyPressEvent(event)

    def resizeEvent(self, event):
        """Handle window resize events to reposition help overlay."""
        super().resizeEvent(event)
        if self.help_overlay is not None and self.help_visible:
            self.position_help_overlay()

def main():
    if not MACOS_AVAILABLE or sys.platform != "darwin":
        print("This application is designed for macOS and requires pyobjc.", file=sys.stderr)
        sys.exit(1)
        
    app = QApplication(sys.argv)
    bongo_cat = BongoCatApp()
    
    # Catch Ctrl+C in the terminal
    def sigint_handler(*args):
        print("\nShutting down Bongo Cat...")
        QApplication.quit()
    
    import signal
    signal.signal(signal.SIGINT, sigint_handler)

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
