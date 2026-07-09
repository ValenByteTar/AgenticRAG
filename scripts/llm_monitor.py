import argparse
import json
import os
import sys
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, Optional

# Optional deps
try:
    import psutil  # type: ignore
except Exception:
    psutil = None  # type: ignore

try:
    import pynvml  # type: ignore
except Exception:
    pynvml = None  # type: ignore

# Optional pretty output
try:
    from rich.console import Console  # type: ignore
    from rich.table import Table  # type: ignore
    from rich.live import Live  # type: ignore
    from rich.panel import Panel  # type: ignore
except Exception:
    Console = None  # type: ignore
    Table = None  # type: ignore
    Live = None  # type: ignore
    Panel = None  # type: ignore

DEFAULT_METRICS_FILE = Path("data/metrics.log.jsonl")
DEFAULT_MONITOR_LOG = Path("data/monitor_samples.jsonl")


def now_iso() -> str:
    return datetime.utcnow().isoformat() + "Z"


def duration_to_seconds(raw: Optional[float]) -> Optional[float]:
    if raw is None:
        return None
    # Heurística: ollama suele devolver duraciones en nanosegundos.
    # Si es muy grande, asumimos ns; si no, ya está en s.
    if raw > 1e6:
        return raw / 1e9
    return float(raw)


class FileTailer:
    def __init__(self, path: Path, start_at_end: bool = True, poll_interval: float = 0.2):
        self.path = path
        self.start_at_end = start_at_end
        self.poll_interval = poll_interval
        self._stop = threading.Event()
        self._thread = None
        self._callbacks = []  # list of callables(line:str)

    def on_line(self, cb):
        self._callbacks.append(cb)

    def start(self):
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self):
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=1.0)

    def _run(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        # Touch file if missing
        if not self.path.exists():
            try:
                self.path.write_text("", encoding="utf-8")
            except Exception:
                pass
        try:
            with self.path.open("r", encoding="utf-8") as f:
                if self.start_at_end:
                    f.seek(0, os.SEEK_END)
                while not self._stop.is_set():
                    pos = f.tell()
                    line = f.readline()
                    if not line:
                        time.sleep(self.poll_interval)
                        f.seek(pos)
                    else:
                        for cb in self._callbacks:
                            try:
                                cb(line)
                            except Exception:
                                pass
        except Exception:
            # Silent exit
            return


class MonitorLogger:
    def __init__(self, path: Path):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()

    def log(self, record: Dict[str, Any]) -> None:
        try:
            with self._lock:
                with self.path.open("a", encoding="utf-8") as f:
                    f.write(json.dumps(record, ensure_ascii=False) + "\n")
        except Exception:
            pass


class GPUInfo:
    def __init__(self):
        self.available = False
        self._use_nvml = False
        self._nvml_device = None
        try:
            if pynvml is not None:
                pynvml.nvmlInit()
                self._nvml_device = pynvml.nvmlDeviceGetHandleByIndex(0)
                self.available = True
                self._use_nvml = True
        except Exception:
            self._use_nvml = False
            self.available = self._check_nvidia_smi()

    def _check_nvidia_smi(self) -> bool:
        try:
            import subprocess
            subprocess.run(["nvidia-smi", "-L"], capture_output=True, check=False)
            return True
        except Exception:
            return False

    def get_summary(self) -> Dict[str, Any]:
        if not self.available:
            return {"gpu_present": False}
        if self._use_nvml:
            try:
                util = pynvml.nvmlDeviceGetUtilizationRates(self._nvml_device)
                mem = pynvml.nvmlDeviceGetMemoryInfo(self._nvml_device)
                temp = None
                try:
                    temp = pynvml.nvmlDeviceGetTemperature(self._nvml_device, pynvml.NVML_TEMPERATURE_GPU)
                except Exception:
                    temp = None
                return {
                    "gpu_present": True,
                    "gpu_util_pct": util.gpu,
                    "vram_used_mb": int(mem.used / (1024 * 1024)),
                    "vram_total_mb": int(mem.total / (1024 * 1024)),
                    "gpu_temp_c": temp,
                }
            except Exception:
                return {"gpu_present": True}
        else:
            # Fallback nvidia-smi
            try:
                import subprocess
                q = [
                    "nvidia-smi",
                    "--query-gpu=utilization.gpu,memory.used,memory.total,temperature.gpu",
                    "--format=csv,noheader,nounits",
                ]
                p = subprocess.run(q, capture_output=True, text=True, check=False)
                out = (p.stdout or "").strip().splitlines()
                if not out:
                    return {"gpu_present": True}
                vals = out[0].split(",")
                vals = [v.strip() for v in vals]
                util, used, total, temp = [int(float(v)) for v in vals[:4]]
                return {
                    "gpu_present": True,
                    "gpu_util_pct": util,
                    "vram_used_mb": used,
                    "vram_total_mb": total,
                    "gpu_temp_c": temp,
                }
            except Exception:
                return {"gpu_present": True}

    def get_process_vram(self) -> Dict[int, int]:
        # Return mapping pid->used_mb if available
        if self._use_nvml and self._nvml_device is not None:
            try:
                procs = pynvml.nvmlDeviceGetComputeRunningProcesses_v3(self._nvml_device)
                d: Dict[int, int] = {}
                for p in procs:
                    try:
                        used_mb = int(p.usedGpuMemory / (1024 * 1024))
                    except Exception:
                        used_mb = 0
                    d[int(p.pid)] = used_mb
                return d
            except Exception:
                return {}
        else:
            try:
                import subprocess
                q = [
                    "nvidia-smi",
                    "--query-compute-apps=pid,process_name,used_memory",
                    "--format=csv,noheader,nounits",
                ]
                p = subprocess.run(q, capture_output=True, text=True, check=False)
                lines = (p.stdout or "").strip().splitlines()
                d: Dict[int, int] = {}
                for line in lines:
                    parts = [x.strip() for x in line.split(",")]
                    if len(parts) >= 3:
                        try:
                            pid = int(parts[0])
                            used_mb = int(float(parts[2]))
                            d[pid] = used_mb
                        except Exception:
                            continue
                return d
            except Exception:
                return {}


class ProcessFinder:
    def __init__(self, names: Iterable[str]):
        self.names = {n.lower() for n in names}

    def find(self) -> Dict[str, Optional[int]]:
        result = {n: None for n in self.names}
        if psutil is None:
            return result
        for p in psutil.process_iter(attrs=["pid", "name", "cmdline"]):
            try:
                name = (p.info.get("name") or "").lower()
                cmdline = " ".join(p.info.get("cmdline") or []).lower()
                for n in list(result.keys()):
                    if result[n] is None and (n in name or n in cmdline):
                        result[n] = int(p.info["pid"])
            except Exception:
                continue
        return result


class ResourceSampler(threading.Thread):
    def __init__(self, interval: float, logger: MonitorLogger, gpu: GPUInfo, target_pids: Iterable[int]):
        super().__init__(daemon=True)
        self.interval = max(0.2, interval)
        self.logger = logger
        self.gpu = gpu
        self.target_pids = set([int(p) for p in target_pids if p])
        self._stop = threading.Event()
        self.last_sample: Dict[str, Any] = {}

    def stop(self):
        self._stop.set()

    def run(self):
        while not self._stop.is_set():
            rec: Dict[str, Any] = {
                "event": "resource_sample",
                "ts": now_iso(),
            }
            # System-level
            if psutil is not None:
                try:
                    rec.update({
                        "cpu_pct": psutil.cpu_percent(interval=None),
                        "ram_used_mb": int(psutil.virtual_memory().used / (1024 * 1024)),
                        "ram_pct": float(psutil.virtual_memory().percent),
                    })
                except Exception:
                    pass
            # GPU
            try:
                rec.update(self.gpu.get_summary())
            except Exception:
                pass
            # Per-process
            if psutil is not None:
                procs: Dict[int, Dict[str, Any]] = {}
                for pid in list(self.target_pids):
                    try:
                        p = psutil.Process(pid)
                        procs[pid] = {
                            "cpu_pct": p.cpu_percent(interval=None),
                            "rss_mb": int((p.memory_info().rss) / (1024 * 1024)),
                            "name": p.name(),
                        }
                    except Exception:
                        continue
                # Merge per-process VRAM
                try:
                    vmap = self.gpu.get_process_vram() if self.gpu.available else {}
                    for pid, used_mb in vmap.items():
                        if pid in procs:
                            procs[pid]["vram_mb"] = used_mb
                except Exception:
                    pass
                rec["processes"] = procs
            self.last_sample = rec
            self.logger.log(rec)
            time.sleep(self.interval)


class EventBuffer:
    def __init__(self, maxlen: int = 50):
        from collections import deque
        self._buf = deque(maxlen=maxlen)
        self._lock = threading.Lock()

    def append(self, obj: Dict[str, Any]):
        with self._lock:
            self._buf.append(obj)

    def last(self, event: Optional[str] = None) -> Optional[Dict[str, Any]]:
        with self._lock:
            if not self._buf:
                return None
            if event is None:
                return self._buf[-1]
            for item in reversed(self._buf):
                if item.get("event") == event:
                    return item
            return None

    def snapshot(self) -> list:
        with self._lock:
            return list(self._buf)


def derive_llm_metrics(ev: Dict[str, Any]) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    eval_count = ev.get("eval_count")
    prompt_eval_count = ev.get("prompt_eval_count")
    td = duration_to_seconds(ev.get("total_duration"))
    ld = duration_to_seconds(ev.get("load_duration"))
    pd = duration_to_seconds(ev.get("prompt_eval_duration"))
    ed = duration_to_seconds(ev.get("eval_duration"))
    out["total_s"] = td
    out["load_s"] = ld
    out["prefill_s"] = pd
    out["decode_s"] = ed
    try:
        out["ttft_est_s"] = (ld or 0.0) + (pd or 0.0)
    except Exception:
        out["ttft_est_s"] = None
    try:
        if ed and eval_count:
            out["decode_tps"] = float(eval_count) / float(ed)
    except Exception:
        pass
    try:
        if pd and prompt_eval_count:
            out["prefill_tps"] = float(prompt_eval_count) / float(pd)
    except Exception:
        pass
    out["out_tokens"] = eval_count
    out["in_tokens"] = prompt_eval_count
    return out


def build_table(sample: Dict[str, Any], last_llm: Optional[Dict[str, Any]], last_rag: Optional[Dict[str, Any]]):
    if Console is None or Table is None:
        return None
    t = Table(title="LLM Monitor", expand=True)
    t.add_column("Metric", justify="left")
    t.add_column("Value", justify="right")

    # System metrics
    if sample:
        t.add_row("Time", sample.get("ts", now_iso()))
        if "cpu_pct" in sample:
            t.add_row("CPU %", f"{sample.get('cpu_pct', 0):.1f}")
        if "ram_pct" in sample:
            t.add_row("RAM %", f"{sample.get('ram_pct', 0):.1f}")
        if "ram_used_mb" in sample:
            t.add_row("RAM Used (MB)", str(sample.get("ram_used_mb", 0)))
        if sample.get("gpu_present"):
            if "gpu_util_pct" in sample:
                t.add_row("GPU %", str(sample.get("gpu_util_pct")))
            if "vram_used_mb" in sample and "vram_total_mb" in sample:
                t.add_row("VRAM (MB)", f"{sample.get('vram_used_mb')}/{sample.get('vram_total_mb')}")
            if sample.get("gpu_temp_c") is not None:
                t.add_row("GPU Temp (C)", str(sample.get("gpu_temp_c")))

    # LLM metrics
    if last_llm:
        d = derive_llm_metrics(last_llm)
        t.add_row("TTFT est (s)", f"{d.get('ttft_est_s', 0) if d.get('ttft_est_s') is not None else 'n/a'}")
        if d.get("prefill_s") is not None:
            t.add_row("Prefill (s)", f"{d.get('prefill_s'):.3f}")
        if d.get("decode_s") is not None:
            t.add_row("Decode (s)", f"{d.get('decode_s'):.3f}")
        if d.get("decode_tps") is not None:
            t.add_row("Decode TPS", f"{d.get('decode_tps'):.1f}")
        if d.get("prefill_tps") is not None:
            t.add_row("Prefill TPS", f"{d.get('prefill_tps'):.1f}")
        if d.get("in_tokens") is not None:
            t.add_row("Input tokens", str(d.get("in_tokens")))
        if d.get("out_tokens") is not None:
            t.add_row("Output tokens", str(d.get("out_tokens")))

    # RAG metrics
    if last_rag:
        t.add_row("RAG latency (s)", f"{last_rag.get('latency_s', 'n/a')}")
        if last_rag.get("approx_prompt_tokens") is not None:
            t.add_row("Approx prompt tokens", str(last_rag.get("approx_prompt_tokens")))
        if last_rag.get("approx_ctx_tokens") is not None:
            t.add_row("Approx ctx tokens", str(last_rag.get("approx_ctx_tokens")))

    # Per-process snapshot
    if sample and isinstance(sample.get("processes"), dict) and sample["processes"]:
        t2 = Table(title="Processes", expand=True)
        t2.add_column("PID")
        t2.add_column("Name")
        t2.add_column("CPU %")
        t2.add_column("RSS MB")
        t2.add_column("VRAM MB")
        for pid, info in sample["processes"].items():
            t2.add_row(
                str(pid),
                str(info.get("name", "")),
                f"{info.get('cpu_pct', 0):.1f}",
                str(info.get("rss_mb", 0)),
                str(info.get("vram_mb", 0)),
            )
        if Panel is not None:
            return Panel.fit(t, subtitle_align="right", subtitle="LLM + RAG metrics") if t2 is None else Panel.fit(t, subtitle_align="right")
    return t


def main():
    ap = argparse.ArgumentParser(description="Real-time monitor for LLM/RAG + system resources")
    ap.add_argument("--metrics-file", type=str, default=str(DEFAULT_METRICS_FILE), help="Path to metrics JSONL file")
    ap.add_argument("--log-file", type=str, default=str(DEFAULT_MONITOR_LOG), help="Output JSONL for monitor samples")
    ap.add_argument("--interval", type=float, default=0.5, help="Sampling interval seconds")
    ap.add_argument("--processes", type=str, nargs="*", default=["python", "ollama", "ollama_llama_server"], help="Process name hints to track")
    ap.add_argument("--no-ui", action="store_true", help="Disable live UI, just log")
    args = ap.parse_args()

    metrics_file = Path(args.metrics_file)
    log_file = Path(args.log_file)

    console = Console() if Console is not None else None

    logger = MonitorLogger(log_file)
    gpu = GPUInfo()

    # Find PIDs
    target_pids: Iterable[int] = []
    if psutil is not None:
        pf = ProcessFinder(args.processes)
        found = pf.find()
        if console:
            console.print(f"[dim]Process hints -> {found}[/dim]")
        target_pids = [pid for pid in found.values() if pid]

    sampler = ResourceSampler(args.interval, logger, gpu, target_pids)
    sampler.start()

    events = EventBuffer(maxlen=200)

    def handle_line(line: str):
        line = line.strip()
        if not line:
            return
        try:
            obj = json.loads(line)
            ev = str(obj.get("event", ""))
            if ev in {"llm_infer", "rag_query", "out_of_domain"}:
                events.append(obj)
                # Also mirror to monitor log with tag
                rec = {"event": f"log_{ev}", "ts": now_iso(), **obj}
                logger.log(rec)
        except Exception:
            return

    tailer = FileTailer(metrics_file, start_at_end=False)
    tailer.on_line(handle_line)
    tailer.start()

    try:
        if args.no_ui or console is None or Table is None or Live is None:
            # Headless mode: just run and log
            if console:
                console.print("[green]Monitor running (no UI). Press Ctrl+C to stop.[/green]")
            while True:
                time.sleep(1.0)
        else:
            with Live(refresh_per_second=max(2, int(1.0 / max(args.interval, 0.2))), console=console) as live:
                while True:
                    sample = sampler.last_sample
                    last_llm = events.last("llm_infer")
                    last_rag = events.last("rag_query")
                    table = build_table(sample, last_llm, last_rag)
                    if table is not None:
                        live.update(table)
                    time.sleep(args.interval)
    except KeyboardInterrupt:
        if console:
            console.print("\n[yellow]Stopping monitor...[/yellow]")
    finally:
        try:
            tailer.stop()
        except Exception:
            pass
        try:
            sampler.stop()
        except Exception:
            pass


if __name__ == "__main__":
    main()
