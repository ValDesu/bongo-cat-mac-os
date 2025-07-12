import sys
import os
import threading
from PyQt6.QtWidgets import QApplication, QWidget, QLabel, QMessageBox
from PyQt6.QtGui import QPixmap, QMovie
from PyQt6.QtCore import Qt, pyqtSignal, QObject

# macOS specific imports for key logging
try:
    from ApplicationServices import *
    MACOS_AVAILABLE = True
except ImportError:
    MACOS_AVAILABLE = False

# --- Configuration ---
# Set these to True to enable the features
ALWAYS_ON_TOP = False
REMOVE_DECORATIONS = True
THEME = "default"
SCALE = 0.5
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
