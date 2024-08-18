import tkinter as tk
import obd
import asyncio
import concurrent.futures
import queue
import logging
import time

logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')

class DigitalGauge(tk.Canvas):
    def __init__(self, master, width, height, max_value, label, unit="", **kwargs):
        super().__init__(master, width=width, height=height, bg='black', highlightthickness=0, **kwargs)
        self.width = width
        self.height = height
        self.max_value = max_value
        self.label = label
        self.unit = unit
        self.value = 0
        self.segments = 20
        self.segment_width = self.width // (self.segments + 2)
        self.segment_height = self.height - 40
        self.color = 'red'
        self.active = True
        self.draw()

    def set_value(self, value):
        self.value = min(value, self.max_value)
        self.active = True
        self.draw()

    def set_inactive(self):
        self.active = False
        self.draw()

    def set_color(self, color):
        self.color = color
        self.draw()

    def draw(self):
        self.delete("all")
        self.create_text(self.width // 2, 5, text=self.label, fill=self.color, font=('Arial', 12, 'bold'), anchor='n')
        
        for i in range(self.segments):
            x = i * self.segment_width
            y = 25
            if self.active:
                color = self.color if i < int(self.value * self.segments / self.max_value) else self.color_dim()
            else:
                color = self.color_dim()
            self.create_rectangle(x, y, x + self.segment_width - 1, y + self.segment_height,
                                  fill=color, outline='')

        for i in range(5):
            x = (i * (self.segments // 4)) * self.segment_width
            self.create_line(x, 25, x, 25 + self.segment_height, fill=self.color)
            
        if self.active:
            value_text = f"{self.value:.1f} {self.unit}"
        else:
            value_text = "N/A"
        self.create_text(self.width // 2, self.height - 5, text=value_text, 
                         fill=self.color, font=('Digital-7', 14), anchor='s')

    def color_dim(self):
        return '#300000' if self.color == 'red' else '#303030'

class AsyncRetroDashboard(tk.Frame):
    def __init__(self, master, **kwargs):
        super().__init__(master, bg='black', **kwargs)
        self.gauges = {}
        self.update_queue = queue.Queue()
        self.color = 'red'
        self.connection = None
        self.running = True
        
        gauge_configs = [
            ('INTAKE_TEMP', 'Intake Temp', 100, '°C'),
            ('OIL_TEMP', 'Oil Temp', 150, '°C'),
            ('COOLANT_TEMP', 'Coolant Temp', 120, '°C'),
            ('RPM', 'RPM', 8000, 'rpm'),
            ('SPEED', 'Speed', 200, 'mph'),
            ('ENGINE_LOAD', 'Engine Load', 100, '%'),
            ('FUEL_LEVEL', 'Fuel Level', 100, '%'),
            ('SHORT_FUEL_TRIM_1', 'Short Fuel Trim', 100, '%'),
            ('THROTTLE_POS', 'Throttle Pos', 100, '%'),
            ('MAF', 'MAF', 300, 'g/s'),
            ('BAROMETRIC_PRESSURE', 'Baro Pressure', 200, 'kPa'),
            ('AMBIANT_AIR_TEMP', 'Ambient Temp', 50, '°C')
        ]

        for i, (key, label, max_value, unit) in enumerate(gauge_configs):
            self.gauges[key] = DigitalGauge(self, width=310, height=110, max_value=max_value, label=label, unit=unit)
            row, col = divmod(i, 4)
            self.gauges[key].grid(row=row, column=col, padx=5, pady=5)

        self.status_var = tk.StringVar(value="INITIALIZING...")
        self.status_label = tk.Label(self, textvariable=self.status_var, font=('Arial', 10), fg='red', bg='black')
        self.status_label.grid(row=3, column=0, columnspan=4, sticky='w', pady=5)

        self.dtc_var = tk.StringVar(value="")
        self.dtc_label = tk.Label(self, textvariable=self.dtc_var, font=('Arial', 12, 'bold'), fg='yellow', bg='black')
        self.dtc_label.grid(row=4, column=0, columnspan=4, sticky='we', pady=5)

        self.master.bind('<Button-1>', self.toggle_color)

        # Start the asyncio event loop in a separate thread
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
        self.executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)
        self.executor.submit(self.run_async_loop)

        self.master.after(100, self.process_updates)

    def run_async_loop(self):
        self.loop.run_until_complete(self.main_async_loop())

    async def main_async_loop(self):
        while self.running:
            if not self.connection:
                await self.connect_obd()
                if not self.connection:
                    await asyncio.sleep(5)
                    continue

            await self.update_gauges()
            await self.check_dtc()
            await asyncio.sleep(0.1)

    async def connect_obd(self):
        try:
            self.connection = await self.loop.run_in_executor(None, obd.OBD)
            self.status_var.set("CONNECTED")
            logging.info("Successfully connected to OBD device")
        except Exception as e:
            self.status_var.set("CONNECTION FAILED")
            logging.error(f"Failed to connect to OBD device: {e}")
            self.connection = None

    async def update_gauges(self):
        commands = {
            "INTAKE_TEMP": obd.commands.INTAKE_TEMP,
            "OIL_TEMP": obd.commands.OIL_TEMP,
            "COOLANT_TEMP": obd.commands.COOLANT_TEMP,
            "RPM": obd.commands.RPM,
            "SPEED": obd.commands.SPEED,
            "ENGINE_LOAD": obd.commands.ENGINE_LOAD,
            "FUEL_LEVEL": obd.commands.FUEL_LEVEL,
            "SHORT_FUEL_TRIM_1": obd.commands.SHORT_FUEL_TRIM_1,
            "THROTTLE_POS": obd.commands.THROTTLE_POS,
            "MAF": obd.commands.MAF,
            "BAROMETRIC_PRESSURE": obd.commands.BAROMETRIC_PRESSURE,
            "AMBIANT_AIR_TEMP": obd.commands.AMBIANT_AIR_TEMP
        }
        
        for name, command in commands.items():
            try:
                response = await self.loop.run_in_executor(None, self.connection.query, command)
                if not response.is_null():
                    value = response.value.magnitude
                    if name == "SPEED":
                        value = value * 0.621371
                    self.update_queue.put(("gauge", (name, value, True)))
                    logging.debug(f"Updated {name}: {value}")
                else:
                    self.update_queue.put(("gauge", (name, 0, False)))
                    logging.debug(f"Null response for {name}")
            except Exception as e:
                self.update_queue.put(("gauge", (name, 0, False)))
                logging.error(f"Exception when querying {name}: {e}")

    async def check_dtc(self):
        try:
            dtc_codes = await self.loop.run_in_executor(None, self.connection.query, obd.commands.GET_DTC)
            if dtc_codes.value:
                self.update_queue.put(("dtc", dtc_codes.value))
                logging.info(f"DTC codes found: {dtc_codes.value}")
            else:
                self.update_queue.put(("dtc", None))
        except Exception as e:
            logging.error(f"Exception when querying DTC codes: {e}")

    def process_updates(self):
        try:
            while True:
                item_type, item_value = self.update_queue.get_nowait()
                if item_type == "gauge":
                    name, value, active = item_value
                    if active:
                        self.gauges[name].set_value(value)
                    else:
                        self.gauges[name].set_inactive()
                elif item_type == "dtc":
                    if item_value:
                        dtc_string = " | ".join([f"{code[0]}: {code[1]}" for code in item_value])
                        self.dtc_var.set(dtc_string)
                    else:
                        self.dtc_var.set("")
        except queue.Empty:
            pass
        self.master.after(10, self.process_updates)

    def toggle_color(self, event):
        self.color = 'white' if self.color == 'red' else 'red'
        for gauge in self.gauges.values():
            gauge.set_color(self.color)
        self.status_label.config(fg=self.color)
        self.dtc_label.config(fg='yellow')

    def stop(self):
        self.running = False
        if self.connection:
            self.connection.close()
        self.loop.call_soon_threadsafe(self.loop.stop)
        self.executor.shutdown(wait=False)

def exit_app(root):
    if hasattr(root, 'dashboard'):
        root.dashboard.stop()
    root.quit()
    root.destroy()

def main():
    root = tk.Tk()
    root.title("Async OBD Monitor")
    root.geometry("1280x400")
    root.configure(bg='black')
    root.attributes('-fullscreen', True)
    
    root.config(cursor="none")
    
    dashboard = AsyncRetroDashboard(root)
    root.dashboard = dashboard
    dashboard.pack(expand=True, fill='both')
    
    root.bind('<Control-c>', lambda e: exit_app(root))
    
    root.mainloop()

if __name__ == "__main__":
    main()
