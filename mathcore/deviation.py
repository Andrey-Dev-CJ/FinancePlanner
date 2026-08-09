"""
MathCore Deviation — обнаружение дефицитов, рисков, отклонений.
"""
from typing import List, Dict, Optional
from datetime import datetime
from .models import FinancialConfig


class DeviationDetector:
    """Анализ рисков и отклонений от плана."""
    
    def __init__(self, config: FinancialConfig):
        self.config = config
    
    def detect_deficits(self, forecast: List[Dict]) -> List[Dict]:
        """
        Находит все точки, где баланс уходит в минус.
        
        Args:
            forecast: результат ForecastEngine.calculate_daily_balance()
        
        Returns:
            List[Dict]:
            - date: str
            - balance: float
            - deficit: float (насколько в минусе)
            - severity: 'low' | 'medium' | 'critical'
            - recovery_days: int (дней до выхода в плюс)
        """
        deficits = []
        
        for i, point in enumerate(forecast):
            if point['balance'] < 0:
                # Проверяем, не дубль ли (если вчера тоже был минус)
                if i > 0 and forecast[i-1]['balance'] < 0:
                    continue
                
                # Считаем глубину
                deficit = abs(point['balance'])
                
                # Определяем серьёзность
                if deficit > self.config.monthly_income * 0.5:
                    severity = 'critical'
                elif deficit > self.config.monthly_income * 0.2:
                    severity = 'medium'
                else:
                    severity = 'low'
                
                # Ищем восстановление
                recovery_days = self._find_recovery(forecast, i)
                
                deficits.append({
                    'date': point['date'],
                    'day_label': point.get('day_label', point['date']),
                    'balance': point['balance'],
                    'deficit': round(deficit, 2),
                    'severity': severity,
                    'recovery_days': recovery_days
                })
        
        return deficits
    
    def detect_tight_periods(self, forecast: List[Dict], threshold_pct: float = 0.1) -> List[Dict]:
        """
        Находит периоды, когда баланс критически низкий (но не в минусе).
        
        Args:
            forecast: прогноз
            threshold_pct: порог (10% от месячного дохода по умолчанию)
        """
        threshold = self.config.monthly_income * threshold_pct
        tight_periods = []
        in_tight = False
        period_start = None
        
        for point in forecast:
            if 0 <= point['balance'] < threshold:
                if not in_tight:
                    in_tight = True
                    period_start = point['date']
            else:
                if in_tight:
                    tight_periods.append({
                        'start': period_start,
                        'end': point['date'],
                        'min_balance': min(
                            p['balance'] for p in forecast 
                            if period_start <= p['date'] <= point['date']
                        )
                    })
                    in_tight = False
        
        return tight_periods
    
    def what_if_analysis(
        self,
        forecast: List[Dict],
        extra_income: float = 0,
        extra_expense: float = 0,
        extra_income_day: Optional[int] = None,
        skip_event_ids: List[str] = None
    ) -> Dict:
        """
        Что-если анализ.
        
        Показывает, как изменится прогноз при:
        - Дополнительном доходе
        - Дополнительном расходе
        - Отмене событий
        """
        current_deficits = len(self.detect_deficits(forecast))
        
        # Модифицируем конфиг временно
        modified_balance = self.config.initial_balance + extra_income - extra_expense
        
        # Упрощённый расчёт влияния
        total_event_savings = 0
        if skip_event_ids:
            for ev in self.config.events:
                if ev.id in skip_event_ids:
                    total_event_savings += ev.amount
        
        net_impact = extra_income - extra_expense + total_event_savings
        
        return {
            'original_deficits': current_deficits,
            'net_impact': round(net_impact, 2),
            'modified_balance': round(modified_balance, 2),
            'event_savings': round(total_event_savings, 2),
            'recommendation': self._generate_recommendation(net_impact, current_deficits)
        }
    
    def calculate_runway(self, forecast: List[Dict]) -> Dict:
        """
        Рассчитывает 'runway' — сколько дней можно прожить без дохода.
        """
        daily_burn = (self.config.monthly_total_expenses / 30.0)
        
        if daily_burn == 0:
            return {'days': 999, 'daily_burn': 0, 'available_funds': 0, 'message': 'Нет расходов'}
        
        # reserve_envelopes — это просто dict {str: float}
        total_reserves = sum(
            v for v in self.config.reserve_envelopes.values()
            if isinstance(v, (int, float))
        )
        
        available_funds = self.config.initial_balance + total_reserves
        runway_days = int(available_funds / daily_burn) if daily_burn > 0 else 999
        
        return {
            'days': runway_days,
            'daily_burn': round(daily_burn, 2),
            'available_funds': round(available_funds, 2),
            'message': f"Без дохода продержишься {runway_days} дней"
        }
    
    def _find_recovery(self, forecast: List[Dict], deficit_index: int) -> int:
        """Считает, через сколько дней баланс вернётся в плюс."""
        for i in range(deficit_index + 1, len(forecast)):
            if forecast[i]['balance'] >= 0:
                return i - deficit_index
        return len(forecast) - deficit_index
    
    def _generate_recommendation(self, net_impact: float, deficits: int) -> str:
        if deficits == 0 and net_impact >= 0:
            return "✅ Всё в порядке, дефицитов нет"
        elif net_impact > 0:
            return f"💡 Изменения улучшат баланс на {net_impact:,.0f} ₽"
        elif net_impact < 0:
            return f"⚠️ Изменения ухудшат баланс на {abs(net_impact):,.0f} ₽"
        else:
            return "ℹ️ Изменения не влияют на прогноз"


    def calculate_required_reserve(self, forecast: List[Dict]) -> List[float]:
        """
        Для каждой даты считает минимальную сумму, которую НЕОБХОДИМО
        иметь на руках, чтобы все будущие обязательства были покрыты.
        
        Если текущий баланс ниже этого значения — в дальнейшем возникнет дефицит.
        
        Математика: required[i] = max(0, max_{j>=i} sum_{k=i..j} (expenses[k] - income[k]))
        """
        n = len(forecast)
        if n == 0:
            return []
        
        net = [p['expenses_paid'] - p['income_received'] for p in forecast]
        
        # total[i] = сумма net[i..n-1]
        total = [0.0] * (n + 1)
        for i in range(n - 1, -1, -1):
            total[i] = total[i + 1] + net[i]
        
        # min_suffix[i] = min(total[i..n])
        min_suffix = [0.0] * (n + 2)
        min_suffix[n] = total[n]
        for i in range(n - 1, -1, -1):
            min_suffix[i] = min(total[i], min_suffix[i + 1])
        
        required = []
        for i in range(n):
            min_after = min_suffix[i + 1]   # min total[i+1..n]
            required.append(round(max(0.0, total[i] - min_after), 2))
        
        return required