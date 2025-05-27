from enum import Enum

class Channel(Enum):
    """Каналы работы устройства"""
    Receiver = "Receiver"
    Transmitter = "Transmitter"

class Direction(Enum):
    """Направления поляризации"""
    Horizontal = "Horizontal"
    Vertical = "Vertical"

class PhaseDir(Enum):
    """Направления изменения фазы"""
    UP = "UP"
    DOWN = "DOWN" 