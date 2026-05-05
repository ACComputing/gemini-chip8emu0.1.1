import tkinter as tk
from tkinter import filedialog
import random
import threading
import time
import os

try:
    import winsound
except ImportError:
    winsound = None

# --- CHIP-8 CPU CORE ---
class Chip8:
    def __init__(self):
        # Standard CHIP-8 fontset
        self.fontset = [
            0xF0, 0x90, 0x90, 0x90, 0xF0, # 0
            0x20, 0x60, 0x20, 0x20, 0x70, # 1
            0xF0, 0x10, 0xF0, 0x80, 0xF0, # 2
            0xF0, 0x10, 0xF0, 0x10, 0xF0, # 3
            0x90, 0x90, 0xF0, 0x10, 0x10, # 4
            0xF0, 0x80, 0xF0, 0x10, 0xF0, # 5
            0xF0, 0x80, 0xF0, 0x90, 0xF0, # 6
            0xF0, 0x10, 0x20, 0x40, 0x40, # 7
            0xF0, 0x90, 0xF0, 0x90, 0xF0, # 8
            0xF0, 0x90, 0xF0, 0x10, 0xF0, # 9
            0xF0, 0x90, 0xF0, 0x90, 0x90, # A
            0xE0, 0x90, 0xE0, 0x90, 0xE0, # B
            0xF0, 0x80, 0x80, 0x80, 0xF0, # C
            0xE0, 0x90, 0x90, 0x90, 0xE0, # D
            0xF0, 0x80, 0xF0, 0x80, 0xF0, # E
            0xF0, 0x80, 0xF0, 0x80, 0x80  # F
        ]
        self.reset()

    def reset(self):
        self.memory = bytearray(4096)
        self.V = bytearray(16)
        self.I = 0
        self.pc = 0x200
        self.gfx = [0] * (64 * 32)
        self.delay_timer = 0
        self.sound_timer = 0
        self.stack = []
        self.keys = [False] * 16
        self.draw_flag = False
        self.halted = False
        self.load_fontset()

    def load_fontset(self):
        for i in range(80):
            self.memory[i] = self.fontset[i]

    def load_rom(self, data):
        self.reset()
        for i, byte in enumerate(data):
            if 0x200 + i < 4096:
                self.memory[0x200 + i] = byte

    def emulate_cycle(self):
        if self.halted:
            return
        if self.pc < 0 or self.pc + 1 >= len(self.memory):
            self.halted = True
            return

        # Fetch Opcode (2 bytes)
        opcode = (self.memory[self.pc] << 8) | self.memory[self.pc + 1]
        self.pc += 2

        # Decode & Execute
        x = (opcode & 0x0F00) >> 8
        y = (opcode & 0x00F0) >> 4
        nn = opcode & 0x00FF
        nnn = opcode & 0x0FFF
        
        first = opcode >> 12

        if first == 0x0:
            if opcode == 0x00E0: # Clear screen
                self.gfx = [0] * (64 * 32)
                self.draw_flag = True
            elif opcode == 0x00EE: # Return
                if self.stack:
                    self.pc = self.stack.pop()
                else:
                    self.halted = True
        elif first == 0x1: # Jump
            self.pc = nnn
        elif first == 0x2: # Call
            self.stack.append(self.pc)
            self.pc = nnn
        elif first == 0x3: # Skip if VX == NN
            if self.V[x] == nn: self.pc += 2
        elif first == 0x4: # Skip if VX != NN
            if self.V[x] != nn: self.pc += 2
        elif first == 0x5: # Skip if VX == VY
            if self.V[x] == self.V[y]: self.pc += 2
        elif first == 0x6: # Set VX = NN
            self.V[x] = nn
        elif first == 0x7: # Add NN to VX
            self.V[x] = (self.V[x] + nn) & 0xFF
        elif first == 0x8: # Arithmetic
            last = opcode & 0x000F
            if last == 0x0: self.V[x] = self.V[y]
            elif last == 0x1: self.V[x] |= self.V[y]
            elif last == 0x2: self.V[x] &= self.V[y]
            elif last == 0x3: self.V[x] ^= self.V[y]
            elif last == 0x4:
                res = self.V[x] + self.V[y]
                self.V[0xF] = 1 if res > 0xFF else 0
                self.V[x] = res & 0xFF
            elif last == 0x5:
                self.V[0xF] = 1 if self.V[x] > self.V[y] else 0
                self.V[x] = (self.V[x] - self.V[y]) & 0xFF
            elif last == 0x6:
                self.V[0xF] = self.V[x] & 0x1
                self.V[x] >>= 1
            elif last == 0x7:
                self.V[0xF] = 1 if self.V[y] > self.V[x] else 0
                self.V[x] = (self.V[y] - self.V[x]) & 0xFF
            elif last == 0xE:
                self.V[0xF] = (self.V[x] & 0x80) >> 7
                self.V[x] = (self.V[x] << 1) & 0xFF
        elif first == 0x9: # Skip if VX != VY
            if self.V[x] != self.V[y]: self.pc += 2
        elif first == 0xA: # Set I
            self.I = nnn
        elif first == 0xB: # Jump to V0 + NNN
            self.pc = nnn + self.V[0]
        elif first == 0xC: # Random
            self.V[x] = random.randint(0, 255) & nn
        elif first == 0xD: # Draw Sprite
            vx = self.V[x] % 64
            vy = self.V[y] % 32
            h = opcode & 0x000F
            self.V[0xF] = 0
            
            for row in range(h):
                addr = self.I + row
                if addr >= len(self.memory):
                    break
                sprite_byte = self.memory[addr]
                for col in range(8):
                    if (sprite_byte & (0x80 >> col)):
                        px = vx + col
                        py = vy + row
                        if px < 64 and py < 32: # Clipping
                            idx = px + (py * 64)
                            if self.gfx[idx] == 1:
                                self.V[0xF] = 1
                            self.gfx[idx] ^= 1
            self.draw_flag = True
        elif first == 0xE: # Keyboard skips
            if (opcode & 0x00FF) == 0x9E:
                key_idx = self.V[x] & 0xF
                if self.keys[key_idx]: self.pc += 2
            elif (opcode & 0x00FF) == 0xA1:
                key_idx = self.V[x] & 0xF
                if not self.keys[key_idx]: self.pc += 2
        elif first == 0xF: # Timers, Memory, I
            last = opcode & 0x00FF
            if last == 0x07: self.V[x] = self.delay_timer
            elif last == 0x0A:
                pressed = False
                for i, k in enumerate(self.keys):
                    if k:
                        self.V[x] = i
                        pressed = True
                        break
                if not pressed: self.pc -= 2 # Wait for keypress
            elif last == 0x15: self.delay_timer = self.V[x]
            elif last == 0x18: self.sound_timer = self.V[x]
            elif last == 0x1E: self.I = (self.I + self.V[x]) & 0xFFFF
            elif last == 0x29: self.I = self.V[x] * 5
            elif last == 0x33:
                if self.I + 2 < len(self.memory):
                    self.memory[self.I] = self.V[x] // 100
                    self.memory[self.I + 1] = (self.V[x] // 10) % 10
                    self.memory[self.I + 2] = self.V[x] % 10
            elif last == 0x55:
                for i in range(x + 1):
                    addr = self.I + i
                    if addr < len(self.memory):
                        self.memory[addr] = self.V[i]
            elif last == 0x65:
                for i in range(x + 1):
                    addr = self.I + i
                    if addr < len(self.memory):
                        self.V[i] = self.memory[addr]

    def update_timers(self):
        if self.delay_timer > 0: self.delay_timer -= 1
        if self.sound_timer > 0: self.sound_timer -= 1

# --- GUI / FRONTEND ---
class Chip8EmulatorGUI:
    def __init__(self, root):
        self.root = root
        self.base_title = "AC's Chip-8 Engine 0.1 - Team Flames"
        self.root.title(self.base_title)
        self.root.resizable(False, False)
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)
        
        self.cpu = Chip8()
        self.running = True
        self.paused = False
        self.cycles_per_frame = 10
        self.pixel_on_color = "#00BFFF"
        self.beep_enabled = True
        self.beep_var = tk.BooleanVar(value=True)
        self.last_beep_time = 0.0
        self.frames_drawn = 0
        self.last_fps_time = time.time()
        self.current_fps = 0
        
        # Scaling factor for the 64x32 display
        self.scale = 12 
        
        # KEY MAPPING (Standard CHIP-8 layout mapped to QWERTY)
        # 1 2 3 C  =>  1 2 3 4
        # 4 5 6 D  =>  Q W E R
        # 7 8 9 E  =>  A S D F
        # A 0 B F  =>  Z X C V
        self.keymap = {
            '1': 0x1, '2': 0x2, '3': 0x3, '4': 0xC,
            'q': 0x4, 'w': 0x5, 'e': 0x6, 'r': 0xD,
            'a': 0x7, 's': 0x8, 'd': 0x9, 'f': 0xE,
            'z': 0xA, 'x': 0x0, 'c': 0xB, 'v': 0xF
        }

        self.setup_ui()
        self.setup_events()
        
        # Start blank; user can load a ROM from File -> Load ROM...
        self.current_rom_name = "No ROM Loaded"
        self.update_title()

        # Start Emulation Threads
        self.cpu_thread = threading.Thread(target=self.emulation_loop, daemon=True)
        self.cpu_thread.start()
        
        # Start GUI draw loop
        self.update_screen()

    def setup_ui(self):
        # mGBA style menu bar
        menubar = tk.Menu(self.root)
        
        filemenu = tk.Menu(menubar, tearoff=0)
        filemenu.add_command(label="Load ROM...", command=self.open_rom)
        filemenu.add_separator()
        filemenu.add_command(label="Exit", command=self.root.quit)
        menubar.add_cascade(label="File", menu=filemenu)
        
        emumenu = tk.Menu(menubar, tearoff=0)
        emumenu.add_command(label="Pause/Resume", command=self.toggle_pause)
        emumenu.add_command(label="Reset", command=self.reset_emu)
        emumenu.add_separator()
        emumenu.add_command(label="Speed -", command=self.decrease_speed)
        emumenu.add_command(label="Speed +", command=self.increase_speed)
        emumenu.add_checkbutton(label="Beep Enabled", variable=self.beep_var, command=self.toggle_beep)
        menubar.add_cascade(label="Emulation", menu=emumenu)

        viewmenu = tk.Menu(menubar, tearoff=0)
        viewmenu.add_command(label="Neon Blue Pixels", command=lambda: self.set_pixel_color("#00BFFF"))
        viewmenu.add_command(label="GameBoy Pixels", command=lambda: self.set_pixel_color("#9bbc0f"))
        viewmenu.add_command(label="Classic Green Pixels", command=lambda: self.set_pixel_color("#00FF00"))
        menubar.add_cascade(label="View", menu=viewmenu)
        
        self.root.config(menu=menubar)

        # Toolbar (Per User Request: Black background, Blue text)
        toolbar = tk.Frame(self.root, bg="#222222", bd=1, relief=tk.RAISED)
        toolbar.pack(side=tk.TOP, fill=tk.X)
        
        # Styling dictionary for buttons
        btn_style = {
            'bg': 'black', 
            'fg': '#00BFFF', # Bright blue 
            'activebackground': '#111111', 
            'activeforeground': 'cyan',
            'font': ('Courier', 10, 'bold'),
            'relief': tk.FLAT,
            'padx': 10
        }

        btn_load = tk.Button(toolbar, text="LOAD ROM", command=self.open_rom, **btn_style)
        btn_load.pack(side=tk.LEFT, padx=2, pady=2)
        
        self.btn_pause = tk.Button(toolbar, text="PAUSE", command=self.toggle_pause, **btn_style)
        self.btn_pause.pack(side=tk.LEFT, padx=2, pady=2)

        btn_reset = tk.Button(toolbar, text="RESET", command=self.reset_emu, **btn_style)
        btn_reset.pack(side=tk.LEFT, padx=2, pady=2)

        self.speed_label = tk.Label(
            toolbar,
            text=f"SPEED: {self.cycles_per_frame}",
            bg="#222222",
            fg="#00BFFF",
            font=("Courier", 10, "bold"),
        )
        self.speed_label.pack(side=tk.LEFT, padx=10)

        # Main Display Canvas
        self.canvas = tk.Canvas(self.root, width=64*self.scale, height=32*self.scale, bg="black", highlightthickness=0)
        self.canvas.pack(padx=10, pady=10)

        self.status_label = tk.Label(
            self.root,
            text="FPS: 0 | ROM: No ROM Loaded",
            bg="#111111",
            fg="#00BFFF",
            font=("Courier", 10, "bold"),
            anchor="w",
        )
        self.status_label.pack(fill=tk.X, padx=10, pady=(0, 8))

        # Pre-create rectangles for fast drawing
        self.rects = {}
        for y in range(32):
            for x in range(64):
                x1 = x * self.scale
                y1 = y * self.scale
                x2 = x1 + self.scale
                y2 = y1 + self.scale
                self.rects[(x, y)] = self.canvas.create_rectangle(x1, y1, x2, y2, fill="black", outline="")

    def setup_events(self):
        self.root.bind("<KeyPress>", self.key_down)
        self.root.bind("<KeyRelease>", self.key_up)

    def key_down(self, event):
        key = event.keysym.lower()
        if key in self.keymap:
            self.cpu.keys[self.keymap[key]] = True

    def key_up(self, event):
        key = event.keysym.lower()
        if key in self.keymap:
            self.cpu.keys[self.keymap[key]] = False

    def toggle_pause(self):
        self.paused = not self.paused
        self.btn_pause.config(text="RESUME" if self.paused else "PAUSE")

    def reset_emu(self):
        self.cpu.reset()
        self.paused = False
        self.btn_pause.config(text="PAUSE")
        self.current_rom_name = "No ROM Loaded"
        self.update_title()

    def open_rom(self):
        filepath = filedialog.askopenfilename(title="Select CHIP-8 ROM", filetypes=[("CHIP-8 ROMs", "*.ch8 *.rom"), ("All Files", "*.*")])
        if filepath:
            try:
                with open(filepath, 'rb') as f:
                    rom_data = f.read()
                self.cpu.load_rom(rom_data)
                self.paused = False
                self.btn_pause.config(text="PAUSE")
                self.current_rom_name = os.path.basename(filepath)
                self.update_title()
            except Exception as e:
                print(f"Error loading ROM: {e}")

    def increase_speed(self):
        if self.cycles_per_frame < 20:
            self.cycles_per_frame += 1
            self.speed_label.config(text=f"SPEED: {self.cycles_per_frame}")

    def decrease_speed(self):
        if self.cycles_per_frame > 1:
            self.cycles_per_frame -= 1
            self.speed_label.config(text=f"SPEED: {self.cycles_per_frame}")

    def toggle_beep(self):
        self.beep_enabled = bool(self.beep_var.get())

    def set_pixel_color(self, color):
        self.pixel_on_color = color

    def update_title(self):
        self.root.title(f"{self.base_title} - {self.current_rom_name}")

    def maybe_beep(self):
        if not self.beep_enabled or self.cpu.sound_timer <= 0:
            return
        now = time.time()
        if now - self.last_beep_time < 0.08:
            return
        self.last_beep_time = now
        if winsound:
            try:
                winsound.Beep(880, 40)
            except RuntimeError:
                pass
        else:
            try:
                self.root.bell()
            except tk.TclError:
                pass

    def on_close(self):
        self.running = False
        self.root.destroy()

    def emulation_loop(self):
        """Runs in a background thread to maintain CPU speed independent of Tkinter"""
        while self.running:
            if not self.paused:
                for _ in range(self.cycles_per_frame):
                    self.cpu.emulate_cycle()
                
                self.cpu.update_timers()
            
            # Sleep roughly 1/60th of a second to match 60Hz timers
            time.sleep(1/60)

    def update_screen(self):
        self.maybe_beep()
        if self.cpu.draw_flag:
            # Update canvas rectangles
            for y in range(32):
                for x in range(64):
                    idx = x + (y * 64)
                    color = self.pixel_on_color if self.cpu.gfx[idx] else "black"
                    self.canvas.itemconfig(self.rects[(x, y)], fill=color)
            self.cpu.draw_flag = False

        self.frames_drawn += 1
        now = time.time()
        if now - self.last_fps_time >= 1.0:
            self.current_fps = self.frames_drawn
            self.frames_drawn = 0
            self.last_fps_time = now
            self.status_label.config(
                text=f"FPS: {self.current_fps} | SPEED: {self.cycles_per_frame} | ROM: {self.current_rom_name}"
            )
            
        # Call this function again on the Tkinter main thread
        self.root.after(16, self.update_screen)

if __name__ == "__main__":
    root = tk.Tk()
    app = Chip8EmulatorGUI(root)
    root.mainloop()
