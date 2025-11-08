"""
Minimal E5818A controller class
---------------------------------------------------
Покрывает:
  • подключение/инициализация/первичная настройка
  • одиночный импульс
  • пачка импульсов с заданным периодом
  • обработка внешнего триггера с EXT1 (SW-handshake: проверка подлинности + дебаунс)
  • обработка ошибок (очередь ошибок SCPI), безопасное планирование ALARM «в будущее»
  • очистка логов EXT/TTL (ручная и автоматическая)
  • disarm (снятие активных ALARM)

Зависимость:
    pip install pyvisa

Примечания:
- Время в приборе — TAI из LXI. ALARM должен стартовать строго в будущем.
  Метод _schedule_alarm_burst_guarded автоматически «подтолкнёт» старт к now+guard,
  если рассчитанное время оказалось в прошлом (чтобы не ловить Alarm time invalid).
- Лог EXT читается через LOG:STAMp:DATA? — это FIFO: каждая запись читается и удаляется.
- Для устойчивости к различным версиям прошивки предусмотрены небольшие «алиасы»
  команд (COUN?/COUNt?, LXI:TIME?/LXI:TIME:VAL?).
- Логи автоматически очищаются каждые N операций (по умолчанию 100), чтобы предотвратить
  переполнение и таймауты. Интервал настраивается через E5818Config.log_clear_interval.
"""

from __future__ import annotations
from dataclasses import dataclass
from typing import Optional, Callable, Dict
from utils.logger import format_device_log
from loguru import logger

try:
    import pyvisa
except Exception as e:  # pragma: no cover
    pyvisa = None


# -------------------- Exceptions --------------------

class E5818Error(Exception):
    """Базовая ошибка драйвера E5818A."""


class E5818NotConnected(E5818Error):
    """Попытка операции без подключения."""


class E5818Timeout(E5818Error):
    """Таймаут ожидания события/операции."""


# -------------------- Config --------------------

@dataclass
class E5818Config:
    resource: str                        # "TCPIP0::<ip>::inst0::INSTR" или "TEST" для тестового режима
    ttl_channel: int = 1                 # TTL1..2
    ext_channel: int = 1                 # EXT1..2 (0=EXT1, 1=EXT2 внутри лога)
    visa_timeout_ms: int = 2000
    start_lead_s: float = 0.010          # задержка старта серии (см. README предыдущих сообщений)
    pulse_period_s: float = 0.0005       # >= 100e-6
    min_alarm_guard_s: float = 0.0015    # «микро-буфер» если рассчитанное время старта уже прошло
    ext_debounce_s: float = 0.0010       # софт-дебаунс EXT (минимальный интервал между валидными событиями)
    log_clear_interval: int = 100        # Очищать логи каждые N операций (для предотвращения переполнения)
    logger: Optional[Callable[[str], None]] = None  # опциональный логгер (print-совместимый коллбек)


# -------------------- Driver --------------------

class E5818:
    """
    Класс управления Keysight E5818A (SCPI/VXI-11 по LAN) — минимальный, для встраивания.
    """

    def __init__(self, cfg: E5818Config):
        self.cfg = cfg
        self.rm: Optional["pyvisa.ResourceManager"] = None
        self.connection: Optional["pyvisa.resources.MessageBasedResource"] = None
        self._last_ext_ts: Optional[float] = None   # для SW-дебаунса EXT
        self._idn: Optional[str] = None
        self._operation_counter: int = 0  # Счетчик операций для периодической очистки логов
        self.test_mode = (cfg.resource == "TEST")  # Флаг тестового режима

    # -------- infra --------
    def connect(self) -> str:
        """Открыть VISA ресурс, базовая инициализация, включение логов, TTL→ALARM1."""
        if self.test_mode:
            # Тестовый режим
            self._idn = "TEST MODE: E5818A Simulation"
            self.connection = True  # Заглушка для проверки подключения
            self._log(f"[ЗАГЛУШКА] Подключение к устройству синхронизации E5818")
            return self._idn
        
        if pyvisa is None:
            raise E5818Error("PyVISA не установлен. Установите: pip install pyvisa")

        self.rm = pyvisa.ResourceManager()
        self.connection = self.rm.open_resource(self.cfg.resource)
        self.connection.timeout = self.cfg.visa_timeout_ms

        self._idn = self.query("*IDN?")
        self._log(f"Connected: {self._idn}")

        # Базовая очистка/инициализация
        self.write("*CLS")
        self._enable_and_clear_logs()
        self._drop_all_alarms()
        self._bind_ttl_to_alarm1()
        return self._idn

    def close(self):
        """Закрыть соединение (без исключений)."""
        try:
            self.disarm()
        except Exception:
            pass
        try:
            if self.connection is not None:
                try:
                    self._drop_all_alarms()
                except Exception:
                    pass
                self.connection.close()
        finally:
            if self.rm is not None:
                self.rm.close()
        self.connection = None
        self.rm = None
        self._log("Closed connection")

    # context manager
    def __enter__(self):
        self.connect()
        return self

    def __exit__(self, et, ev, tb):
        self.close()

    # -------- SCPI helpers --------
    def write(self, cmd: str):
        if self.connection is None:
            logger.error('Не обнаружено подключение к LXI при попытке отправки данных')
            raise E5818NotConnected("Нет активного подключения")
        if self.test_mode:
            logger.debug(format_device_log('LXI [TEST]', '>>', cmd))
            return
        logger.debug(format_device_log('LXI', '>>', cmd))
        self.connection.write(cmd)

    def query(self, cmd: str) -> str:
        if self.connection is None:
            logger.error('Не обнаружено подключение к LXI при попытке отправки данных')
            raise E5818NotConnected("Нет активного подключения")
        if self.test_mode:
            logger.debug(format_device_log('LXI [TEST]', '>>', cmd))
            # Возвращаем заглушки для разных команд
            if "*IDN?" in cmd:
                result = "TEST MODE: E5818A Simulation"
            elif "SYST:ERR" in cmd:
                result = "0,No Error"
            elif "LOG:STAMp:DATA?" in cmd:
                result = "NO EVENTS"
            else:
                result = "OK"
            logger.debug(format_device_log('LXI [TEST]', '<<', result))
            return result
        logger.debug(format_device_log('LXI', '>>', cmd))
        result = self.connection.query(cmd).strip()
        logger.debug(format_device_log('LXI', '<<', result))
        return result

    def check_error_queue(self) -> Optional[str]:
        """
        Считывает одну ошибку из очереди ошибок SCPI (если есть).
        Возвращает None, если ошибок нет. Возможные мнемоники: SYST:ERR?, SYSTEM:ERROR?
        """
        for q in ("SYST:ERR?", "SYST:ERRor?"):
            try:
                resp = self.query(q)
                # Ожидаемый формат: "0,No error" или "-200,"...
                if not resp:
                    continue
                code_str = resp.split(",", 1)[0].strip()
                try:
                    code = int(code_str)
                except Exception:
                    code = 0 if "no error" in resp.lower() else -1
                if code == 0:
                    return None
                return resp
            except Exception:
                continue
        return None

    # -------- Basic setup helpers --------
    def _enable_and_clear_logs(self):
        # Включить и очистить логи EXT/TTL
        for cmd in ("LOG:STAMp:STAT 1", "LOG:STAMp:CLE",
                    "LOG:TRIG:STAT 1", "LOG:TRIG:CLE"):
            try:
                self.write(cmd)
            except Exception:
                pass

    def _drop_all_alarms(self):
        try:
            self.write("LXI:TRIG:ALARM:DALL")
        except Exception:
            pass

    def _bind_ttl_to_alarm1(self):
        """Связать выбранный TTLn с ALARM1 и включить TTL."""
        ch = self.cfg.ttl_channel
        self.write(f'TRIG:TTL{ch}:SOUR "ALARM1"')
        self.write(f"TRIG:TTL{ch}:STAT 1")

    # -------- Time helpers --------
    def _get_tai(self) -> float:
        """Возвращает текущее TAI (сек, дробная часть) как float секунды."""
        t = self.query("LXI:TIME?")
        parts = [p.strip() for p in t.split(",")]
        sec = int(float(parts[0]))
        frac = float(parts[1]) if len(parts) > 1 else 0.0
        return sec, frac

    # -------- Alarm scheduling (robust) --------
    def _schedule_alarm_burst_guarded(self, start_in_s: float, period_s: float, count: int):
        """
        Поставить ALARM1 со стартом через start_in_s, защитив от «время уже прошло».
        Если целевое время не будущее — сдвигаем на now + min_alarm_guard_s.
        """
        if period_s < 0.0001:
            raise E5818Error("period_s слишком мал (минимум 100 мкс)")
        if not (1 <= count <= 5000):
            raise E5818Error("count вне диапазона (1..5000)")

        now = self._get_tai()
        desired = now + start_in_s
        if desired <= now + 1e-6:
            desired = now + max(self.cfg.min_alarm_guard_s, 0.0015)

        start_sec = int(desired)
        start_frac = desired - start_sec

        # Программируем и включаем
        self._bind_ttl_to_alarm1()
        self.write(f"LXI:TRIG:ALARM1:SET:PER {period_s}")
        self.write(f"LXI:TRIG:ALARM1:SET:COUN {count}")
        self.write(f"LXI:TRIG:ALARM1:SET:CONF 1,{start_sec},{start_frac:.9f},{period_s},{count}")

        err = self.check_error_queue()
        if err:
            raise E5818Error(f"SCPI error after ALARM schedule: {err}")

    # ------------------ Public API ------------------

    # Primary housekeeping
    def clear_logs(self):
        """Очистить логи EXT/TTL (начать «с чистого листа»)."""
        self._enable_and_clear_logs()
        self._last_ext_ts = None
        self._operation_counter = 0  # Сбрасываем счетчик при ручной очистке
        self._log("Logs cleared")
    
    def _auto_clear_logs_if_needed(self):
        """Автоматическая очистка логов при достижении порога операций."""
        self._operation_counter += 1
        if self._operation_counter >= self.cfg.log_clear_interval:
            try:
                self._enable_and_clear_logs()
                self._operation_counter = 0
                self._log(f"Auto-cleared logs after {self.cfg.log_clear_interval} operations")
            except Exception as e:
                logger.warning(f"Не удалось автоматически очистить логи LXI: {e}")

    def disarm(self):
        """Остановить активные будильники/режимы — безопасная остановка."""
        self._drop_all_alarms()
        self._log("Disarmed (all alarms dropped)")

    # One-shot / burst
    def single_pulse(self, lead_s: Optional[float] = None):
        """
        Одиночный импульс TTL (ширина ~1 µs фиксирована у прибора).
        lead_s — задержка старта от текущего момента.
        """
        lead = self.cfg.start_lead_s if lead_s is None else float(lead_s)
        self._schedule_alarm_burst_guarded(lead, period_s=0.001, count=1)
        self._log(f"Single pulse scheduled in {lead*1e3:.1f} ms")
        self._auto_clear_logs_if_needed()  # Периодическая очистка логов


    def burst(self, count: int, period_s: Optional[float] = None, lead_s: Optional[float] = None):
        """
        Генерация пачки импульсов
        Args:
            count: количество импульсов в серии (обязательный параметр)
            period_s: период между импульсами (если None, берется из конфига)
            lead_s: задержка старта (если None, берется из конфига)
        """
        n = int(count)
        per = self.cfg.pulse_period_s if period_s is None else float(period_s)
        lead = self.cfg.start_lead_s if lead_s is None else float(lead_s)
        
        if self.test_mode:
            self._log(f"[ЗАГЛУШКА] Генерация пачки импульсов: count={n}, period={per*1e6:.1f} мкс, lead={lead*1e3:.1f} мс")
            return
        
        self._schedule_alarm_burst(start_in_s=lead, period_s=per, count=n)
        self._auto_clear_logs_if_needed()  # Периодическая очистка логов


    # -------- SW-handshake helpers --------

    def pop_ext_event(self) -> Optional[Dict, str]:
        """
        Считать одну запись из лога EXT (или None, если пусто).
        """
        if self.test_mode:
            return 'evt'

        raw = self.query("LOG:STAMp:DATA?")
        if raw.upper().startswith("NO EVENT"):
            return None
        parts = [p.strip() for p in raw.split(",")]
        # Формат: log_sec,log_frac,ts_sec,ts_frac,source(0/1),slope
        self._auto_clear_logs_if_needed()  # Периодическая очистка логов при чтении событий
        return {
            "log_sec": int(float(parts[0])),
            "log_frac": float(parts[1]),
            "ts_sec": int(float(parts[2])),
            "ts_frac": float(parts[3]),
            "source": int(parts[4]),   # 0=EXT1, 1=EXT2
            "slope": parts[5]
        }

    def _is_valid_ext1(self, evt: Dict, slope: Optional[str]) -> bool:
        """Проверка что событие относится к EXT1 и (опц.) нужному фронту."""
        if evt.get("source") != (self.cfg.ext_channel - 1):
            return False
        if slope:
            want = slope.strip().lower()
            got = str(evt.get("slope", "")).strip().lower()
            if want and got and want not in got:
                return False
        # дебаунс
        ts = float(evt["ts_sec"]) + float(evt["ts_frac"])
        if self._last_ext_ts is not None:
            if (ts - self._last_ext_ts) < max(0.0001, self.cfg.ext_debounce_s):
                return False
        self._last_ext_ts = ts
        return True

    def _schedule_alarm_burst(self, start_in_s: float, period_s: float, count: int):
        """Настраивает ALARM1 на серию импульсов начиная с (now + start_in_s)."""
        if period_s < 0.00001:
            raise ValueError("period_s слишком мал (минимум 10 мкс)")
        if count < 1 or count > 5000:
            raise ValueError("count вне диапазона (1..5000)")
        now_sec, now_frac = self._get_tai()
        start_total = now_sec + now_frac + start_in_s
        start_sec = int(start_total)
        start_frac = start_total - start_sec
        self.write(
            f'LXI:TRIGger:ALARM1:SET:CONFigure 1,{start_sec},{start_frac:.9f},{period_s},{count}'
        )
    # -------------------- Utils --------------------

    def _safe_poll_interval(self, per: float) -> float:
        """Подбор мягкой частоты опроса: не чаще половины периода, но и не реже 2 мс."""
        return max(0.002, min(0.05, per * 0.5))

    def _log(self, msg: str):
        if self.cfg.logger:
            self.cfg.logger(msg)
        # по умолчанию — тихо

    # -------------------- Optional helpers --------------------

    def ext_log_count(self) -> int:
        """Сколько записей в EXT-логе на текущий момент (может не поддерживаться всеми прошивками)."""
        for q in ("LOG:STAMp:COUN?", "LOG:STAMp:COUNt?"):
            try:
                return int(self.query(q))
            except Exception:
                continue
        return 0

    @property
    def idn(self) -> Optional[str]:
        return self._idn
