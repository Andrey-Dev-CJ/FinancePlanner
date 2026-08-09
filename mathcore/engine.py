"""
MathCore Engine — главный фасад.
Все расчёты вызываются через этот класс.
"""
from datetime import datetime
from typing import Dict, List, Optional
from .models import FinancialConfig
from .forecast import ForecastEngine
from .sprint import SprintEngine
from .deviation import DeviationDetector
from .config import ConfigLoader


class MathCore:
    """
    Главный класс математического ядра.
    
    Usage:
        core = MathCore.from_config_file('config.json')
        # или
        core = MathCore.from_dict({...})
        
        forecast = core.get_forecast(days=90)
        sprints = core.get_sprints(count=6)
        risks = core.get_risks()
        summary = core.get_summary()
    """
    
    def __init__(self, config: FinancialConfig):
        self.config = config
        self._forecast_engine = ForecastEngine(config)
        self._sprint_engine = SprintEngine(config)
        self._deviation_detector = DeviationDetector(config)
    
    # ===== Фабричные методы =====
    
    @classmethod
    def from_config_file(cls, filepath: str) -> 'MathCore':
        config = ConfigLoader.from_json(filepath)
        return cls(config)
    
    @classmethod
    def from_dict(cls, data: dict) -> 'MathCore':
        config = ConfigLoader.from_dict(data)
        return cls(config)
    
    @classmethod
    def empty(cls) -> 'MathCore':
        return cls(ConfigLoader.empty_config())
    
    # ===== Основные методы =====
    
    def get_forecast(self, days: int = 90) -> Dict:
        """
        Полный прогноз: баланс + необходимый резерв + дефициты + предупреждения.
        """
        start = datetime.now()
        daily = self._forecast_engine.calculate_daily_balance(start, days)
        
        # Необходимый резерв по дням
        required = self._deviation_detector.calculate_required_reserve(daily)
        for i, point in enumerate(daily):
            point['required_reserve'] = required[i]
        
        deficits = self._deviation_detector.detect_deficits(daily)
        tight = self._deviation_detector.detect_tight_periods(daily)
        
        current_required = required[0] if required else 0
        deficit_risk = self.config.initial_balance < current_required
        
        return {
            'daily': daily,
            'deficits': deficits,
            'tight_periods': tight,
            'required_reserve': required,
            'current_required_reserve': current_required,
            'deficit_risk': deficit_risk,
            'total_days': days,
            'final_balance': daily[-1]['balance'] if daily else 0
        }
    
    def get_sprints(self, count: int = 6) -> List[Dict]:
        """Расчёт спринтов."""
        return self._sprint_engine.calculate_sprints(datetime.now(), count)
    
    def get_current_sprint(self) -> Dict:
        """Текущий спринт."""
        return self._sprint_engine.get_current_sprint()
    
    def get_risks(self) -> Dict:
        """Все риски и предупреждения."""
        forecast = self._forecast_engine.calculate_daily_balance(
            datetime.now(), days=90
        )
        deficits = self._deviation_detector.detect_deficits(forecast)
        tight = self._deviation_detector.detect_tight_periods(forecast)
        runway = self._deviation_detector.calculate_runway(forecast)
        
        return {
            'deficits': deficits,
            'tight_periods': tight,
            'runway': runway,
            'risk_level': self._calculate_risk_level(deficits, tight)
        }
    
    def get_summary(self) -> Dict:
        """Сводка по бюджету."""
        return {
            'monthly_income': self.config.monthly_income,
            'monthly_fixed': self.config.monthly_fixed,
            'monthly_variable': self.config.monthly_variable,
            'monthly_total_expenses': self.config.monthly_total_expenses,
            'monthly_surplus': self.config.monthly_surplus,
            'initial_balance': self.config.initial_balance,
            'reserve_envelopes': self.config.reserve_envelopes,
            'pending_events_count': len(self.config.pending_events),
            'pending_events_cost': self.config.total_pending_events_cost,
            'pay_days': self.config.pay_schedule.pay_days
        }
    
    def what_if(
        self,
        extra_income: float = 0,
        extra_expense: float = 0,
        skip_event_ids: List[str] = None
    ) -> Dict:
        """Что-если анализ."""
        forecast = self._forecast_engine.calculate_daily_balance(
            datetime.now(), days=90
        )
        return self._deviation_detector.what_if_analysis(
            forecast, extra_income, extra_expense,
            skip_event_ids=skip_event_ids
        )
    
    def save_config(self, filepath: str):
        """Сохраняет текущую конфигурацию."""
        ConfigLoader.to_json(self.config, filepath)
    
    def update_config(self, new_data: dict):
        """Обновляет конфигурацию из словаря."""
        self.config = ConfigLoader.from_dict(new_data)
        self._forecast_engine = ForecastEngine(self.config)
        self._sprint_engine = SprintEngine(self.config)
        self._deviation_detector = DeviationDetector(self.config)
    
    # ===== Приватные =====
    
    def _calculate_risk_level(self, deficits: list, tight: list) -> str:
        """Общий уровень риска."""
        if any(d['severity'] == 'critical' for d in deficits):
            return 'critical'
        elif len(deficits) > 0:
            return 'warning'
        elif len(tight) > 0:
            return 'caution'
        return 'safe'