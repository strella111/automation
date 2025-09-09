"""
Keysight E5818A trigger helper (v2, handshake-ready)
-----------------------------------------------------
• Класс управления E5818A по SCPI (VXI-11/LXI) через PyVISA
• Тестовые функции (single, burst, extloop, handshake)
• Обновлённый GUI (Tkinter) с режимом «программное рукопожатие»

Новая логика «рукопожатия»
-------------------------
Задача: первая пачка из N импульсов уходит по команде скрипта (prime), далее каждая
следующая пачка запускается по приходу импульса от PNA на EXT1 (Trigger Out после свипа).
Количество пачек ограничивается параметром «Batches».

Реализация:
  • schedule_alarm_burst(...) — программирует ALARM1 → TTLn на серию.
  • run_handshake_loop(...) — 1) чистит лог EXT; 2) запускает prime-пачку; 3) ждёт EXT-событие;
    4) на каждый валидный EXT планирует новую серию; 5) повторяет, пока не израсходует «Batches».
  • Debounce по EXT (по TAI-метке) — чтобы не реагировать на дребезг/повторы.
  • Disarm надёжно останавливает поток, делает join и очищает ALARM.

Требования:
    pip install pyvisa

Запуск GUI:
    python e5818a_trigger_tool.py --gui

CLI:
    python e5818a_trigger_tool.py --test single  --ip 192.168.1.50
    python e5818a_trigger_tool.py --test burst   --ip 192.168.1.50 --period-us 500 --count 11
    python e5818a_trigger_tool.py --test extloop --ip 192.168.1.50 --runtime 60
    python e5818a_trigger_tool.py --test handshake --ip 192.168.1.50 --period-us 500 --count 11 --batches 20
"""
from __future__ import annotations
import argparse
import threading
import time
from dataclasses import dataclass
from typing import Optional, Dict

try:
    import pyvisa
except Exception as e:  # pragma: no cover
    pyvisa = None
    print("[WARN] PyVISA не установлен. Установите: pip install pyvisa")


# -------------------------- Конфигурация --------------------------
@dataclass
class E5818Config:
    resource: str                  # e.g. "TCPIP0::10.10.61.71::inst0::INSTR"
    ttl_channel: int = 1           # 1..2
    ext_channel: int = 1           # 1..2 (слушаем EXTn)
    start_lead_s: float = 0.02     # задержка старта серии после детекта, сек
    pulse_period_s: float = 0.0005 # период импульсов, сек (>=100e-6)
    pulse_count: int = 11          # число импульсов в серии (N)
    batches: int = 10              # число пачек (серий) в режиме «рукопожатия»
    poll_interval_s: float = 0.002 # шаг опроса лога EXT, сек
    visa_timeout_ms: int = 2000    # VISA timeout
    ext_debounce_s: float = 0.002  # дебаунс EXT, сек (минимальный интервал между событиями)


# -------------------------- Драйвер E5818A --------------------------
class KeysightE5818A:
    """
    Управление Keysight E5818A по SCPI (VXI-11/LXI через PyVISA).
    Реализует:
      • TTLn ← ALARM1 (серии импульсов)
      • EXT лог (таймстампы)
      • Режимы: одиночный импульс, burst, EXT→burst, handshake (prime + EXT)
    """
    def __init__(self, cfg: E5818Config):
        self.cfg = cfg
        self.rm: Optional[pyvisa.ResourceManager] = None
        self.inst: Optional[pyvisa.resources.MessageBasedResource] = None
        self._stop_event: Optional[threading.Event] = None
        self._thread: Optional[threading.Thread] = None
        self._mode: Optional[str] = None  # 'extloop' | 'handshake'

    # ---------- инфраструктура ----------
    def connect(self) -> str:
        if pyvisa is None:
            raise RuntimeError("PyVISA не установлен. Выполните: pip install pyvisa")
        self.rm = pyvisa.ResourceManager()
        self.inst = self.rm.open_resource(self.cfg.resource)
        self.inst.timeout = self.cfg.visa_timeout_ms
        idn = self.query("*IDN?")
        # Сброс статусов и логов
        self.write("*CLS")
        self.write("LOG:STAMp:STATe 1"); self.write("LOG:STAMp:CLEar")
        self.write("LOG:TRIGger:STATe 1"); self.write("LOG:TRIGger:CLEar")
        # Удалить все активные будильники
        self.write("LXI:TRIGger:ALARM:DALL")
        # Настроить TTL→ALARM1 и включить
        self.ensure_ttl_source()
        return idn

    def close(self):
        try:
            self.disarm()  # безопасная остановка потока
            if self.inst is not None:
                try:
                    self.write("LXI:TRIGger:ALARM:DALL")
                except Exception:
                    pass
                self.inst.close()
        finally:
            if self.rm is not None:
                self.rm.close()
        self.rm = None
        self.inst = None

    # ---------- SCPI helpers ----------
    def write(self, cmd: str):
        assert self.inst is not None, "Не подключено"
        print(f'write:::{cmd}')
        self.inst.write(cmd)

    def query(self, cmd: str) -> str:
        assert self.inst is not None, "Не подключено"
        result = self.inst.query(cmd).strip()
        print(f'write:::{cmd}')
        print(f'read:::{result}')
        return result

    # ---------- базовые операции ----------
    def ensure_ttl_source(self):
        """Привязать TTLn к ALARM1 и включить канал TTL."""
        ch = self.cfg.ttl_channel
        self.write(f'TRIG:TTL{ch}:SOUR "ALARM1"')
        self.write(f"TRIG:TTL{ch}:STAT 1")

    def _get_tai(self):
        """Возвращает текущий TAI (LXI time) кортежем (sec:int, frac:float)."""
        t = self.query("LXI:TIME?")
        parts = [p.strip() for p in t.split(",")]
        sec = int(float(parts[0]))
        frac = float(parts[1]) if len(parts) > 1 else 0.0
        return sec, frac

    def schedule_alarm_burst(self, start_in_s: float, period_s: float, count: int):
        """Настраивает ALARM1 на серию импульсов начиная с (now + start_in_s)."""
        if period_s < 0.0001:
            raise ValueError("period_s слишком мал (минимум 100 мкс)")
        if count < 1 or count > 5000:
            raise ValueError("count вне диапазона (1..5000)")
        now_sec, now_frac = self._get_tai()
        start_total = now_sec + now_frac + start_in_s
        start_sec = int(start_total)
        start_frac = start_total - start_sec
        self.write(
            f'LXI:TRIGger:ALARM1:SET:CONFigure 1,{start_sec},{start_frac:.9f},{period_s},{count}'
        )

    # ---------- EXT лог ----------
    def ext_log_count(self) -> int:
        return int(self.query("LOG:STAMp:COUNt?"))

    def pop_ext_event(self) -> Optional[Dict]:
        raw = self.query("LOG:STAMp:DATA?")
        if raw.upper().startswith("NO EVENT"):
            return None
        parts = [p.strip() for p in raw.split(",")]
        # Формат: log_sec,log_frac,ts_sec,ts_frac,source(0/1),slope
        return {
            "log_sec": int(float(parts[0])),
            "log_frac": float(parts[1]),
            "ts_sec": int(float(parts[2])),
            "ts_frac": float(parts[3]),
            "source": int(parts[4]),   # 0=EXT1, 1=EXT2
            "slope": parts[5]
        }

    # ---------- Высокоуровневые сценарии ----------
    def single_pulse(self, lead_s: Optional[float] = None):
        lead = self.cfg.start_lead_s if lead_s is None else lead_s
        self.schedule_alarm_burst(start_in_s=lead, period_s=0.001, count=1)

    def burst(self, count: Optional[int] = None, period_s: Optional[float] = None, lead_s: Optional[float] = None):
        n = self.cfg.pulse_count if count is None else int(count)
        per = self.cfg.pulse_period_s if period_s is None else float(period_s)
        lead = self.cfg.start_lead_s if lead_s is None else float(lead_s)
        self.schedule_alarm_burst(start_in_s=lead, period_s=per, count=n)

    # --------- EXT→Burst (как в v1) ---------
    def run_ext_to_burst_loop(self, stop_event: threading.Event):
        ext_idx = self.cfg.ext_channel - 1
        print("[ARMED] Waiting EXT events → scheduling bursts...")
        while not stop_event.is_set():
            try:
                cnt = self.ext_log_count()
                if cnt > 0:
                    evt = self.pop_ext_event()
                    if not evt:
                        continue
                    if evt["source"] == ext_idx:
                        self.schedule_alarm_burst(
                            start_in_s=self.cfg.start_lead_s,
                            period_s=self.cfg.pulse_period_s,
                            count=self.cfg.pulse_count
                        )
                        print(
                            f"EXT{self.cfg.ext_channel} {evt['slope']} @ {evt['ts_sec']}+{evt['ts_frac']:.6f} -> "
                            f"scheduled {self.cfg.pulse_count} pulses (period {self.cfg.pulse_period_s*1e6:.1f} µs)"
                        )
                time.sleep(self.cfg.poll_interval_s)
            except Exception as e:
                print(f"[ERR] Loop: {e}")
                time.sleep(0.1)
        print("[STOP] EXT→Burst loop stopped.")

    # --------- Handshake: prime + EXT feedback ---------
    def run_handshake_loop(self, stop_event: threading.Event, batches: int, prime_lead_s: Optional[float] = None):
        """Запускает первую пачку по времени, затем batches-1 пачек по EXT событиям."""
        ext_idx = self.cfg.ext_channel - 1
        lead = self.cfg.start_lead_s if prime_lead_s is None else prime_lead_s

        # Сбросить лог EXT перед стартом, чтобы не съесть старые события
        try:
            self.write("LOG:STAMp:CLEar")
        except Exception:
            pass

        remaining = int(batches)
        last_ext_t = None

        print(f"[HS] Prime burst: {self.cfg.pulse_count} @ {self.cfg.pulse_period_s*1e6:.1f} µs, starts in {lead*1e3:.1f} ms")
        # Первая пачка уходит сразу по времени
        self.schedule_alarm_burst(start_in_s=lead, period_s=self.cfg.pulse_period_s, count=self.cfg.pulse_count)
        remaining -= 1

        print(f"[HS] Remaining batches after prime: {remaining}")
        while not stop_event.is_set() and remaining > 0:
            try:
                cnt = self.ext_log_count()
                if cnt > 0:
                    evt = self.pop_ext_event()
                    if not evt:
                        continue
                    if evt["source"] != ext_idx:
                        continue
                    # debounce по времени события (TAI)
                    t_evt = evt["ts_sec"] + evt["ts_frac"]
                    if last_ext_t is not None:
                        if (t_evt - last_ext_t) < max(0.0001, self.cfg.ext_debounce_s):
                            # слишком близко — игнорируем
                            continue
                    last_ext_t = t_evt

                    # Планируем следующую пачку
                    self.schedule_alarm_burst(
                        start_in_s=self.cfg.start_lead_s,
                        period_s=self.cfg.pulse_period_s,
                        count=self.cfg.pulse_count
                    )
                    remaining -= 1
                    print(
                        f"[HS] EXT{self.cfg.ext_channel} {evt['slope']} @ {evt['ts_sec']}+{evt['ts_frac']:.6f} -> "
                        f"scheduled burst; remaining={remaining}"
                    )
                time.sleep(self.cfg.poll_interval_s)
            except Exception as e:
                print(f"[ERR] Handshake: {e}")
                time.sleep(0.1)
        print("[HS] Handshake loop completed or stopped.")

    # ---------- Управление потоками ----------
    def _start_thread(self, target, *args):
        if self._stop_event is not None and not self._stop_event.is_set():
            print("[INFO] Уже работает. Сначала Disarm.")
            return
        self._stop_event = threading.Event()
        self._thread = threading.Thread(target=target, args=(self._stop_event, *args), daemon=True)
        self._thread.start()

    def arm_ext_burst(self):
        self._mode = 'extloop'
        self._start_thread(self.run_ext_to_burst_loop)

    def arm_handshake(self, batches: Optional[int] = None, prime_lead_s: Optional[float] = None):
        self._mode = 'handshake'
        b = self.cfg.batches if batches is None else int(batches)
        self._start_thread(self.run_handshake_loop, b, prime_lead_s)

    def disarm(self):
        if self._stop_event is None:
            return
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=1.5)
        self._stop_event = None
        self._thread = None
        # Остановить активные будильники, чтобы не осталось висящих серий
        try:
            self.write("LXI:TRIGger:ALARM:DALL")
        except Exception:
            pass
        print("[STOP] Disarmed.")


# -------------------------- Тестовые функции (CLI) --------------------------
def test_single(ip: str, lead_ms: float = 20.0):
    cfg = E5818Config(resource=f"TCPIP0::{ip}::inst0::INSTR")
    dev = KeysightE5818A(cfg)
    try:
        print("Connecting…")
        print("IDN:", dev.connect())
        print(f"Shoot single pulse in {lead_ms} ms…")
        dev.single_pulse(lead_s=lead_ms/1000.0)
        print("Done.")
    finally:
        dev.close()


def test_burst(ip: str, period_us: float = 500.0, count: int = 11, lead_ms: float = 20.0):
    cfg = E5818Config(resource=f"TCPIP0::{ip}::inst0::INSTR")
    dev = KeysightE5818A(cfg)
    try:
        print("Connecting…")
        print("IDN:", dev.connect())
        dev.burst(count=count, period_s=period_us/1e6, lead_s=lead_ms/1000.0)
        print(f"Burst scheduled: {count} @ {period_us} µs, starts in {lead_ms} ms")
    finally:
        dev.close()


def test_extloop(ip: str, period_us: float = 500.0, count: int = 11, runtime_s: float = 60.0):
    cfg = E5818Config(
        resource=f"TCPIP0::{ip}::inst0::INSTR",
        pulse_period_s=period_us/1e6,
        pulse_count=count,
    )
    dev = KeysightE5818A(cfg)
    try:
        print("Connecting…")
        print("IDN:", dev.connect())
        print("Arming EXT→Burst loop… (send EXT pulse on E5818A EXT1)")
        dev.arm_ext_burst()
        t0 = time.time()
        while time.time() - t0 < runtime_s:
            time.sleep(0.1)
        print("Disarming…")
        dev.disarm()
    finally:
        dev.close()


def test_handshake(ip: str, period_us: float = 500.0, count: int = 11, batches: int = 10, lead_ms: float = 20.0):
    cfg = E5818Config(
        resource=f"TCPIP0::{ip}::inst0::INSTR",
        pulse_period_s=period_us/1e6,
        pulse_count=count,
        batches=batches,
        start_lead_s=lead_ms/1000.0,
    )
    dev = KeysightE5818A(cfg)
    try:
        print("Connecting…")
        print("IDN:", dev.connect())
        print(f"Arming handshake: N={count} per burst, batches={batches}, period={period_us} µs")
        dev.arm_handshake(batches=batches)
        # Ждём пока поток сам завершится (или Ctrl+C)
        while dev._thread is not None and dev._thread.is_alive():
            time.sleep(0.2)
        print("Handshake finished.")
    finally:
        dev.close()


# -------------------------- GUI (Tkinter) --------------------------
import tkinter as tk
from tkinter import ttk, messagebox

class E5818App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("E5818A Pulse Tool (v2)")
        self.geometry("720x560")  # больше ширина/высота, чтобы кнопки поместились
        self.minsize(700, 520)

        self.dev: Optional[KeysightE5818A] = None

        # Vars
        self.var_ip = tk.StringVar(value="10.10.61.71")
        self.var_ttl = tk.IntVar(value=1)
        self.var_ext = tk.IntVar(value=1)
        self.var_lead_ms = tk.DoubleVar(value=20.0)
        self.var_period_us = tk.DoubleVar(value=500.0)
        self.var_count = tk.IntVar(value=11)
        self.var_batches = tk.IntVar(value=10)
        self.var_debounce_ms = tk.DoubleVar(value=2.0)
        self.var_status = tk.StringVar(value="Готов")

        self._build_ui()

    def _row(self, parent, r, label, widget):
        ttk.Label(parent, text=label).grid(row=r, column=0, sticky=tk.W, padx=6, pady=6)
        widget.grid(row=r, column=1, sticky=tk.EW, padx=6, pady=6)

    def _build_ui(self):
        frm = ttk.Frame(self)
        frm.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)
        frm.columnconfigure(1, weight=1)

        # Параметры подключения и тайминги
        self._row(frm, 0, "E5818A IP:", ttk.Entry(frm, textvariable=self.var_ip))
        self._row(frm, 1, "TTL канал (1..2):", ttk.Spinbox(frm, from_=1, to=2, textvariable=self.var_ttl, width=5))
        self._row(frm, 2, "EXT канал (1..2):", ttk.Spinbox(frm, from_=1, to=2, textvariable=self.var_ext, width=5))
        self._row(frm, 3, "Start lead, ms:", ttk.Entry(frm, textvariable=self.var_lead_ms))
        self._row(frm, 4, "Period, µs:", ttk.Entry(frm, textvariable=self.var_period_us))
        self._row(frm, 5, "Count per burst (N):", ttk.Entry(frm, textvariable=self.var_count))
        self._row(frm, 6, "Batches (серий):", ttk.Entry(frm, textvariable=self.var_batches))
        self._row(frm, 7, "EXT debounce, ms:", ttk.Entry(frm, textvariable=self.var_debounce_ms))

        # Кнопки в две строки
        btns = ttk.Frame(frm)
        btns.grid(row=8, column=0, columnspan=2, pady=(8, 4), sticky=tk.EW)
        for c in range(6):
            btns.columnconfigure(c, weight=1)

        ttk.Button(btns, text="Подключиться", command=self.on_connect).grid(row=0, column=0, padx=4, sticky=tk.EW)
        ttk.Button(btns, text="Отключиться", command=self.on_disconnect).grid(row=0, column=1, padx=4, sticky=tk.EW)
        ttk.Button(btns, text="Одиночный импульс", command=self.on_single).grid(row=0, column=2, padx=4, sticky=tk.EW)
        ttk.Button(btns, text="Пачка (N)", command=self.on_burst).grid(row=0, column=3, padx=4, sticky=tk.EW)
        ttk.Button(btns, text="ARM EXT→Burst", command=self.on_arm_extloop).grid(row=0, column=4, padx=4, sticky=tk.EW)
        ttk.Button(btns, text="Disarm", command=self.on_disarm).grid(row=0, column=5, padx=4, sticky=tk.EW)

        ttk.Button(btns, text="ARM Handshake (prime+EXT)", command=self.on_arm_handshake).grid(row=1, column=0, columnspan=3, padx=4, pady=4, sticky=tk.EW)
        ttk.Button(btns, text="Очистить логи EXT/TTL", command=self.on_clear_logs).grid(row=1, column=3, columnspan=3, padx=4, pady=4, sticky=tk.EW)

        # Status + log
        ttk.Label(frm, textvariable=self.var_status, foreground="#444").grid(row=9, column=0, columnspan=2, sticky=tk.W, padx=6, pady=(6, 2))
        self.txt = tk.Text(frm, height=12, width=80)
        self.txt.grid(row=10, column=0, columnspan=2, sticky=tk.NSEW, padx=6, pady=6)
        frm.rowconfigure(10, weight=1)

        # Bind close
        self.protocol("WM_DELETE_WINDOW", self.on_close)

    # ------------- helpers -------------
    def _make_dev(self) -> KeysightE5818A:
        ip = self.var_ip.get().strip()
        cfg = E5818Config(
            resource=f"TCPIP0::{ip}::inst0::INSTR",
            ttl_channel=int(self.var_ttl.get()),
            ext_channel=int(self.var_ext.get()),
            start_lead_s=float(self.var_lead_ms.get())/1000.0,
            pulse_period_s=float(self.var_period_us.get())/1e6,
            pulse_count=int(self.var_count.get()),
            batches=int(self.var_batches.get()),
            ext_debounce_s=float(self.var_debounce_ms.get())/1000.0,
        )
        return KeysightE5818A(cfg)

    def _log(self, s: str):
        self.txt.insert(tk.END, s + "")
        self.txt.see(tk.END)

    # ------------- actions -------------
    def on_connect(self):
        try:
            if self.dev is not None:
                self._log("[INFO] Уже подключено")
                return
            self.dev = self._make_dev()
            idn = self.dev.connect()
            self.var_status.set(f"Подключено: {idn}")
            self._log("Connected: " + idn)
        except Exception as e:
            messagebox.showerror("Ошибка подключения", str(e))
            self.var_status.set("Ошибка подключения")
            self.dev = None

    def on_disconnect(self):
        try:
            if self.dev is None:
                return
            self.dev.disarm()
            self.dev.close()
            self.dev = None
            self.var_status.set("Отключено")
            self._log("Disconnected")
        except Exception as e:
            messagebox.showerror("Ошибка", str(e))

    def _ensure_connected(self) -> bool:
        if self.dev is None:
            self.on_connect()
        return self.dev is not None

    def on_single(self):
        if not self._ensure_connected():
            return
        try:
            self._pull_cfg()
            self.dev.single_pulse()
            self._log("Single pulse scheduled")
        except Exception as e:
            messagebox.showerror("Ошибка", str(e))

    def on_burst(self):
        if not self._ensure_connected():
            return
        try:
            self._pull_cfg()
            self.dev.burst()
            self._log(
                f"Burst scheduled: {self.dev.cfg.pulse_count} @ {self.dev.cfg.pulse_period_s*1e6:.1f} µs"
            )
        except Exception as e:
            messagebox.showerror("Ошибка", str(e))

    def on_arm_extloop(self):
        if not self._ensure_connected():
            return
        try:
            self._pull_cfg()
            self.dev.arm_ext_burst()
            self.var_status.set("ARMED EXT→Burst (по EXT)")
            self._log("ARM EXT→Burst engaged")
        except Exception as e:
            messagebox.showerror("Ошибка", str(e))

    def on_arm_handshake(self):
        if not self._ensure_connected():
            return
        try:
            self._pull_cfg()
            self.dev.arm_handshake(batches=self.dev.cfg.batches)
            self.var_status.set("ARMED Handshake (prime + EXT)")
            self._log(f"ARM Handshake: batches={self.dev.cfg.batches}")
        except Exception as e:
            messagebox.showerror("Ошибка", str(e))

    def on_disarm(self):
        if self.dev is None:
            return
        self.dev.disarm()
        self.var_status.set("Disarmed")
        self._log("Disarmed")

    def on_clear_logs(self):
        if not self._ensure_connected():
            return
        try:
            self.dev.write("LOG:STAMp:CLEar")
            self.dev.write("LOG:TRIGger:CLEar")
            self._log("Logs cleared (EXT/TTL)")
        except Exception as e:
            messagebox.showerror("Ошибка", str(e))

    def _pull_cfg(self):
        # Обновить параметры из GUI в объект
        self.dev.cfg.ttl_channel = int(self.var_ttl.get())
        self.dev.cfg.ext_channel = int(self.var_ext.get())
        self.dev.cfg.start_lead_s = float(self.var_lead_ms.get())/1000.0
        self.dev.cfg.pulse_period_s = float(self.var_period_us.get())/1e6
        self.dev.cfg.pulse_count = int(self.var_count.get())
        self.dev.cfg.batches = int(self.var_batches.get())
        self.dev.cfg.ext_debounce_s = float(self.var_debounce_ms.get())/1000.0
        # убедимся, что TTL привязан и включён
        self.dev.ensure_ttl_source()

    def on_close(self):
        try:
            if self.dev is not None:
                self.dev.disarm()
                self.dev.close()
        finally:
            self.destroy()


# -------------------------- Entry point --------------------------

def main():
    parser = argparse.ArgumentParser(description="Keysight E5818A trigger helper (v2)")
    parser.add_argument("--gui", action="store_true", help="Запустить графический интерфейс")
    parser.add_argument("--ip", type=str, default="10.10.61.71", help="IP адрес E5818A")
    parser.add_argument("--test", choices=["single", "burst", "extloop", "handshake"], help="Выполнить тест")
    parser.add_argument("--period-us", type=float, default=500.0, help="Период, мкс")
    parser.add_argument("--count", type=int, default=11, help="Число импульсов в пачке")
    parser.add_argument("--batches", type=int, default=10, help="Число пачек (серий) в режиме Handshake")
    parser.add_argument("--lead-ms", type=float, default=20.0, help="Стартовый лаг, мс (prime)")
    parser.add_argument("--runtime", type=float, default=30.0, help="Длительность теста extloop, с")
    args = parser.parse_args()

    if args.gui:
        app = E5818App()
        app.var_ip.set(args.ip)
        app.mainloop()
        return

    if args.test == "single":
        test_single(args.ip, lead_ms=args.lead_ms)
    elif args.test == "burst":
        test_burst(args.ip, period_us=args.period_us, count=args.count, lead_ms=args.lead_ms)
    elif args.test == "extloop":
        test_extloop(args.ip, period_us=args.period_us, count=args.count, runtime_s=args.runtime)
    elif args.test == "handshake":
        test_handshake(args.ip, period_us=args.period_us, count=args.count, batches=args.batches, lead_ms=args.lead_ms)
    else:
        print("Ничего не выбрано. Запустите с --gui или --test …")


if __name__ == "__main__":
    main()
