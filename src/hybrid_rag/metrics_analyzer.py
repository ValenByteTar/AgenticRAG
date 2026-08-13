"""
Analizador de Metricas
Lee metrics.log.jsonl y calcula KPIs (p50, p90, tasa de errores, disponibilidad)
"""

import json
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, List, Optional
import statistics


class MetricsAnalyzer:
    """Analiza metricas del sistema desde JSONL"""
    
    def __init__(self, metrics_file: str = "data/metrics.log.jsonl"):
        self.metrics_file = Path(metrics_file)
    
    def read_metrics(self, hours: int = 24) -> List[Dict]:
        """
        Lee metricas de las ultimas N horas
        
        Args:
            hours: Horas hacia atras a leer
            
        Returns:
            Lista de eventos
        """
        if not self.metrics_file.exists():
            return []
        
        cutoff_time = datetime.now() - timedelta(hours=hours)
        events = []
        
        with open(self.metrics_file, 'r', encoding='utf-8') as f:
            for line in f:
                try:
                    event = json.loads(line.strip())
                    
                    # Parsear timestamp
                    ts_str = event.get('ts', '')
                    if ts_str:
                        # Formato: 2025-10-30T06:35:44.300236Z
                        ts = datetime.fromisoformat(ts_str.replace('Z', '+00:00'))
                        
                        # Filtrar por tiempo
                        if ts.replace(tzinfo=None) >= cutoff_time:
                            events.append(event)
                except Exception:
                    continue
        
        return events
    
    def calculate_latency_percentiles(self, events: List[Dict]) -> Dict:
        """
        Calcula percentiles de latencia
        
        Returns:
            Dict con p50, p90, p95, p99, avg, min, max
        """
        # Filtrar eventos con latencia
        latencies = []
        for event in events:
            if 'latency_s' in event:
                latencies.append(event['latency_s'])
        
        if not latencies:
            return {
                'p50': 0,
                'p90': 0,
                'p95': 0,
                'p99': 0,
                'avg': 0,
                'min': 0,
                'max': 0,
                'count': 0
            }
        
        latencies.sort()
        
        return {
            'p50': statistics.median(latencies),
            'p90': latencies[int(len(latencies) * 0.9)] if len(latencies) > 10 else max(latencies),
            'p95': latencies[int(len(latencies) * 0.95)] if len(latencies) > 20 else max(latencies),
            'p99': latencies[int(len(latencies) * 0.99)] if len(latencies) > 100 else max(latencies),
            'avg': statistics.mean(latencies),
            'min': min(latencies),
            'max': max(latencies),
            'count': len(latencies)
        }
    
    def calculate_error_rate(self, events: List[Dict]) -> Dict:
        """
        Calcula tasa de errores
        
        Returns:
            Dict con total, errors, error_rate
        """
        total_queries = 0
        errors = 0
        
        for event in events:
            event_type = event.get('event', '')
            
            if event_type == 'rag_query':
                total_queries += 1
            elif event_type == 'error':
                errors += 1
        
        error_rate = (errors / total_queries * 100) if total_queries > 0 else 0
        
        return {
            'total_queries': total_queries,
            'errors': errors,
            'error_rate': round(error_rate, 2)
        }
    
    def calculate_availability(self, events: List[Dict], hours: int = 24) -> Dict:
        """
        Calcula disponibilidad estimada
        
        Asume que si hay eventos, el sistema esta disponible
        Mide gaps de tiempo sin eventos
        
        Returns:
            Dict con uptime_percent, downtime_minutes
        """
        if not events:
            return {
                'uptime_percent': 0,
                'downtime_minutes': hours * 60,
                'total_minutes': hours * 60
            }
        
        # Ordenar eventos por timestamp
        sorted_events = sorted(events, key=lambda e: e.get('ts', ''))
        
        # Detectar gaps mayores a 5 minutos (posible downtime)
        downtime_minutes = 0
        gap_threshold = timedelta(minutes=5)
        
        for i in range(len(sorted_events) - 1):
            ts1_str = sorted_events[i].get('ts', '')
            ts2_str = sorted_events[i + 1].get('ts', '')
            
            if ts1_str and ts2_str:
                try:
                    ts1 = datetime.fromisoformat(ts1_str.replace('Z', '+00:00'))
                    ts2 = datetime.fromisoformat(ts2_str.replace('Z', '+00:00'))
                    
                    gap = ts2 - ts1
                    if gap > gap_threshold:
                        downtime_minutes += gap.total_seconds() / 60
                except Exception:
                    continue
        
        total_minutes = hours * 60
        uptime_minutes = total_minutes - downtime_minutes
        uptime_percent = (uptime_minutes / total_minutes * 100) if total_minutes > 0 else 0
        
        return {
            'uptime_percent': round(uptime_percent, 2),
            'downtime_minutes': round(downtime_minutes, 1),
            'total_minutes': total_minutes
        }
    
    def get_summary(self, hours: int = 24) -> Dict:
        """
        Obtiene resumen completo de metricas
        
        Args:
            hours: Horas hacia atras a analizar
            
        Returns:
            Dict con todos los KPIs
        """
        events = self.read_metrics(hours=hours)
        
        return {
            'period_hours': hours,
            'total_events': len(events),
            'latency': self.calculate_latency_percentiles(events),
            'errors': self.calculate_error_rate(events),
            'availability': self.calculate_availability(events, hours=hours),
            'timestamp': datetime.now().isoformat()
        }


def test_analyzer():
    """Test del analizador"""
    analyzer = MetricsAnalyzer()
    summary = analyzer.get_summary(hours=24)
    
    print("\n=== RESUMEN DE METRICAS (ultimas 24h) ===\n")
    print(f"Total eventos: {summary['total_events']}")
    print(f"\nLatencia:")
    print(f"  - p50: {summary['latency']['p50']:.2f}s")
    print(f"  - p90: {summary['latency']['p90']:.2f}s")
    print(f"  - avg: {summary['latency']['avg']:.2f}s")
    print(f"  - max: {summary['latency']['max']:.2f}s")
    print(f"\nErrores:")
    print(f"  - Total queries: {summary['errors']['total_queries']}")
    print(f"  - Errores: {summary['errors']['errors']}")
    print(f"  - Tasa: {summary['errors']['error_rate']}%")
    print(f"\nDisponibilidad:")
    print(f"  - Uptime: {summary['availability']['uptime_percent']}%")
    print(f"  - Downtime: {summary['availability']['downtime_minutes']} min")
    print()


if __name__ == "__main__":
    test_analyzer()
