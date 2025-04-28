#!/usr/bin/env python3
"""
Script to create parallel translation LaTeX documents from character-based dialogue input,
with fixes for Windows encoding issues when copying/pasting Spanish text.
"""

import curses
import re
import os
import sys
import locale
import codecs

# Set up locale for proper handling of non-ASCII characters
try:
    locale.setlocale(locale.LC_ALL, '')
except:
    pass  # Fail silently if locale setting fails

def fix_encoding(text):
    """
    Fix common encoding issues when pasting text in Windows.
    Converts incorrectly encoded characters back to their proper form.
    """
    encoding_fixes = {
        'Ã¡': 'á',
        'Ã©': 'é',
        'Ã­': 'í',
        'Ã³': 'ó',
        'Ãº': 'ú',
        'Ã±': 'ñ',
        'Ã': 'í',  # Sometimes just the first part appears
        'Â¡': '¡',
        'Â¿': '¿',
        'Ã\x81': 'Á',
        'Ã\x89': 'É',
        'Ã\x8d': 'Í',
        'Ã\x93': 'Ó',
        'Ã\x9a': 'Ú',
        'Ã\x91': 'Ñ',
    }
    
    for wrong, correct in encoding_fixes.items():
        text = text.replace(wrong, correct)
    
    return text

class ScrollableTextbox:
    """A scrollable text editor using curses with support for special characters."""
    
    def __init__(self, stdscr, height, width, y, x, prompt=""):
        self.stdscr = stdscr
        self.height = height
        self.width = width
        self.y = y
        self.x = x
        self.prompt = prompt
        
        # Content storage
        self.lines = [""]
        self.current_line = 0
        self.current_col = 0
        self.scroll_pos = 0
        
        # Create a window for the editor
        self.win = curses.newwin(height, width, y, x)
        self.win.keypad(True)
        
        # Create instructions window
        self.instructions_win = curses.newwin(1, width, y + height, x)
        self.instructions_win.addstr(0, 0, "Ctrl+G to save | Arrow keys to navigate | Ctrl+V to paste")
        self.instructions_win.refresh()
        
        # Draw a rectangle around the editor
        self._draw_border()
        self.stdscr.refresh()
        
        # Initialize cursor
        self._update_display()
    
    def _draw_border(self):
        """Draw a border around the editor with the prompt."""
        self.stdscr.attron(curses.A_BOLD)
        # Draw top border with title
        self.stdscr.addstr(self.y-1, self.x-1, "┌" + "─" * (self.width) + "┐")
        self.stdscr.addstr(self.y-1, self.x+2, f" {self.prompt} ")
        
        # Draw side borders
        for i in range(self.height):
            self.stdscr.addstr(self.y+i, self.x-1, "│")
            self.stdscr.addstr(self.y+i, self.x+self.width, "│")
        
        # Draw bottom border
        self.stdscr.addstr(self.y+self.height, self.x-1, "└" + "─" * (self.width) + "┘")
        self.stdscr.attroff(curses.A_BOLD)
        
        # Add scrollbar indicators if needed
        if len(self.lines) > self.height:
            # Show up arrow if scrolled down
            if self.scroll_pos > 0:
                self.stdscr.addstr(self.y, self.x+self.width, "↑")
            
            # Show down arrow if can scroll down more
            if self.scroll_pos + self.height < len(self.lines):
                self.stdscr.addstr(self.y+self.height-1, self.x+self.width, "↓")
    
    def _update_display(self):
        """Update the display with current content and cursor position."""
        self.win.clear()
        
        # Make sure scroll position is valid
        self._adjust_scroll()
        
        # Display visible lines
        display_lines = self.lines[self.scroll_pos:self.scroll_pos+self.height]
        for i, line in enumerate(display_lines):
            if i < self.height:
                try:
                    self.win.addstr(i, 0, line[:self.width-1])
                except curses.error:
                    # Handle potential curses errors when displaying special characters
                    # Just display what we can and continue
                    pass
        
        # Position cursor
        cursor_y = self.current_line - self.scroll_pos
        cursor_x = min(self.current_col, len(self.lines[self.current_line]))
        try:
            self.win.move(cursor_y, cursor_x)
        except curses.error:
            # Fallback to a safe position if there's an error
            self.win.move(0, 0)
        
        self._draw_border()
        self.win.refresh()
    
    def _adjust_scroll(self):
        """Adjust scroll position based on cursor."""
        # Scroll up if cursor above viewport
        if self.current_line < self.scroll_pos:
            self.scroll_pos = self.current_line
        
        # Scroll down if cursor below viewport
        elif self.current_line >= self.scroll_pos + self.height:
            self.scroll_pos = self.current_line - self.height + 1
    
    def edit(self):
        """Start the editor and return the entered text."""
        self.win.clear()
        self.win.refresh()
        
        # Main editing loop
        while True:
            self._update_display()
            
            try:
                ch = self.win.getch()
                
                # Save and exit with Ctrl+G
                if ch == 7:  # Ctrl+G
                    break
                
                # Handle special keys
                elif ch == curses.KEY_UP:
                    self._move_up()
                elif ch == curses.KEY_DOWN:
                    self._move_down()
                elif ch == curses.KEY_LEFT:
                    self._move_left()
                elif ch == curses.KEY_RIGHT:
                    self._move_right()
                elif ch == curses.KEY_HOME:
                    self.current_col = 0
                elif ch == curses.KEY_END:
                    self.current_col = len(self.lines[self.current_line])
                elif ch == curses.KEY_PPAGE:  # Page Up
                    self._page_up()
                elif ch == curses.KEY_NPAGE:  # Page Down
                    self._page_down()
                elif ch == 10:  # Enter
                    self._insert_newline()
                elif ch == 127 or ch == curses.KEY_BACKSPACE:  # Backspace
                    self._backspace()
                elif ch == curses.KEY_DC:  # Delete
                    self._delete()
                elif ch == curses.KEY_RESIZE:  # Terminal resize
                    self._handle_resize()
                elif ch == 22:  # Ctrl+V (paste)
                    self._handle_paste()
                # Handle regular printable characters and extended characters
                elif 32 <= ch <= 126 or ch > 127:  # ASCII printable and Unicode characters
                    # Convert character code to actual character
                    char = chr(ch)
                    self._insert_char(char)
            
            except KeyboardInterrupt:
                return ""
        
        # Return the complete text with encoding fixes
        result = '\n'.join(self.lines)
        return fix_encoding(result)
    
    def _move_up(self):
        """Move cursor up."""
        if self.current_line > 0:
            self.current_line -= 1
            self.current_col = min(self.current_col, len(self.lines[self.current_line]))
    
    def _move_down(self):
        """Move cursor down."""
        if self.current_line < len(self.lines) - 1:
            self.current_line += 1
            self.current_col = min(self.current_col, len(self.lines[self.current_line]))
    
    def _move_left(self):
        """Move cursor left."""
        if self.current_col > 0:
            self.current_col -= 1
        elif self.current_line > 0:
            # Move to end of previous line
            self.current_line -= 1
            self.current_col = len(self.lines[self.current_line])
    
    def _move_right(self):
        """Move cursor right."""
        if self.current_col < len(self.lines[self.current_line]):
            self.current_col += 1
        elif self.current_line < len(self.lines) - 1:
            # Move to beginning of next line
            self.current_line += 1
            self.current_col = 0
    
    def _page_up(self):
        """Move cursor up by a page."""
        self.current_line = max(0, self.current_line - self.height)
        self.scroll_pos = max(0, self.scroll_pos - self.height)
        self.current_col = min(self.current_col, len(self.lines[self.current_line]))
    
    def _page_down(self):
        """Move cursor down by a page."""
        self.current_line = min(len(self.lines) - 1, self.current_line + self.height)
        self.scroll_pos = min(len(self.lines) - 1, self.scroll_pos + self.height)
        self.current_col = min(self.current_col, len(self.lines[self.current_line]))
    
    def _insert_char(self, char):
        """Insert a character at the current position."""
        current = self.lines[self.current_line]
        self.lines[self.current_line] = current[:self.current_col] + char + current[self.current_col:]
        self.current_col += 1
    
    def _insert_newline(self):
        """Insert a new line at the current position."""
        current = self.lines[self.current_line]
        self.lines[self.current_line] = current[:self.current_col]
        self.lines.insert(self.current_line + 1, current[self.current_col:])
        self.current_line += 1
        self.current_col = 0
    
    def _backspace(self):
        """Delete the character before the cursor."""
        if self.current_col > 0:
            current = self.lines[self.current_line]
            self.lines[self.current_line] = current[:self.current_col-1] + current[self.current_col:]
            self.current_col -= 1
        elif self.current_line > 0:
            # Join with previous line
            self.current_col = len(self.lines[self.current_line - 1])
            self.lines[self.current_line - 1] += self.lines[self.current_line]
            self.lines.pop(self.current_line)
            self.current_line -= 1
    
    def _delete(self):
        """Delete the character at the cursor."""
        current = self.lines[self.current_line]
        if self.current_col < len(current):
            self.lines[self.current_line] = current[:self.current_col] + current[self.current_col+1:]
        elif self.current_line < len(self.lines) - 1:
            # Join with next line
            self.lines[self.current_line] += self.lines[self.current_line + 1]
            self.lines.pop(self.current_line + 1)
    
    def _handle_paste(self):
        """Handle pasting text from clipboard."""
        # This is a simple implementation - Windows terminal doesn't fully support
        # getting clipboard content directly in Python curses
        # Instead, we'll rely on the terminal's built-in paste functionality
        # which sends characters as if they were typed
        
        # Show a message to instruct the user
        self.instructions_win.clear()
        self.instructions_win.addstr(0, 0, "Paste your text now... Press Enter when done")
        self.instructions_win.refresh()
        
        # Let the terminal handle the paste operation
        # The characters will be processed one by one as they're typed
        
        # After a short delay, restore the normal instructions
        curses.napms(3000)  # 3 second delay
        self.instructions_win.clear()
        self.instructions_win.addstr(0, 0, "Ctrl+G to save | Arrow keys to navigate | Ctrl+V to paste")
        self.instructions_win.refresh()
    
    def _handle_resize(self):
        """Handle terminal resize event."""
        height, width = self.stdscr.getmaxyx()
        # Adjust window sizes if needed
        # This is a simplified resize handler - in a real app you'd want to be more thorough
        self.win.resize(min(self.height, height-self.y-1), min(self.width, width-self.x-1))
        self.instructions_win.resize(1, min(self.width, width-self.x-1))
        self.instructions_win.mvwin(min(self.y+self.height, height-1), self.x)
        self.instructions_win.clear()
        self.instructions_win.addstr(0, 0, "Ctrl+G to save | Arrow keys to navigate | Ctrl+V to paste")
        self.instructions_win.refresh()
    
    def set_text(self, text):
        """Set the editor content from a string."""
        self.lines = text.split('\n')
        if not self.lines:
            self.lines = [""]
        self.current_line = 0
        self.current_col = 0
        self.scroll_pos = 0
        self._update_display()

def parse_character_dialogue(text):
    """
    Parse text that contains character names in square brackets followed by dialogue.
    Support character names with spaces like [Angel Dust].
    Returns a list of tuples (character, dialogue).
    """
    if not text.strip():
        return []
    
    # First, fix any encoding issues
    text = fix_encoding(text)
    
    # Use regex to find character names in square brackets
    # This pattern will match [Name] including names with spaces like [Angel Dust]
    pattern = r'(\[[^\]]+\])'
    parts = re.split(pattern, text)
    
    # Remove any empty strings at the beginning
    if parts and not parts[0].strip():
        parts.pop(0)
    
    result = []
    current_character = None
    current_dialogue = ""
    
    for part in parts:
        if re.match(r'\[.+\]', part):  # This is a character name
            # If we already have a character and dialogue, save it
            if current_character is not None:
                result.append((current_character, current_dialogue.strip()))
            
            # Start a new character's dialogue
            current_character = part
            current_dialogue = ""
        else:
            # Add to the current dialogue
            current_dialogue += part
    
    # Add the last character's dialogue if it exists
    if current_character is not None:
        result.append((current_character, current_dialogue.strip()))
    
    return result

def escape_latex_special_chars(text):
    """
    Escape special LaTeX characters to ensure proper rendering.
    """
    # Define LaTeX special characters and their escaped versions
    latex_special_chars = {
        '&': r'\&',
        '%': r'\%',
        '$': r'\$',
        '#': r'\#',
        '_': r'\_',
        '{': r'\{',
        '}': r'\}',
        '~': r'\textasciitilde{}',
        '^': r'\textasciicircum{}',
        '\\': r'\textbackslash{}',
        '<': r'\textless{}',
        '>': r'\textgreater{}'
    }
    
    # Replace special characters with their escaped versions
    for char, replacement in latex_special_chars.items():
        text = text.replace(char, replacement)
    
    return text

def generate_latex(title, author, left_dialogues, right_dialogues):
    """Generate LaTeX document with parallel translation supporting special characters."""
    
    # Escape special LaTeX characters in title and author
    title = escape_latex_special_chars(title)
    author = escape_latex_special_chars(author)
    
    # Preamble with enhanced language support
    latex = r"""\documentclass[12pt,a4paper]{article}
\usepackage[margin=1in]{geometry}
\usepackage{parallel}
\usepackage{fontspec}
\usepackage{polyglossia}
\usepackage{microtype}
\usepackage{titlesec}
\usepackage{fancyhdr}
\usepackage{xcolor}
\usepackage[utf8]{inputenc}

% Set up multilingual support
\setmainlanguage{english}
\setotherlanguage{spanish} % For Spanish support

% Use a font with good Unicode support
\setmainfont{DejaVu Serif}
\setsansfont{DejaVu Sans}

% Character name styling
\newcommand{\charname}[1]{\textbf{\textcolor{blue}{#1}}}

% Custom title format
\titleformat{\section}
  {\normalfont\Large\bfseries}{\thesection}{1em}{}

% Page style setup
\pagestyle{fancy}
\fancyhf{}
\rhead{Parallel Translation}
\lhead{\thepage}
\renewcommand{\headrulewidth}{0.4pt}
\renewcommand{\footrulewidth}{0.4pt}

\title{""" + title + r"""}
\author{""" + author + r"""}
\date{\today}

\begin{document}

\maketitle

\begin{Parallel}{0.48\textwidth}{0.48\textwidth}
"""

    # Ensure we process only the min number of dialogues available in both
    num_dialogues = min(len(left_dialogues), len(right_dialogues))
    
    for i in range(num_dialogues):
        left_char, left_text = left_dialogues[i]
        right_char, right_text = right_dialogues[i]
        
        # Format character names (remove brackets) for display
        left_char_formatted = left_char.strip('[]')
        right_char_formatted = right_char.strip('[]')
        
        # Fix any encoding issues
        left_char_formatted = fix_encoding(left_char_formatted)
        right_char_formatted = fix_encoding(right_char_formatted)
        left_text = fix_encoding(left_text)
        right_text = fix_encoding(right_text)
        
        # Escape special characters in all text
        left_char_formatted = escape_latex_special_chars(left_char_formatted)
        right_char_formatted = escape_latex_special_chars(right_char_formatted)
        left_text = escape_latex_special_chars(left_text)
        right_text = escape_latex_special_chars(right_text)
        
        # Add this dialogue pair
        latex += r"\ParallelLText{%" + "\n"
        latex += r"\charname{" + left_char_formatted + r"}" + "\n"
        latex += left_text.replace("\n", r"\\" + "\n") + "\n"
        latex += "}\n"
        
        latex += r"\ParallelRText{%" + "\n"
        latex += r"\charname{" + right_char_formatted + r"}" + "\n"
        latex += right_text.replace("\n", r"\\" + "\n") + "\n"
        latex += "}\n"
        
        # Add parallel paragraph separator if not the last dialogue
        if i < num_dialogues - 1:
            latex += r"\ParallelPar" + "\n"
    
    # End document
    latex += r"""
\end{Parallel}

\end{document}
"""
    
    return latex

def show_message(stdscr, message, y=None, x=None, wait_for_key=True):
    """Show a message on the screen."""
    height, width = stdscr.getmaxyx()
    
    if y is None:
        y = height // 2
    if x is None:
        x = (width - len(message)) // 2
        
    try:
        stdscr.addstr(y, x, message)
    except curses.error:
        # Handle potential display errors
        pass
    
    stdscr.refresh()
    
    if wait_for_key:
        stdscr.getch()  # Wait for key press

def main(stdscr):
    # Set up colors
    curses.start_color()
    curses.init_pair(1, curses.COLOR_BLUE, curses.COLOR_BLACK)
    curses.init_pair(2, curses.COLOR_GREEN, curses.COLOR_BLACK)
    curses.init_pair(3, curses.COLOR_RED, curses.COLOR_BLACK)
    
    # Hide cursor if possible
    try:
        curses.curs_set(1)  # Make cursor visible but not too distracting
    except:
        pass  # Some terminals don't support cursor visibility
    
    # Enable non-blocking input
    stdscr.nodelay(0)
    
    # Clear screen
    stdscr.clear()
    
    # Get screen dimensions
    height, width = stdscr.getmaxyx()
    
    # Display welcome message
    try:
        stdscr.addstr(0, 0, "Welcome to Parallel Translation Generator", curses.A_BOLD)
        stdscr.addstr(1, 0, "Enter the required information in each text box.")
        stdscr.addstr(2, 0, "Use Ctrl+G to save and continue, Ctrl+C to cancel.")
        stdscr.addstr(3, 0, "Press Ctrl+V to paste text (fixes Windows encoding issues).")
        stdscr.addstr(4, 0, "Supports Spanish: á, é, í, ó, ú, ñ, ¡, ¿")
    except curses.error:
        # Handle potential display errors
        pass
    
    stdscr.refresh()
    
    # Get title
    editor_height = 3
    try:
        stdscr.addstr(6, 0, "Enter the title of your translation:")
    except curses.error:
        pass
    
    stdscr.refresh()
    title_editor = ScrollableTextbox(stdscr, editor_height, width-4, 7, 2, "Title")
    title = title_editor.edit()
    
    # Get author
    stdscr.clear()
    try:
        stdscr.addstr(0, 0, "Enter author information:", curses.A_BOLD)
    except curses.error:
        pass
    
    stdscr.refresh()
    author_editor = ScrollableTextbox(stdscr, editor_height, width-4, 2, 2, "Author")
    author = author_editor.edit()
    
    # Get left (original) text
    stdscr.clear()
    try:
        stdscr.addstr(0, 0, "Enter the 'left' input (original text)", curses.A_BOLD)
        stdscr.addstr(1, 0, "Format: [CharacterName] followed by their dialogue.")
        stdscr.addstr(2, 0, "Example: [Charlie] ¡Nadie podrá negar!")
    except curses.error:
        pass
    
    stdscr.refresh()
    
    # Use almost full screen for the editor
    left_editor_height = height - 10
    left_editor = ScrollableTextbox(stdscr, left_editor_height, width-4, 4, 2, "Original Text")
    left_input = left_editor.edit()
    
    # Get right (translation) text
    stdscr.clear()
    try:
        stdscr.addstr(0, 0, "Enter the 'right' input (translation)", curses.A_BOLD)
        stdscr.addstr(1, 0, "Format: [CharacterName] followed by their dialogue.")
        stdscr.addstr(2, 0, "Use the same character names as in the original text.")
    except curses.error:
        pass
    
    stdscr.refresh()
    right_editor = ScrollableTextbox(stdscr, left_editor_height, width-4, 4, 2, "Translation")
    right_input = right_editor.edit()
    
    # Process the inputs
    stdscr.clear()
    show_message(stdscr, "Processing input...", 0, 0, False)
    
    # Parse the inputs
    left_dialogues = parse_character_dialogue(left_input)
    right_dialogues = parse_character_dialogue(right_input)
    
    # Check if parsing was successful
    if not left_dialogues:
        stdscr.clear()
        show_message(
            stdscr, 
            "Warning: No character dialogue found in the left text! Make sure to use [CharacterName] format.", 
            0, 0
        )
    
    if not right_dialogues:
        stdscr.clear()
        show_message(
            stdscr, 
            "Warning: No character dialogue found in the right text! Make sure to use [CharacterName] format.", 
            2, 0
        )
    
    # Generate LaTeX
    latex_content = generate_latex(title, author, left_dialogues, right_dialogues)
    
    # Determine output filename (sanitize title for filename)
    safe_title = "".join(c if c.isalnum() or c in "._- " else "_" for c in title)
    safe_title = safe_title.replace(" ", "_")
    if not safe_title:
        safe_title = "parallel_translation"
    output_filename = f"{safe_title}_parallel.tex"
    
    # Write to file with UTF-8 encoding explicitly
    try:
        with open(output_filename, "w", encoding="utf-8") as f:
            f.write(latex_content)
            
        # Show success message
        stdscr.clear()
        try:
            stdscr.addstr(0, 0, "LaTeX document created successfully!", curses.A_BOLD | curses.color_pair(2))
            stdscr.addstr(2, 0, f"File: {output_filename}")
            stdscr.addstr(3, 0, "To compile to PDF, run:")
            stdscr.addstr(4, 0, f"  xelatex {output_filename}")
        except curses.error:
            pass
    except Exception as e:
        # Show error message
        stdscr.clear()
        try:
            stdscr.addstr(0, 0, "Error creating file!", curses.A_BOLD | curses.color_pair(3))
            stdscr.addstr(2, 0, f"Error: {str(e)}")
        except curses.error:
            pass
    
    # Statistics
    try:
        stdscr.addstr(6, 0, "Statistics:")
        stdscr.addstr(7, 0, f"Original text: {len(left_dialogues)} character sections")
        stdscr.addstr(8, 0, f"Translation: {len(right_dialogues)} character sections")
        
        if len(left_dialogues) != len(right_dialogues):
            stdscr.addstr(9, 0, "WARNING: Number of character sections doesn't match!", curses.color_pair(3))
            stdscr.addstr(10, 0, "Only the first matching sections were processed.")
        
        stdscr.addstr(12, 0, "Press any key to exit...", curses.A_BOLD)
    except curses.error:
        pass
    
    stdscr.refresh()
    stdscr.getch()

if __name__ == "__main__":
    try:
        # Initialize curses
        curses.initscr()
        # Start the main program
        curses.wrapper(main)
    except KeyboardInterrupt:
        # Clean up curses
        curses.endwin()
        print("\nProgram canceled by user.")
        sys.exit(1)
    except Exception as e:
        # Clean up curses
        curses.endwin()
        print(f"\nAn error occurred: {e}")
        sys.exit(1)